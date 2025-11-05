import modules.build_database as build_database
import modules.preprocess as preprocess

class DBManager:
    def __init__(self):
        self.chromadb_client = None
        self.judgement_collection = None

    def init_db(self, force=[False, False, False]):
        """
        force
        [0]: convert_pdf_to_txt
        [1]: preprocess_raw_text
        [2]: rebuild_database
        """
        preprocess.run(force[0], force[1]) # 데이터 전처리 시작
        
        self.chromadb_client, self.judgement_collection = \
            build_database.build(force[2]) # 데이터베이스 구성
        
        return self.judgement_collection

db_manager = DBManager()
