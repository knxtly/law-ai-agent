# 루트디렉토리 추가해서 따로 실행해도 모듈 임포트 가능하게 함
import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import chromadb
import chromadb.utils.embedding_functions as ef
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
def add_to_collection(law, chunks, collection, do_parse=True):
    docs, metas, ids = [], [], []
    if do_parse:
        for i, chunk in enumerate(chunks):
            parsed = parse_chunk(chunk)
            if not parsed["내용"]:
                continue
            docs.append(parsed["내용"])
            metas.append({
                "법령종류": law,
                "제목": parsed["제목"],
                "판례번호": parsed["판례번호"],
                "선정이유": parsed["선정이유"]
            })
            ids.append(f"{law}_{i + 1}")
    else:
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({"법령종류": law})
            ids.append(f"{law}_{i + 1}")
    if docs:
        collection.add(documents=docs, metadatas=metas, ids=ids)
    return len(docs)


# === 데이터베이스 처음부터 구성 ===
def restart_db(col_name: str, embedding_function, db_path):
    db_client = chromadb.PersistentClient(path=db_path) # 영구 저장 클라이언트
    try:
        print(" [build_database.py] 모든 컬렉션 삭제")
        for c in db_client.list_collections():
            db_client.delete_collection(c.name)
    except:
        pass
    jdmt_col = db_client.create_collection(
        name=col_name,
        embedding_function=embedding_function
    )
    
    # 판례 다시 추가
    for i, law in enumerate(law_types):
        with open(f"./data/preprocessed_texts/{law}_판례_prep.txt", "r", encoding="utf-8") as f:
            chunks = re.split(r"#### Chunk \d+\n", f.read())[1:]
        if len(chunks) != n_of_jud[i]:
            print(f" [build_database.py] {law}: 전처리 중 chunk 개수와 판례개수가 맞지 않음: {chunks} / {n_of_jud[i]}")
        
        jdmt_cnt = add_to_collection(law, chunks, jdmt_col)
        print(f" [build_database.py] {law}: {jdmt_cnt} / {len(chunks)} saved.")


if __name__ == "__main__":
    pass