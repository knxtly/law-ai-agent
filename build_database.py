import chromadb
from chromadb.utils import embedding_functions
import re

from config import n_of_jud, law_types

# === 하나의 Chunk에서 정보 파싱 ===
def parse_chunk(chunk: str):
    """
    #### Chunk N
    제목 (여러 줄 가능)
    (판례번호) (1줄)
    <쟁점>
    ...
    <판결요지>
    ...
    <판례선정이유>
    ...
    """
    lines = [line.strip() for line in chunk.strip().split("\n") if line.strip()]
    if not lines:
        return {"제목": "", "판례번호": "", "내용": "", "선정이유": ""}

    # 1. 제목 추출
    title_lines = []
    idx = 0
    for i, line in enumerate(lines):
        if re.match(r"^\(.*\)$", line):  # (판례번호 ...) 등장
            idx = i
            break
        title_lines.append(line)
    title = " ".join(title_lines).strip()

    # 2. 판례번호
    case_no_lines = []
    for j in range(idx, len(lines)):
        if re.match(r"^<[^>]+>\s*$", lines[j]):  # <태그> 나오면 종료
            break
        case_no_lines.append(lines[j])
    case_no = " ".join(case_no_lines).strip()

    # 3. 나머지 내용
    body = "\n".join(lines[idx + 1 :])

    # 4. 내용에서 꺽쇠(<...>) 기준 분리
    parts = re.split(r"^<[^>]+>\s*$", body, flags=re.M)
    parts = [p.strip() for p in parts if p.strip()]

    # 5. 내용 구성
    main_text = ""
    selection_reason = ""

    if len(parts) >= 2: # (쟁점 + 판결요지)를 내용으로
        main_text = "\n".join(parts[:2]).strip()
    elif len(parts) == 1:
        main_text = parts[0].strip()

    if len(parts) >= 3:
        selection_reason = parts[2].strip()

    return {
        "제목": title,
        "판례번호": case_no,
        "내용": main_text,
        "선정이유": selection_reason
    }


def add_to_collection(law, chunks, collection, offset):
    docs, metas, ids = [], [], []
    for j, chunk in enumerate(chunks):
        parsed = parse_chunk(chunk)
        if not parsed["내용"]:
            continue
        docs.append(parsed["내용"])
        metas.append({
            "law_type": law,
            "제목": parsed["제목"],
            "판례번호": parsed["판례번호"],
            "선정이유": parsed["선정이유"]
        })
        ids.append(f"{law}_{offset + j + 1}")
    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)
        print(f"  - {len(docs)}건 추가 완료")


# 데이터베이스 새로 구성
def rebuild_db(public_jud_collection,
               private_jud_collection,
               law_types):
    # 데이터 삭제
    for law in law_types:
        public_jud_collection.delete(where={"law_type":law})
        private_jud_collection.delete(where={"law_type":law})
    
    # 판례 다시 추가
    for law in law_types:
        with open(f"./preprocess/prep_texts/{law}_prep.txt", "r", encoding="utf-8") as f:
            prep_chunks = re.split(r"#### Chunk \d+\n", f.read())[1:]
        if len(prep_chunks) != n_of_jud:
            print(f" [Warning] {law}: chunk 개수와 판례개수가 맞지 않음")
            
        intercept = int(len(prep_chunks) * 0.8) + 1
        print(f"{law} added: 전체 {len(prep_chunks)} (public {intercept} / private {len(prep_chunks) - intercept})")
        add_to_collection(law, prep_chunks[:intercept], public_jud_collection, 0)
        add_to_collection(law, prep_chunks[intercept:], private_jud_collection, intercept)
    

def run(force: list[bool]):
    """
    force:
    init_db?
    """
    # === ChromaDB Client & Collection 생성 ===
    client = chromadb.PersistentClient(path="./chroma_db") # 영구 저장 클라이언트
    public_jud_collection = client.get_or_create_collection(
        name="public_judgements",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
            # TODO: public 판례 DB는 Jina Embedding, private 판례 DB는 HuggingFace Embedding 사용
            # model_name="jina-embeddings-v3", # intfloat/multilingual-e5-small
            # api_key=JINA_API_KEY,
            # late_chunking=True,
            # task="retrieval.passage"
        )
    )
    private_jud_collection = client.get_or_create_collection(
        name="private_judgements",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )
    )
    
    if force[0]:
        rebuild_db(public_jud_collection,
            private_jud_collection,
            law_types)
    
    return client, public_jud_collection, private_jud_collection