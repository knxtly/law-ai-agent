import chromadb
from chromadb.utils import embedding_functions
import re

from modules.config import n_of_jud, law_types

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


# === collection에 임베딩 저장 ===
def add_to_collection(law, chunks, collection):
    docs, metas, ids = [], [], []
    for i, chunk in enumerate(chunks):
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
        ids.append(f"{law}_{i + 1}")
    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)
    return len(docs)


# === 데이터베이스 처음부터 구성 ===
def rebuild_db(judgement_collection, law_types):
    # 데이터 삭제
    for law in law_types:
        judgement_collection.delete(where={"law_type":law})
    
    # 판례 다시 추가
    for i, law in enumerate(law_types):
        with open(f"./data/preprocessed_texts/{law}_판례_prep.txt", "r", encoding="utf-8") as f:
            chunks = re.split(r"#### Chunk \d+\n", f.read())[1:]
        if len(chunks) != n_of_jud[i]:
            print(f" [Warning] {law}: 전처리 중 chunk 개수와 판례개수가 맞지 않음: {chunks} / {n_of_jud[i]}")
        
        num_of_added_judgement = add_to_collection(law, chunks, judgement_collection)
        print(f"{law}: {num_of_added_judgement} / {len(chunks)} saved.")
    

def build(force: bool):
    """
    force:
    init_db?
    """
    # === ChromaDB Client & Collection 생성 ===
    client = chromadb.PersistentClient(path="./data/chroma_db") # 영구 저장 클라이언트
    judgement_collection = client.get_or_create_collection(
        name="judgement_collection",
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
            # TODO: Jina Embedding 사용해보기
            # model_name="jina-embeddings-v3", # intfloat/multilingual-e5-small
            # api_key=JINA_API_KEY,
            # late_chunking=True,
            # task="retrieval.passage"
        )
    )
    
    if force:
        rebuild_db(judgement_collection, law_types)
    
    return client, judgement_collection