import json
from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from enum import Enum
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI
import os, uuid

from modules import build_database, query
from modules.db_manager import db_manager

app = FastAPI()

# 환경변수 로드
load_dotenv(".env")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL_NAME = "gpt-5-mini"

openai_client = OpenAI(api_key=OPENAI_API_KEY)
chromadb_client, judgement_collection = build_database.build(False)

# System prompts
with open("./prompts/0.chat_model_system_prompt.txt", "r", encoding="utf-8") as f:
    chat_syst_prompt = f.read()
with open("./prompts/1.extract_model_system_prompt.txt", "r", encoding="utf-8") as f:
    extract_syst_prompt = f.read()
with open("./prompts/2.query_model_system_prompt.txt", "r", encoding="utf-8") as f:
    query_syst_prompt = f.read()

# 세션 안의 대화들(conv_id들 + history) 및 현재 active 대화id
session_data = {}
"""
session_data = {
    session_id: {
        "conversations": {
            conv_id1: {
              "history": [
                {"role": "user", "content": "..."},
                {"role": "assistant", "content", "..."},
              ],
              "title": "대화 제목"},
            ...
        },
        "active_conversation_id": conv_id1
    }
}
"""

# POST 요청 데이터 모델
class UserQuery(BaseModel):
    session_id: str
    conv_id: str
    query: str

@app.get("/")
def init_or_restore_session():
    # 아무 세션도 없으면 새 세션 생성
    if len(session_data) == 0:
        session_id = str(uuid.uuid4())
        session_data[session_id] = {
            "conversations": {},
            "active_conversation_id": None
        }
        print(f"새 세션이 생성되었습니다: {session_id}")

    # 반환될 세션 지정(세션은 1개만 쓰기로 상정)
    session_id = next(iter(session_data.keys()))
    
    # 반환될 대화 지정
    active_conv_id = session_data[session_id]["active_conversation_id"]
    title = None
    if active_conv_id:
        title = session_data[session_id]["conversations"][active_conv_id]["title"]
        print(f"기존 대화를 복원했습니다: {session_id} / {active_conv_id}")
        return {
            "session_id": session_id,
            "active_conv_id": active_conv_id,
            "title": title
        }
    return {"session_id": session_id}

# DB 업데이트
@app.post("/update_db")
def update_database():
    db_manager.init_db([False, False, True])
    return {"message": "DB 업데이트 완료"}

