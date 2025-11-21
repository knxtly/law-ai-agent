from fastapi import FastAPI
from fastapi import Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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

openai_client = OpenAI(api_key=OPENAI_API_KEY)
chromadb_client, judgement_collection = build_database.build(False)

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
    
    print(f"[{session_id} / {conv_id}] 유저 질문: {user_query}")
    
    # TODO: 이 부분에 첫 번째 모델의 답변 생성
    # answer = openai_client.responses.create(
    #     model="gpt-5-mini",
    #     conversation=conv_id,
    #     prompt=user_query,
    # )
    answer = "질문을 받았습니다."

    print("대화 저장 중...")
    session_data[session_id]["conversations"][conv_id]["history"].append(
        {"role": "user", "content": user_query})
    session_data[session_id]["conversations"][conv_id]["history"].append(
        {"role": "assistant", "content": answer})
    
    return {
        "status": "ok",
        "answer": answer
    }

# 다운로드 요청 시 파일 생성
@app.get("/download_conversation")
def download_conversation(session_id: str, conversation_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "해당 세션이 없습니다."}
    if conversation_id not in session_data[session_id].get("conversations", {}):
        return {"status": "error", "message": "대화 ID가 없습니다."}
    
    history = session_data[session_id]["conversations"][conversation_id]["history"]
    title = session_data[session_id]["conversations"][conversation_id]["title"]
    
    if len(history) == 0:
        return {"status": "error", "message": f"\"{title}\"의 대화 내용이 없습니다."}
    
    lines = [f"=== 세션: {session_id}, 대화 ID: {conversation_id} ===\n\n"]
    for i, turn in enumerate(history):
        role = "사용자" if turn["role"] == "user" else "법률상담봇"
        lines.append(f"  - [{role}]:\n{turn['content']}\n\n")
    
    return Response(
        content="".join(lines),
        media_type="text/plain; charset=utf-8"
    )

# 대화 삭제
@app.delete("/delete_conversation")
def delete_conversation(session_id: str, conversation_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "해당 세션이 없습니다."}
    
    conversations = session_data[session_id].get("conversations", {})
    if conversation_id not in conversations:
        return {"status": "error", "message": "해당 대화가 없습니다."}
    
    try:
        openai_client.conversations.delete(conversation_id)
    except:
        pass
    
    del conversations[conversation_id]
    
    # active 갱신
    if session_data[session_id]["active_conversation_id"] == conversation_id:
        if len(conversations) > 0:
            # 남은 대화 중 첫 번째를 active로 설정
            new_active = next(iter(conversations.keys()))
            session_data[session_id]["active_conversation_id"] = new_active
            history = conversations[new_active]["history"]
        else:
            # 비어 있다면 active 제거
            session_data[session_id]["active_conversation_id"] = None
            history = []
    else:
        # active 아닌 것 지울 경우 기존 active 유지
        active = session_data[session_id]["active_conversation_id"]
        history = conversations[active]["history"] if active else []
    return {"status": "ok", "message": "대화 삭제됨",
            "active_conv_id": session_data[session_id]["active_conversation_id"],
            "history": history}

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

    return {
        "status": "ok",
        "conversations": items
    }


@app.post("/new_conversation")
def new_conversation(session_id: str):
    if session_id not in session_data:
        return {"status": "error", "message": "세션이 없습니다."}

    # 1차 모델(Chat Model): System prompt 주입
    with open("./prompts/0.chat_model_system_prompt.txt", "r", encoding="utf-8") as f:
        system_prompt = f.read()
    conversation = openai_client.conversations.create(
        items=[
            {
                "role": "system",
                "content": system_prompt
            }
        ]
    )

    new_conv_id = conversation.id
    session_data[session_id]["conversations"][new_conv_id] = {
        "title": f"대화 {len(session_data[session_id]['conversations']) + 1}",
        "history": []
    }
    # active_conv로 설정
    session_data[session_id]["active_conversation_id"] = new_conv_id
    print(f"새 대화 생성됨:\tID: {new_conv_id}")

    return {
        "status": "ok",
        "conversation_id": new_conv_id,
        "title": session_data[session_id]["conversations"][new_conv_id]["title"],
        "history": session_data[session_id]["conversations"][new_conv_id]["history"]
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
        "conversation_id": conversation_id,
        "title": session_data[session_id]["conversations"][conversation_id]["title"],
        "history": session_data[session_id]["conversations"][conversation_id]["history"]
    }
