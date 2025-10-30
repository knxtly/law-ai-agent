import chromadb
from chromadb.utils import embedding_functions
import re

# 데이터베이스 가져오기
def make_database(start_from_scratch: bool = False):
    client = chromadb.PersistentClient(path="./chroma_db") # 영구 저장 클라이언트
    
    if start_from_scratch: # 기존 DB 삭제
        collections = client.list_collections()
        for collection in collections:
            client.delete_collection(name=collection.name)
    
    # TODO: public 판례 DB는 Jina Embedding, private 판례 DB는 HuggingFace Embedding 사용
    # public_jgmt_collection = client.get_or_create_collection(
    #     name="public_judgements",
    #     embedding_function=embedding_functions.JinaEmbeddingFunction(
    #         model_name="jina-embeddings-v3",
    #         api_key=JINA_API_KEY,
    #         late_chunking=True,
    #         task="retrieval.passage"
    #     ))
    
    print("Building public and private judgement databases...")
    # public 판례 DB build
    public_jud_collection = client.get_or_create_collection(
        name="public_judgements",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )
    )
    # private 판례 DB build
    private_jud_collection = client.get_or_create_collection(
        name="private_judgements",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )
    )
    
    return public_jud_collection, private_jud_collection


# === 유틸: 하나의 Chunk에서 정보 파싱 ===
def parse_chunk(chunk: str):
    """
    #### Chunk N
    제목 (여러 줄 가능)
    (판례번호)
    <...>   → 1번째: 쟁점
    <...>   → 2번째: 판결요지
    <...>   → 3번째: 선정이유
    """
    lines = [line.strip() for line in chunk.strip().split("\n") if line.strip()]
    if not lines:
        return {"제목": "", "판례번호": "", "쟁점": "", "판결요지": "", "선정이유": ""}

    # --- 1. 제목 ---
    title_lines = []
    idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^\(.*\)$", line):  # (헌재 ...)
            idx = i
            break
        title_lines.append(line)
    title = " ".join(title_lines).strip()

    # --- 2. 판례번호 ---
    case_no = lines[idx].strip() if idx < len(lines) else ""

    # --- 3. 본문 나머지 ---
    body = "\n".join(lines[idx + 1 :])

    # 꺽쇠 라인을 기준으로 분리 (태그 이름은 무시)
    parts = re.split(r"^<[^>]+>\s*$", body, flags=re.M)
    # ['', 첫 번째 본문, 두 번째 본문, 세 번째 본문, ...]

    # 불필요한 빈 문자열 제거
    parts = [p.strip() for p in parts if p.strip()]

    parsed = {
        "제목": title,
        "판례번호": case_no,
        "쟁점": parts[0] if len(parts) > 0 else "",
        "판결요지": parts[1] if len(parts) > 1 else "",
        "선정이유": parts[2] if len(parts) > 2 else "",
    }
    return parsed
 
        
def run(law_types, n_of_jud, redo: list[bool]):
    """
    redo:
    make_database?
    """

    # === ChromaDB Client & Collection 생성 ===
    public_jud_collection, private_jud_collection = make_database(start_from_scratch=redo[0])
        
    # === DB에 판례 추가 ===
    for i, law in enumerate(law_types):
        with open(f"./preprocess/prep_texts/{law}_prep.txt", "r", encoding="utf-8") as f:
            preprocessed = re.split(r"#### Chunk \d+\n", f.read())[1:]

        cnt = n_of_jud[i]
        intercept = int(cnt * 0.8) + 1
        print(f"{law}: 전체 {cnt} (public {intercept} / private {cnt - intercept})")

        def add_to_collection(chunks, collection, offset):
            docs, metas, ids = [], [], []
            for j, chunk in enumerate(chunks):
                parsed = parse_chunk(chunk)
                if not parsed["쟁점"]:
                    continue
                docs.append(parsed["쟁점"])
                metas.append({
                    "law_type": law,
                    "제목": parsed["제목"],
                    "판례번호": parsed["판례번호"],
                    "판결요지": parsed["판결요지"],
                    "선정이유": parsed["선정이유"]
                })
                ids.append(f"{law}_{offset + j + 1}")
            if docs:
                collection.add(documents=docs, metadatas=metas, ids=ids)
                print(f"  - {len(docs)}건 추가 완료")

        add_to_collection(preprocessed[:intercept], public_jud_collection, 0)
        add_to_collection(preprocessed[intercept:], private_jud_collection, intercept)