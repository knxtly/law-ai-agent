import json
import requests

from modules.config import TOP_N

# 사용자 질문 의미적 명료화 (내부RAG에 이용)
def clarify_query_for_rag(query: str, openai_client):
    prompt = f"""
    사용자의 질문을 법률 검색용으로 명료화된 문장으로 변환해줘.
    단순 키워드가 아니라, 의미기반 검색 시 관련 판례가 잘 검색되도록 자연스러운 한 문장으로 만들어.
    
    예:
    "아파트 보증금을 못 돌려받으면 형사고소 가능한가요?" -> 
    "임대차 계약에서 보증금 반환 지연 시 형사처벌 사례"

    질문: {query}
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    return getattr(response, "output_text", "").strip()


# 사용자 질문 키워드적 명료화 (Open API에 이용)
def clarify_query_for_api(query:str, openai_client):
    prompt = f"""
    사용자 질문을 판례검색 키워드로 변환해줘.
    - 불필요한 조사나 문장형 어미 제거.
    - 명사 중심으로 핵심 법률 키워드만 남겨.
    예: 
    "보증금 반환 안 해줄 때 형사고소 가능해요?" → "보증금 반환 형사처벌"
    "교통사고 보험금 안 줘요" → "교통사고 보험금 지급 거절"

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
def structure_results_api(results):
    structured = []

    for item in results:
        # 판례가 없을 경우 건너뜀
        if "Law" in item and "일치하는 판례가 없습니다" in item["Law"]:
            continue
        if "PrecService" not in item:
            continue

        prec = item["PrecService"]
        
        # 판시사항 + 판결요지 결합
        판시사항 = prec.get("판시사항", "").strip() or "(판시사항 없음)"
        판결요지 = prec.get("판결요지", "").strip() or "(판결요지 없음)"
        content = f"[쟁점] {판시사항}\n[판결요지] {판결요지}"

        # 너무 길면 잘라내기
        max_len = 4000
        if len(content) > max_len:
            content = content[:max_len] + "..."

        structured.append({
            "유사도거리": None,
            "내용": content,
            "법령종류": prec.get("법령종류", ""),
            "제목": prec.get("사건명", ""),
            "판례번호": f"({prec.get('법원명', '')} {prec.get('선고일자', '')} 선고 {prec.get('사건번호', '')} 판결)",
            "선정이유": None
        })

    return structured


def search_query(openai_client, judgement_collection, user_query, use_rag):

    # 질의 명료화 TODO: ON/OFF비교
    clarified_query_for_rag = clarify_query_for_rag(user_query, openai_client)
    clarified_query_for_api = clarify_query_for_api(user_query, openai_client)
    print(f"clarified_query_for_rag: {clarified_query_for_rag}\nclarified_query_for_api: {clarified_query_for_api}")
    # clarified_query_for_rag = user_query
    # clarified_query_for_api = user_query
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
        output_path = "./context_rag.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(context_rag, f, ensure_ascii=False, indent=2)
    
    
    # === Open API 검색 ===
    BASE_URL = "https://www.law.go.kr"
    params = {
        "OC": "knxtly1596",
        "target": "prec",
        "type": "JSON",
        "search": 2, # 본문검색
        "query": clarified_query_for_api
    }
    try:
        search_list_api = requests.get(BASE_URL + "/DRF/lawSearch.do", params=params).json()
    except Exception as e:
        print(f" [Error] 판례 검색 API 요청 실패: {e}")
        return context_rag, None
    
    # 검색 결과 저장
    with open("./search_list.txt", "w", encoding="utf-8") as f:
        json.dump(search_list_api, f, ensure_ascii=False, indent=2)

    detail_result_api = []
    
    # 기존 상세조회 파일 초기화
    open("./search_detail.txt", "w", encoding="utf-8").close()
    # 판례 상세조회
    prec_items = search_list_api.get("PrecSearch", {}).get("prec", [])
    if not prec_items:
        print(" [Info] 일치하는 판례 없음")
    else:
        for item in search_list_api["PrecSearch"]["prec"]:
            detail_url = BASE_URL + item["판례상세링크"].replace("HTML", "JSON")
            detail_result = requests.get(detail_url)

            try:
                # JSON 파싱 확인
                parsed = detail_result.json()
            except Exception as e:
                print(f" [Warning] JSON 파싱 오류: {detail_url}, {e}")
                continue

            detail_result_api.append(parsed)

            # 디버깅용 파일 저장
            with open("./search_detail.txt", "a", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
                f.write("\n\n")

    
    # 구조화
    context_api = {
        "query": user_query,
        "expanded_query": clarified_query_for_api,
        "results": structure_results_api(detail_result_api)
    }

    # context 전체 저장
    with open("./context_api.json", "w", encoding="utf-8") as f:
        json.dump(context_api, f, ensure_ascii=False, indent=2)
    
    return context_rag, context_api