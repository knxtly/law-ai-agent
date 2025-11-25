# 루트디렉토리 추가해서 따로 실행해도 모듈 임포트 가능하게 함
# import os, sys
# PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# if PROJECT_ROOT not in sys.path:
#     sys.path.insert(0, PROJECT_ROOT)

import re
import requests
import chromadb
import chromadb.utils.embedding_functions as ef

DEBUG_MSG_RAG = "    - [RAG]"
DEBUG_MSG_API = "    - [API]"


def build_context_block(search_result, source_signal):
    context_blocks = []
    for i, (doc, meta, dist) in enumerate(
        zip(
            search_result['documents'][0],
            search_result['metadatas'][0],
            search_result['distances'][0]
        ),
        start=1
    ):
        block = (
            f"## 판례 {source_signal}{i}\n"
            f"- 판례번호: {meta.get('판례번호', '없음')}\n"
            f"- 법령종류: {meta.get('law_type', '없음')}\n"
            f"- 제목: {meta.get('제목', '없음')}\n"
            f"- 유사도거리: {dist}\n"
            f"- 선정이유: {meta.get('선정이유', '없음')}\n\n"
            f"### 내용\n{doc}\n"
        )
        context_blocks.append(block)
    return context_blocks


def search_query(ef, query_for_rag: str , query_for_api: str, TOP_N: int):
    db_client = chromadb.PersistentClient(path="./data/chroma_db")
    jgmt_collection = db_client.get_collection("rag_prec_collection")
    try:
        db_client.delete_collection("api_prec_collection")
    except:
        pass
    api_collection = db_client.create_collection(
        name="api_prec_collection",
        embedding_function=ef
    )
    
    # === RAG 판례 검색 ===
    print(DEBUG_MSG_RAG, "검색 중...")
    rag_result = jgmt_collection.query(
        query_texts=query_for_rag,
        n_results=TOP_N,
        include=["documents", "metadatas", "distances"]
    )

    # === 법령정보 공동활용 API 판례 검색===
    """
    활용가이드: https://open.law.go.kr/LSO/openApi/guideList.do
    목록조회(예): https://www.law.go.kr/DRF/lawSearch.do?OC=knxtly1596&target=prec&type=JSON&datSrcNm=대법원
    상세조회(예): https://www.law.go.kr/DRF/lawService.do?OC=knxtly1596&target=prec&ID=228531&type=JSON
    """
    BASE_URL = "https://www.law.go.kr"
    
    print(DEBUG_MSG_API, "API 요청 중...")
    prec_list = requests.get(
        BASE_URL + "/DRF/lawSearch.do",
        params={
            "OC": "knxtly1596",
            "target": "prec",
            "type": "JSON",
            "search": 2, # 검색범위 (기본 : 1 판례명) 2 : 본문검색
            "query": query_for_api,
            "display": 40
        }
    ).json().get("PrecSearch", {}).get("prec")
    
    # prec_list는 항상 리스트 (결과가 0개, 1개일 때 예외처리)
    if not prec_list:
        prec_list = []
    if isinstance(prec_list, dict):
        prec_list = [prec_list]
    
    # 목록 검색의 결과 하나씩 본문조회해서 저장
    print(DEBUG_MSG_API, "각 판례 조회 & 파싱 중...")
    ids = []
    metadatas = []
    documents = []
    CONTENT_TARGET_LEN = 1500 # 임베딩 문장 목표 길이
    CONTENT_MIN_LEN = 100 # 임베딩 문장 최소 길이
    for i, item in enumerate(prec_list):
        detail = requests.get(BASE_URL + item["판례상세링크"].replace("HTML", "JSON")).json()

        if "PrecService" not in detail:
            continue
        
        svc = detail["PrecService"]

        # === id 구성 ===
        ids.append(f"{i}_{svc.get('사건번호', '')}")
        
        # === metadata 구성 ===
        metadatas.append({
            "법령종류": svc.get("사건종류명", ""),
            "제목": svc.get("사건명", ""),
            "판례번호": "({} {} {} {} {})".format(
                svc.get("법원명", ""),
                svc.get("선고일자", ""),
                svc.get("선고", ""),
                svc.get("사건번호", ""),
                svc.get("판결유형", "")
            ),
        })
        
        # === document 구성 ===
        판시사항 = svc.get("판시사항", "")
        판결요지 = svc.get("판결요지", "")
        판례내용 = svc.get("판례내용", "")
        # 1. 임베딩할 문장 구성
        content = f"판시사항: {판시사항}\n판결요지: {판결요지}"
        # 2. ". ? !" 기준 판례내용 분리
        sentences = re.split(r"(?<=[.!?])\s+", 판례내용)
        # 3. 문장 단위로 부족한 길이 채우기
        for s in sentences:
            if len(content) >= CONTENT_TARGET_LEN:
                break
            s_strip = s.strip()
            if not s_strip:
                continue
            content += "\n" + s_strip
        # 4. 최소 길이 확보 fallback
        if len(content) < CONTENT_MIN_LEN:
            fallback = (판시사항 or "") + "\n" + (판결요지 or "") + "\n" + (판례내용 or "")
            content = fallback[:CONTENT_TARGET_LEN]
        documents.append(content)

    if ids and metadatas and documents:
        print(DEBUG_MSG_API, "각 판례 embedding...")
        api_collection.add(documents=documents, metadatas=metadatas, ids=ids)
    else:
        print(DEBUG_MSG_API, "추가할 문서가 없습니다. api_collection.add 호출 생략")

    # === API 판례 검색 ===
    print(DEBUG_MSG_API, "검색 중...")
    api_result = api_collection.query(
        query_texts=query_for_rag,
        n_results=TOP_N,
        include=["documents", "metadatas", "distances"]
    )
    
    
    # === LLM [RAG] 컨텍스트 구축 ===
    print(DEBUG_MSG_RAG, "Context 구성 중...")
    context_rag = "\n".join(build_context_block(rag_result, "R"))
    with open("./results/context_rag.txt", "w", encoding="utf-8") as f:
        f.write(context_rag)
    print(DEBUG_MSG_RAG, f"Context 구성 완료 (saved into \"./results/\": {context_rag[:8]}...)")
    # === LLM [API] 컨텍스트 구축 ===
    print(DEBUG_MSG_API, "Context 구성 중...")
    context_api = "\n".join(build_context_block(api_result, "A"))
    with open("./results/context_api.txt", "w", encoding="utf-8") as f:
        f.write(context_api)
    print(DEBUG_MSG_API, f"Context 구성 완료 (saved into \"./results/\": {context_api[:8]}...)")

    return context_rag, context_api

if __name__ == "__main__":
    pass