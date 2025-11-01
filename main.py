import json
import os
from dotenv import load_dotenv
from openai import OpenAI

import preprocess
import build_database
import query
from config import preprocess_force, build_db_force
from config import user_query

# 환경변수 로드
load_dotenv(".env")
JINA_API_KEY = os.getenv("JINA_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# 크롤링 해온 데이터 전처리 시작
preprocess.run(preprocess_force)

# 데이터베이스 구성, 벡터화하여 전처리된 데이터 저장
chromadb_client, public_jud_collection, private_jud_collection = build_database.run(build_db_force)

# 사용자 쿼리를 가지고 관련 판례 검색
openai_client = OpenAI(api_key=OPENAI_API_KEY)
query.run(openai_client,
          public_jud_collection,
          private_jud_collection,
          user_query)



# === query_result.json 불러오기 ===
with open("./query_result.json", "r", encoding="utf-8") as f:
    query_result = json.load(f)

public_results = sorted(query_result["public"], key=lambda r: r["유사도거리"])
private_results = sorted(query_result["private"], key=lambda r: r["유사도거리"])


# === context 구성 ===
def build_context(results, source_name):
    lines = []
    for r in results:
        lines.append(
            f"[{source_name}] ({r['법령종류']} / {r['판례번호']}) "
            f"제목: {r['제목']}\n"
            f"유사도거리: {r['유사도거리']:.3f}\n"
            f"선정이유: {r['선정이유']}\n"
            f"내용: {r['내용']}\n"
        )
    return "\n\n".join(lines)

context = build_context(public_results, "Public") + "\n\n" + build_context(private_results, "Private")

# === 답변 생성 ===
def generate_answer(user_query, context):
    prompt = f"""
    사용자의 질문에 대해, 아래 제공된 판례를 근거로 답변해 주세요.
    - 유사한 판례가 없는 경우 '관련 판례를 찾지 못했습니다'라고 말하고, 관련 법령만을 들어 판단하세요.
    - 가능한 한 법조문이나 판례의 문맥을 유지해서 설명하세요.

    [사용자 질문]
    {user_query}

    [검색된 판례]
    {context}
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )
    return response.output_text

answer = generate_answer(user_query=user_query, context=context)

open("./answer.txt", "w", encoding="utf-8").close()
with open("./answer.txt", "w", encoding="utf-8") as f:
    f.write("=== 사용자 질문 ===\n")
    f.write(user_query)
    f.write("\n=== 생성된 답변 ===\n")
    f.write(answer)
