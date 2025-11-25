import modules.build_database as build_database
import modules.preprocess as preprocess
import chromadb.utils.embedding_functions as ef

class DBManager:
    def __init__(
        self,
        db_path="./data/chroma_db",
        jdmt_col_name="rag_prec_collection"
    ):
        self.db_path = db_path
        self.ef = ef.SentenceTransformerEmbeddingFunction(
            model_name="jhgan/ko-sroberta-multitask"
        )
        self.col_name = jdmt_col_name

    def init_db(self, convert_pdf2txt=False, preprocess_text=False, rebuild_db=False):
        # 데이터 전처리
        preprocess.preprocess(convert_pdf2txt, preprocess_text)
        # DB 구성
        if rebuild_db:
            build_database.restart_db(self.col_name, self.ef, self.db_path)

db_manager = DBManager()
