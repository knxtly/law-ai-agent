import os
from dotenv import load_dotenv
import chromadb

import build_database
import preprocess


law_types = ["민법", "민사소송법", "상법", "헌법", "형법", "형사소송법"]
n_of_jud = [930, 454, 516, 331, 498, 416-1]  # 각 법률별 판례 수
jud_start_page = [9, 29, 45, 3, 27, 33]  # 각 법률별 본문 시작 페이지 번호
jud_end_page = [635, 339, 548, 312, 454, 401]  # 각 법률별 본문 종료 페이지 번호

preprocess.run(
    law_types,
    n_of_jud,
    jud_start_page,
    jud_end_page,
    redo=[True, True])
build_database.run(
    law_types,
    n_of_jud,
    [True])


# === 환경변수 로드 ===
load_dotenv(".env")
JINA_API_KEY = os.getenv("JINA_API_KEY")
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
if not JINA_API_KEY:
    raise ValueError("Can't find JINA_API_KEY")
if not HUGGINGFACE_API_KEY:
    raise ValueError("Can't find HUGGINGFACE_API_KEY")

# DB 열기
client = chromadb.PersistentClient(path="./chroma_db")
public_jud_collection = client.get_collection(name="public_judgements")
private_jud_collection = client.get_collection(name="private_judgements")

query_texts = ["중고거래 판매자가 입금 이후에 물건을 주지 않고 사라졌다면 판매자는 어떤 처벌을 받게 될까?"]
query_result_pub = public_jud_collection.query(
    query_texts=query_texts,
    n_results=3,
    include=["documents", "metadatas", "distances"]
)
query_result_prv = private_jud_collection.query(
    query_texts=query_texts,
    n_results=3,
    include=["documents", "metadatas", "distances"]
)

# public 결과 출력
result = []
result.append("=== Public 판례 검색 결과 ===")
for i, (doc, meta, dist) in enumerate(zip(
    query_result_pub['documents'][0],
    query_result_pub['metadatas'][0],
    query_result_pub['distances'][0]
)):    
    result.append(f"결과 {i+1}")
    result.append(f"법령 종류: {meta.get('law_type')}")
    result.append(f"제목: {meta.get('제목')}")
    result.append(f"판례번호: {meta.get('판례번호')}")
    result.append(f"판결요지: {meta.get('판결요지')}")
    result.append(f"선정이유: {meta.get('선정이유')}")
    result.append(f"유사도 거리: {dist}")
    result.append(f"본문 일부(쟁점): {doc}")
    result.append("-"*80)

    
# private 결과 출력
result.append("\n=== Private 판례 검색 결과 ===")
for i, (doc, meta, dist) in enumerate(zip(
    query_result_prv['documents'][0],
    query_result_prv['metadatas'][0],
    query_result_prv['distances'][0]
)):
    result.append(f"결과 {i+1}")
    result.append(f"법령 종류: {meta.get('law_type')}")
    result.append(f"제목: {meta.get('제목')}")
    result.append(f"판례번호: {meta.get('판례번호')}")
    result.append(f"판결요지: {meta.get('판결요지')}")
    result.append(f"선정이유: {meta.get('선정이유')}")
    result.append(f"유사도 거리: {dist}")
    result.append(f"본문 일부(쟁점): {doc}")
    result.append("-"*80)


with open("./query_result.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(result))
    f.truncate()