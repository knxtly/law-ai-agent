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
    prompt = f"""당신은 사용자의 질문을 법률 판례 검색에 적합하도록 의미적으로 명료화하는 역할을 맡고 있습니다.

목표:
- 사용자의 질문이 어떤 법률 관계(예: 임대인과 임차인, 채권자와 채무자, 가해자와 피해자)에 관한 것인지 드러나야 합니다.
- 구체적인 상황이나 행위(예: 보증금 반환 거부, 대금 미지급, 폭행 발생 등)를 포함하세요.
- 법적 쟁점이나 분쟁 해결의 관점을 포함한 자연스러운 한 문장으로 표현하세요.
- 단순한 키워드 나열이 아닌, 실제 판례 요지나 법적 문장처럼 자연스럽게 서술하세요.

예시:
"아파트 보증금을 못 돌려받으면 어떻게 해야 하나요?" → "임대차 종료 후 임대인이 보증금 반환을 거부할 때 임차인의 민사·형사상 구제수단"
"교통사고 보험금 안 줘요" → "교통사고 피해자가 보험금 지급을 거절당한 경우의 손해배상 청구"
"지인에게 돈을 빌려줬는데 안 갚아요" → "금전 소비대차에서 채무자가 변제를 거부할 때 채권자의 법적 구제 방법"
"이혼 후 양육비를 지급하지 않을 때 처벌 가능 여부" → "이혼 후 양육비를 지급하지 않는 부모에 대한 형사처벌 가능성"
"직장에서 부당하게 해고당했어요" → "근로자가 부당해고를 당한 경우의 구제 절차와 법적 판단"

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
    prompt = f"""당신은 사용자의 질문을 법령정보공동활용 API 검색에 적합한 핵심 검색어로 변환하는 역할을 맡고 있습니다.

규칙:
- 문장형 표현, 조사, 어미, 구어체를 모두 제거합니다.
- 명사 중심으로 핵심 법률 개념이나 사건 관련 단어만 남깁니다.
- 가능한 한 법령·판례에서 실제로 등장할 법적 용어를 사용하세요.
- 너무 구체적인 사례(예: "친구가 돈 안 줘요")는 일반화된 법률 개념으로 바꿉니다.
- 결과는 짧은 검색어 형태(보통 2~6단어)로 출력하세요.

예시:
"보증금 반환 안 해줄 때 형사고소 가능해요?" → "보증금 반환 형사처벌"
"교통사고 보험금 안 줘요" → "교통사고 보험금 지급 거절"
"지인한테 돈 빌려줬는데 안 갚아요" → "금전채권 변제 불이행"
"회사에서 임금을 안 줘요" → "임금 체불 근로기준법"
"전세사기 당했어요" → "전세사기 보증금 반환"
"이혼 시 양육비 안 주면 어떻게 돼요?" → "양육비 미지급 이행명령"

입력: {query}
출력: """
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