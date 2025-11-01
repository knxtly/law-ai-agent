import os
import re
from langchain_community.document_loaders import PyPDFLoader

import config

def clean_dir(dir_path):
    for filename in os.listdir(dir_path):
        file_path = os.path.join(dir_path, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)


# === PDF -> TXT 변환 함수 ===
def convert_pdf_to_txt_judgement(law_types: list[str],
                                 start_page: list[int],
                                 end_page: list[int]):
    clean_dir("./preprocess/raw_texts")
    print("Converting PDF to TXT...")
    for i, law in enumerate(law_types):
        source_file = f"./source_data/judgements/{law}_판례.pdf"
        target_file = f"./preprocess/raw_texts/{law}_raw.txt"
        
        # PDF 로드
        if not os.path.exists(source_file):
            print(f"Can't find file: {source_file}")
            continue
        docs = PyPDFLoader(source_file).load()
        
        # 지정된 페이지 범위의 텍스트 추출 및 저장
        raw_text = "\n".join([doc.page_content for doc in docs[start_page[i]-1:end_page[i]]])
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(raw_text)


# === 전처리 함수 ===
def preprocess_raw_text(law_types: list[str],
                        n_of_jud: list[int]):
    clean_dir("./preprocess/prep_texts")
    print("Preprocessing raw texts...")
    for law in law_types:
        source_file = f"./preprocess/raw_texts/{law}_raw.txt"
        target_file = f"./preprocess/prep_texts/{law}_prep.txt"
        
        # 특정 파일 수정 로직
        if law in ["상법", "형사소송법"]:
            """
            "상법_raw": "회사의 심사의무" 바로 위 (3611 line)"127" -> "127."
            "형사소송법_raw": "범인식별절차의 신용성" 바로 위 (6676 line) "217" -> "217.", 344번째 판례는 원래 없음.
            """
            line_to_edit = 3611 if law == "상법" else 6676
            with open(source_file, "r+", encoding="utf-8") as f:
                lines = f.readlines()
                if len(lines) >= line_to_edit:
                    target_line = lines[line_to_edit - 1].rstrip("\n")
                    if not target_line.endswith("."):
                        lines[line_to_edit - 1] = target_line + ".\n"
                        f.seek(0)
                        f.writelines(lines)
                        f.truncate()
        
        # 원본 텍스트 로드
        if not os.path.exists(source_file):
            print(f"{source_file} not found.")
            continue
        with open(source_file, "r", encoding="utf-8") as f:
            raw_text = f.read()
        
        # 불필요 문구 제거
        raw_text = re.sub(r"^\s*$", "", raw_text, flags=re.MULTILINE) # 빈 줄 제거
        raw_text = re.sub(r"변호사시험의 자격시험을 위한.*", "", raw_text) # 불필요 문구 제거
        raw_text = re.sub(r"^\s*\d{1,4}\s*$", "", raw_text, flags=re.MULTILINE) # 페이지 번호 제거
        raw_text = re.sub(r"제\s*\d+\s*편.*", "", raw_text) # 편 제거
        raw_text = re.sub(r"제\s*\d+\s*장.*", "", raw_text) # 장 제거
        raw_text = re.sub(r"제\s*\d+\s*절.*", "", raw_text) # 절 제거
        
        # 불필요 문구 제거(형법관련)
        raw_text = re.sub(r"형법 총론.*", "", raw_text) # 불필요 문구 제거
        raw_text = re.sub(r"^\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+.*$", "", raw_text, flags=re.MULTILINE) # 로마 숫자로 시작하는 줄 제거
        
        # 공백 정리
        raw_text = raw_text.replace("\r\n", "\n") # CRLF -> LF
        raw_text = re.sub(r"\n{2,}", "\n", raw_text) # 여러 개 연속된 개행 -> 하나 개행
        raw_text = re.sub(r"[ \t]+", " ", raw_text) # 여러 공백 -> 하나 공백
        
        # 판례 단위로 분리
        chunks = re.split(r"\n\d+\.\s*\n", raw_text)[1:] # "숫자. " 패턴 기준으로 분리, 앞부분 제거
        
        # 분리된 각 판례에 번호 매기며 저장
        open(target_file, "w", encoding="utf-8").close() # 파일 초기화
        with open(target_file, "w", encoding="utf-8") as f:
            for i, chunk in enumerate(chunks):
                f.write(f"#### Chunk {i+1}\n")
                f.write(chunk.strip() + "\n")

        # 저장 후, 개수 확인
        if len(chunks) != n_of_jud[law_types.index(law)]:
            print(f"[Warning] {law:<10} 전처리 과정 중, (청크개수={len(chunks)}/판례개수={n_of_jud[law_types.index(law)]}) -> 불일치")


def run(force: list[bool]):
    """
    force ...
    convert_pdf_to_txt_judgement?
    preprocess_raw_text?
    """
    if force[0]:
        convert_pdf_to_txt_judgement(config.law_types,
                                     config.jud_start_page,
                                     config.jud_end_page)
    if force[1]:
        preprocess_raw_text(config.law_types, config.n_of_jud)
