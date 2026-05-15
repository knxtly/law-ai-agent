# Law AI Agent ⚖️

법률 문서를 분석하고 질문에 답변하는 AI 에이전트 프로젝트입니다.

## 시작하기 전에 (초기 세팅)

프로젝트를 처음 다운로드(git pull)받았거나, 환경을 새로 설정해야 할 때 다음 단계를 순서대로 진행하세요.

### 1. 가상환경 생성 및 라이브러리 설치
터미널(**PowerShell**)을 열고 아래 명령어를 한 줄씩 입력하세요. 
(가상환경을 활성화해야 시스템 환경이 더러워지는 것을 방지할 수 있습니다.)

```powershell
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화 (왼쪽에 (.venv)가 떠야 합니다)
.\.venv\Scripts\activate

# 필수 라이브러리 설치
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. 환경 변수 설정
프로젝트 루트 디렉토리에 .env 파일을 생성하고 본인의 OpenAI API 키를 입력합니다.
`OPENAI_API_KEY=sk-your-api-key-here...`

## 서버 실행 방법
반드시 가상환경이 활성화된 상태((.venv))에서 실행하세요.

### Back-end (FastAPI)
새 터미널을 열고 다음을 입력합니다. (포트: 8000)
```PowerShell
uvicorn back:app --reload
```
### Front-end (Streamlit)
또 다른 터미널을 열고 다음을 입력합니다. (자동으로 브라우저가 열립니다. 포트: 8501)
```PowerShell
streamlit run front.py
```

## 사용 순서
1. 서버 부팅: 위 명령어를 이용해 백엔드와 프론트엔드를 모두 실행합니다.

2. DB 업데이트: 웹 화면에서 'DB 업데이트' 버튼을 클릭하여 벡터 DB(Vector Database)를 구축합니다. (첫 실행 시 필수)

3. 질문 시작: DB 구축이 완료되면 하단 채팅창을 통해 법률 상담을 시작하세요.