# 사용자 쿼리를 가지고 관련 판례 검색
@app.post("/ask")
def ask_question(userInput: UserQuery):
    session_id = userInput.session_id
    conv_id = userInput.conv_id
    user_query = userInput.query
    if session_id not in session_data:
        return {"status": "error", "message": "세션이 없습니다."}
    
    print(f"[Sess:{session_id[:5]}... / Conv:{conv_id[5:10]}...] 유저 질문: {user_query}")
    
    # [Chat Model]의 Output Schema
    class ChatStatusEnum(str, Enum):
        CONTINUE = "CONTINUE"
        DONE = "DONE"
    class ChatSchema(BaseModel):
        status: ChatStatusEnum
        message: str
        class Config:
            extra = "forbid"

    # [Extract Model]의 Output Schema
    class Parties(BaseModel):
        sender: Optional[str] = None
        receiver: Optional[str] = None
        relationship: Optional[str] = None
        class Config:
            extra = "forbid"
    class ExtractSchema(BaseModel):
        parties: Parties
        action: Optional[str] = None
        result_or_damage: Optional[str] = None
        legal_issue: Optional[str] = None
        legal_domain: Optional[str] = None
        user_intent: Optional[str] = None
        class Config:
            extra = "forbid"
        
    # [Query Model]의 Output JSON
    class QueryStatusEnum(str, Enum):
        sufficient = "sufficient"
        warning = "warning"
        mandatory = "mandatory"
    class InsufficientField(str, Enum):
        parties = "parties"
        action = "action"
        result_or_damage = "result_or_damage"
        legal_issue = "legal_issue"
        legal_domain = "legal_domain"
        user_intent = "user_intent"
        class Config:
            extra = "forbid"
    class QuerySchema(BaseModel):
        status: QueryStatusEnum # 상태 표시: sufficient / warning / mandatory
        # 쿼리 생성 (sufficient / warning 상태에서만 사용)
        query_for_meaning: Optional[str] = None
        query_for_keyword: Optional[str] = None
        # 부족한 필드 목록 (warning / mandatory 상태)
        insufficient_field: Optional[List[InsufficientField]] = None
        # Chat Model 피드백용 메시지 (mandatory 상태에서만 존재)
        feedback_to_chat: Optional[str] = None
        class Config:
            extra = "forbid"
    
    # [Answer Model]의 Output JSON
    # ...(TODO)

    print("[FastAPI]\tuser_query를 history에 넣는 중...")
    session_data[session_id]["conversations"][conv_id]["history"].append({"role": "user", "content": user_query})


    # [Chat Model] 호출
    print(f"[Chat Model] \t-> 답변 생성 중...")
    history = session_data[session_id]["conversations"][conv_id]["history"]
    
    chat_response = openai_client.responses.parse(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": chat_syst_prompt},
            *history
        ],
        text_format=ChatSchema
    )
    
    # output_parsed(Pydantic형태)
    chat_status = chat_response.output_parsed.status
    chat_msg = chat_response.output_parsed.message
    print(f"[Chat Model] {chat_status}\t->", end=" ")
    
    if chat_status == "CONTINUE":
        print(f"답변 저장 중... [{chat_msg[:30]}...]")
        session_data[session_id]["conversations"][conv_id]["history"].append({"role": "assistant", "content": chat_msg})
        return {"status": "ok", "answer": chat_msg}


    # [Extract Model] 호출
    print(f"Extract Model 호출... [디버깅(아무것도 없는 게 좋음): {chat_msg}...]")
    extract_response = openai_client.responses.parse(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": extract_syst_prompt},
            *history
        ],
        text_format=ExtractSchema
    )

    # output_parsed(Pydantic형태)
    extract_output = extract_response.output_parsed
    try:
        print(f"[Extract Model]\t-> 대화에서 정보 추출됨: {json.dumps(extract_output.model_dump(), ensure_ascii=False, indent=2)}")
    except:
        print("[Extract Model]\t-> 대화에서 정보 추출됨 (raw):", extract_output)


    # [Query Model] 호출
    print(f"[Extract Model]\t-> Query Model 호출...")
    query_response = openai_client.responses.parse(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": query_syst_prompt},
            {"role": "user", "content": extract_output.model_dump_json()}
        ],
        text_format=QuerySchema
    )

    # output_parsed(Pydantic형태)
    query_output = query_response.output_parsed
    query_status = query_output.status
    print(f"[Query Model] {query_status}\t->", end=" ")
    if query_status == "sufficient" or query_status == "warning":
        m = query_output.query_for_meaning
        k = query_output.query_for_keyword
        print("Query 생성 완료")
        print(f" - [Query Model] query for meaning\t-> {m}")
        print(f" - [Query Model] query for keyword\t-> {k}")
        # RAG 검색
        # API 검색
        # build_context
        # answer = [Answer Model] 호출
        answer = "[Answer Model]의 답변 결과가 담겨있을 채팅입니다."
        return {"status": "ok", "answer": answer}
    
    # Query Model의 feedback을 history에 포함
    insufficient = ", ".join([field.value for field in query_output.insufficient_field or []])
    feedback_msg = f"판례 검색을 위한 쿼리를 생성하는 데 다음 정보가 필요합니다: {insufficient}."
    feedback_msg += f"Query Model의 feedback message: {query_output.feedback_to_chat}"
    print("Feedback 생성됨")
    print(f" - [Query Model] missing\t-> {insufficient}")
    print(f" - [Query Model] feedback_msg\t-> {feedback_msg}")
    
    print(f"[Query Model] feedback을 history에 저장 중...")
    session_data[session_id]["conversations"][conv_id]["history"].append({
        "role": "system", "content": feedback_msg})


    # [Chat Model] 호출
    print(f"[Chat Model] \t-> 피드백을 수용하여 질문 생성 중...")
    history = session_data[session_id]["conversations"][conv_id]["history"]
    
    chat_response = openai_client.responses.parse(
        model=MODEL_NAME,
        input=[
            {"role": "system", "content": chat_syst_prompt},
            *history
        ],
        text_format=ChatSchema
    )
    
    # output_parsed(Pydantic형태)
    chat_status = chat_response.output_parsed.status
    chat_msg = chat_response.output_parsed.message
    print(f"[Chat Model] {chat_status}\t-> 답변 저장 중... [{chat_msg[:30]}...]")
    session_data[session_id]["conversations"][conv_id]["history"].append({
        "role": "assistant", "content": chat_msg})
    return {"status": "ok", "answer": chat_msg}


