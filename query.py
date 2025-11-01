import json

from config import TOP_N

# 사용자 질문을 api로 명료화
def clarify_user_query(query: str, openai_client):
    prompt = f"""
    사용자의 질문을 법률 검색용으로 명료화된 문장으로 변환해줘.
    단순 키워드가 아니라, 검색 시 관련 판례가 잘 걸리도록 자연스러운 문장으로 만들어.
    
    예:
    "아파트 보증금을 못 돌려받으면 형사고소 가능한가요?" -> 
    "임대차 계약에서 보증금 반환 지연 시 형사처벌 사례"

    질문: "{query}"
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    return response.output_text.strip()


def keyword_user_query(query:str, openai_client):
    prompt = f"""
    다음 사용자 질문에서 법령정보센터 검색용 키워드를 추출해줘.
    - 핵심 명사, 사건 유형, 법률 관련 용어 위주
    - 불필요한 문장과 일반 단어(있다, 되다 등)는 제외
    - 결과는 콤마(,)로 구분된 문자열로 출력
    
    예:
    "아파트 보증금을 못 돌려받으면 형사고소 가능한가요?" -> 
    "임대차, 보증금, 반환, 형사처벌, 사례"

    질문: "{query}"
    """
    response = openai_client.responses.create(
        model="gpt-5-mini",
        input=prompt
    )
    keywords = response.output_text.strip()
    # 필요하면 리스트로 변환 가능
    return [k.strip() for k in keywords.split(',')]


# 관련판례 검색 결과 -> json 으로 만드는 함수
def structure_results(result):
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


def run(openai_client,
        public_jud_collection,
        private_jud_collection,
        user_query):

    # 질의 의미적으로 명료화 (내부 chromaDB에서 검색하는 용도) TODO: ON/OFF비교
    clarified_query = clarify_user_query(user_query, openai_client)

    # public 판례 검색
    result_pub = public_jud_collection.query(
        query_texts=clarified_query,
        n_results=TOP_N,
        include=["documents", "metadatas", "distances"]
    )
    # private 판례 검색
    result_prv = private_jud_collection.query(
        query_texts=clarified_query,
        n_results=TOP_N,
        include=["documents", "metadatas", "distances"]
    )
    
    
    
    # 중요한 키워드 추출 (법령정보센터 Open API에 이용) TODO
    keyword_query = keyword_user_query(user_query, openai_client)
    print(f"명료화된 쿼리: {clarified_query}\n키워드추출된 쿼리: {keyword_query}")
    
    ###### TODO: 법령정보센터 API로 검색 결과 처리 ######
    # 음.. 아예 chromadb를 내부 rag로 하고 외부 판례는 법령정보센터 api로 할까?
    # 이게 잘 동작한다면 말이지
    
    query_result = {
        "query": user_query,
        "expanded_query": clarified_query,
        "public": structure_results(result_pub),
        "private": structure_results(result_prv)
    }

    # JSON 파일로 저장
    output_path = "./query_result.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(query_result, f, ensure_ascii=False, indent=2)