# 루트디렉토리 추가해서 따로 실행해도 모듈 임포트 가능하게 함
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import requests

from modules.config import TOP_N

# 사용자 질문 의미적 명료화
def clarify_query_for_rag(query: str, openai_client):
    prompt = f"""
    사용자의 질문을 법률 검색용으로 명료화된 문장으로 변환해줘.
    단순 키워드가 아니라, 의미기반 검색 시 관련 판례가 잘 검색되도록 자연스러운 한 문장으로 만들어.
    
    예:
    "아파트 보증금을 못 돌려받으면 어떻게 해야 하나요?" -> 
    "임대차 계약 종료 후 임대인이 보증금 반환을 거부할 때 임차인의 민사·형사적 구제절차"

    질문: {query}
    답변:
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    return getattr(response, "output_text", "").strip()

# 사용자 질문 키워드적 명료화
def clarify_query_for_api(query:str, openai_client):
    prompt = f"""
    사용자 질문을 판례검색 키워드로 변환해줘.
    - 불필요한 조사나 문장형 어미 제거.
    - 명사 중심으로 핵심 법률 키워드만 추출.
    예: 
    "보증금 반환 안 해줄 때 형사고소 가능해요?" → "보증금 반환 형사처벌"
    "교통사고 보험금 안 줘요" → "교통사고 보험금 지급 거절"
    "아파트 보증금을 못 돌려받으면 어떻게 해야 하나요?" → "아파트 보증금 반환"

    입력: {query}
    출력:
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    return getattr(response, "output_text", "").strip()


# 관련판례 검색 결과 -> json
def structure_results_rag(result):
    structured = []
    for doc, meta, dist in zip(result['documents'][0], result['metadatas'][0], result['distances'][0]):
        structured.append({
            "유사도거리": dist,
            "내용": doc,
            "법령종류": meta.get("law_type", ""),
            "제목": meta.get("제목", ""),
            "판례번호": meta.get("판례번호", ""),
            "선정이유": meta.get("선정이유", "")
        })
    return structured

# 관련판례 검색 결과 -> json
def structure_results_api(precs):
    """
    https://www.law.go.kr/DRF/lawService.do?OC=knxtly1596&target=prec&ID=228531&type=JSON
    """
    structured = []

    for prec in precs:
        # 판례가 없을 경우 건너뜀 => {"Law": "일치하는 판례가 없습니다.  판례명을 확인하여 주십시오."}
        if "PrecService" not in prec:
            continue
        prec_detail = prec["PrecService"]
        
        # 내용 = 판시사항 + 판결요지 결합
        content = f"""
        {prec_detail.get("판시사항", "").strip() or ""}
        {prec_detail.get("판결요지", "").strip() or ""}
        """.strip()
        
        # TODO: 판시사항과 판결요지 둘 다 없을 때 판결내용?

        # 너무 길면 잘라내기
        max_len = 8000
        if len(content) > max_len:
            content = content[:max_len] + "..."

        structured.append({
            "유사도거리": None,
            "내용": content,
            "법령종류": prec_detail.get("사건종류명", ""),
            "제목": prec_detail.get("사건명", ""),
            "판례번호": "({} {} {} {} {})".format(
                prec_detail.get("법원명", ""),
                prec_detail.get("선고일자", ""),
                prec_detail.get("선고", ""),
                prec_detail.get("사건번호", ""),
                prec_detail.get("판결유형", "")
            ),
            "선정이유": None
        })

    return structured


def search_query(openai_client, judgement_collection, user_query, use_rag, clarify_q=True):
    clarified_query_for_rag = user_query
    clarified_query_for_api = user_query
    if clarify_q:
        clarified_query_for_rag = clarify_query_for_rag(user_query, openai_client)
        clarified_query_for_api = clarify_query_for_api(user_query, openai_client)
    print(f"clarified_query_for_rag: {clarified_query_for_rag}\nclarified_query_for_api: {clarified_query_for_api}")
    context_rag, context_api = None, None

    # === RAG 판례 검색 ===
    if use_rag:
        search_result_rag = judgement_collection.query(
            query_texts=clarified_query_for_rag,
            n_results=TOP_N,
            include=["documents", "metadatas", "distances"]
        )
        # context 생성
        context_rag = {
            "query": user_query,
            "expanded_query": clarified_query_for_rag,
            "results": structure_results_rag(search_result_rag)
        }
        # 디버깅: JSON 파일로 저장
        with open("./results/context_rag.json", "w", encoding="utf-8") as f:
            json.dump(context_rag, f, ensure_ascii=False, indent=2)
        print("RAG 검색 완료")
    
    # === 법령정보 공동활용 API ===
    """
    활용가이드: https://open.law.go.kr/LSO/openApi/guideList.do
    목록조회(예): https://www.law.go.kr/DRF/lawSearch.do?OC=knxtly1596&target=prec&type=JSON&datSrcNm=대법원
    상세조회(예): https://www.law.go.kr/DRF/lawService.do?OC=knxtly1596&target=prec&ID=228531&type=JSON
    """
    BASE_URL = "https://www.law.go.kr"
    params = {
        "OC": "knxtly1596",
        "target": "prec",
        "type": "JSON",
        "search": 2, # 본문검색
        "query": clarified_query_for_api,
        "display": 40
    }
    
    prec_list = requests.get(BASE_URL + "/DRF/lawSearch.do", params=params).json()\
        .get("PrecSearch", {}).get("prec")
    if not prec_list:
        prec_list = []

    if isinstance(prec_list, dict):
        prec_list = [prec_list]  # prec_list는 항상 리스트
    
    precs = []
    for item in prec_list:
        prec_detail = requests.get(BASE_URL + item["판례상세링크"].replace("HTML", "JSON")).json()
        precs.append(prec_detail)
    # 구조화
    context_api = {
        "query": user_query,
        "expanded_query": clarified_query_for_api,
        "results": structure_results_api(precs)
    }

    # context 전체 저장
    with open("./results/context_api.json", "w", encoding="utf-8") as f:
        json.dump(context_api, f, ensure_ascii=False, indent=2)
    print("법령정보 공동활용 API 검색 완료")
    
    return context_rag, context_api

if __name__ == "__main__":
    # TODO: 질의 명료화 모델 ON/OFF비교
    import chromadb
    import chromadb.utils.embedding_functions as embedding_functions
    
    user_query = "아파트 보증금을 못 돌려받으면 형사고소 가능한가요?" # 1개
    user_query = "미성년자가 부모 동의 없이 신용카드로 물건을 샀는데, 나중에 계약을 취소할 수 있나요?"
    user_query = "집주인이 계약 종료 후 보증금을 안 돌려줄 때 법적 대응 방법은?" # 0개
    user_query = "임대차 계약에서 연체된 차임을 상계"
    client = chromadb.PersistentClient(path="./data/chroma_db") # 영구 저장 클라이언트
    judgement_collection = client.get_collection(
        name="judgement_collection",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="jhgan/ko-sroberta-multitask"
        )
    )
    search_query(None, judgement_collection, user_query, use_rag=True, clarify_q=False)