# 다운로드 요청 시 파일 생성
@app.get("/download_conversation")
def download_conversation(session_id: str, conversation_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "해당 세션이 없습니다."}
    if conversation_id not in session_data[session_id].get("conversations", {}):
        return {"status": "error", "message": "대화 ID가 없습니다."}
    
    history = session_data[session_id]["conversations"][conversation_id]["history"]
    title = session_data[session_id]["conversations"][conversation_id]["title"]
    
    if not history:
        return {
            "status": "error",
            "message": f"\"{title}\"의 대화 내용이 없습니다."
        }
    
    lines = [f"=== 세션: {session_id[:5]}..., 대화 ID: {conversation_id[:10]}... ===\n\n"]
    for turn in history:
        if turn["role"] == "system":
            continue
        role = "사용자" if turn["role"] == "user" else "법률상담봇"
        lines.append(f"  - [{role}]:\n{turn['content']}\n\n")
    
    return JSONResponse({
        "status": "ok",
        "file": "".join(lines)
    })

# 대화 삭제
@app.delete("/delete_conversation")
def delete_conversation(session_id: str, conversation_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "해당 세션이 없습니다."}
    
    conversations = session_data[session_id].get("conversations", {})
    if conversation_id not in conversations:
        return {"status": "error", "message": "해당 대화가 없습니다."}
    
    del conversations[conversation_id]
    
    # active 대화 지울 경우 active 갱신
    if session_data[session_id]["active_conversation_id"] == conversation_id:
        if len(conversations) > 0:
            # 남은 대화 중 첫 번째를 active로 설정
            new_active = next(iter(conversations.keys()))
            session_data[session_id]["active_conversation_id"] = new_active
        else:
            # 비어 있다면 active 제거
            session_data[session_id]["active_conversation_id"] = None
    return {
        "status": "ok",
        "message": "대화 삭제됨",
        "active_conv_id": session_data[session_id]["active_conversation_id"],
    }

@app.get("/get_conversation_detail")
def get_conversation_detail(session_id: str, conversation_id: str):
    # 세션 존재 확인
    if session_id not in session_data:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "해당 세션이 없습니다."}
        )
    
    conversations = session_data[session_id].get("conversations", {})
    
    # 대화 존재 확인
    if conversation_id not in conversations:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": "해당 대화가 없습니다."}
        )
    
    conv = conversations[conversation_id]
    history = conv.get("history", [])
    title = conv.get("title", "")
    
    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "title": title,
        "history": history
    }

# 대화 불러오기
@app.get("/get_conversations")
def get_conversations(session_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "해당 세션이 없습니다."}

    conversations = session_data[session_id]["conversations"]
    active = session_data[session_id]["active_conversation_id"]

    items = []
    for cid, conv in conversations.items():
        items.append({
            "conversation_id": cid,
            "title": conv["title"],
            "is_active": (cid == active),
        })

    return {"status": "ok", "conversations": items}


@app.post("/new_conversation")
def new_conversation(session_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "세션이 없습니다."}

    # 새 대화(new_conv_id) 생성
    new_conv_id = "conv_" + str(uuid.uuid4())[5:]
    session_data[session_id]["conversations"][new_conv_id] = {
        "title": f"대화 {len(session_data[session_id]["conversations"]) + 1}",
        "history": []
    }
    # active_conv로 설정
    session_data[session_id]["active_conversation_id"] = new_conv_id
    print(f"새 대화 생성됨:\tID: {new_conv_id}")

    return {
        "status": "ok",
        "new_conv_id": new_conv_id,
        "title": session_data[session_id]["conversations"][new_conv_id]["title"]
    }


@app.post("/switch_conversation")
def switch_conversation(session_id: str, conversation_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "세션이 없습니다."}
    if conversation_id not in session_data[session_id].get("conversations", {}):
        return {"status": "error", "message": "대화가 존재하지 않습니다."}

    session_data[session_id]["active_conversation_id"] = conversation_id

    return {
        "status": "ok",
        "title": session_data[session_id]["conversations"][conversation_id]["title"]
    }
