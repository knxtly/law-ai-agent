from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI
import os

from modules import build_database, query
from modules.db_manager import db_manager

app = FastAPI()

# 환경변수 로드
load_dotenv(".env")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai_client = OpenAI(api_key=OPENAI_API_KEY)
chromadb_client, judgement_collection = build_database.build(False)

# 세션별 대화 히스토리 및 conversation_id 저장
session_data = {}  # { session_id: { "conversation_id": str, "history": [ ... ] } }

# POST 요청 데이터 모델
class UserQuery(BaseModel):
    session_id: str
    query: str

# DB 업데이트
@app.post("/update_db")
def update_database():
    db_manager.init_db([False, False, True])
    return {"status": "ok", "message": "DB 업데이트 완료"}

# 사용자 쿼리를 가지고 관련 판례 검색
@app.post("/ask")
def ask_question(data: UserQuery):
    user_query = data.query
    session_id = data.session_id
    
    print(f"[{session_id}] 유저 질문: {user_query}")
    
    if session_id not in session_data:
        session_data[session_id] = {"conversation_id": None, "history": []}
    
    # RAG포함 검색 수행 (전문가: True, 일반 사용자: False)
    search_result_rag, search_result_api = query.search_query(openai_client, judgement_collection, user_query, True)
    
    print("검색 결과로부터 context 구성 중...")
    def build_context(search_result):
        if search_result is None or "results" not in search_result:
            return None
        results = sorted(search_result["results"], key=lambda x: (x["유사도거리"] is None, x["유사도거리"]))

        lines = []
        for r in results:
            dist = f"{r['유사도거리']:.3f}" if r["유사도거리"] is not None else "N/A"
            lines.append(
                f"[{r['법령종류']} / {r['판례번호']}] 제목: {r['제목']}\n"
                f"유사도거리: {dist}\n"
                f"선정이유: {r['선정이유']}\n"
                f"내용: {r['내용']}\n"
            )
        return "\n\n".join(lines) 
    
    context_rag = build_context(search_result_rag)
    context_api = build_context(search_result_api)
    
    print("context로부터 답변 생성 중...")
    def generate_answer(user_query, context_rag, context_api):
        max_len = 8000
        if context_rag and len(context_rag) > max_len:
            context_rag = context_rag[:max_len] + "..."
        if context_api and len(context_api) > max_len:
            context_api = context_api[:max_len] + "..."

        prompt = f"""        
        당신은 전문 법률상담 챗봇입니다.
        사용자의 질문에 대해 아래 판례 및 법령을 근거로 구체적이고 신뢰성 있게 답변하세요.
        - 유사한 판례가 없는 경우: "관련 판례를 찾지 못했습니다"라고 말하고 법조문 중심으로 설명하세요.
        - 가능한 한 법조문이나 판례의 문맥을 유지해서 설명하세요.

        [사용자 질문]
        {user_query}

        [검색된 내부 판례]
        {context_rag}
        
        [검색된 공개 판례]
        {context_api}
        """
        
        # 세션별 conversation 이어가기
        conversation_id = session_data[session_id]["conversation_id"]
        
        response = openai_client.responses.create(
            model="gpt-5-mini",
            input=prompt,
            conversation=conversation_id
        )
        
        # 새 conversation이면 저장
        if session_data[session_id]["conversation_id"] is None:
            session_data[session_id]["conversation_id"] = response.conversation
        
        return getattr(response, "output_text", "").strip()
    answer = generate_answer(user_query, context_rag, context_api)

    print("대화 저장 중...")
    session_data[session_id]["history"].append({
        "user": user_query,
        "assistant": answer
    })
    
    print("로컬 저장 중...")
    def save_result():
        with open("./conversation.txt", "w", encoding="utf-8") as f:
            f.write(f"=== 세션: {session_id} ===\n")
            for i, turn in enumerate(session_data[session_id]["history"]):
                f.write(f"### turn {i} ###\n")
                f.write(f"  - 사용자:\n{turn['user']}\n\n")
                f.write(f"  - 법률상담봇:\n{turn['assistant']}\n")
    save_result()
    
    return {"answer": answer}

# 다운로드 요청 시 파일 생성
@app.get("/download_conversation/{session_id}")
def download_conversation(session_id: str):
    if session_id not in session_data:
        return {"error": "해당 세션의 대화가 없습니다."}
    
    path = "./conversation.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"=== 세션: {session_id} ===\n")
        for i, turn in enumerate(session_data[session_id]["history"]):
            f.write(f"### turn {i} ###\n")
            f.write(f"  - 사용자:\n{turn['user']}\n\n")
            f.write(f"  - 법률상담봇:\n{turn['assistant']}\n")
    
    return {"status": "ok", "message": "대화 저장 완료", "path": path}

