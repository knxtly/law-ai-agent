import streamlit as st
import requests
import uuid

# 페이지 설정
st.set_page_config(page_title="RAG기반 AI법률상담챗봇", layout="centered")
st.title("RAG기반 AI 법률상담 챗봇")

# === 고유 세션 ID 생성 (대화 연결용) ===
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []  # 초기화
    st.session_state.initialized = True

# === 사이드바: DB 업데이트 ===
with st.sidebar:
    st.subheader("⚙ 시스템 관리")
    if st.button("DB 업데이트"):
        with st.spinner("DB 갱신 중..."):
            try:
                res = requests.post("http://127.0.0.1:8000/update_db")
                res.raise_for_status()
                st.success(res.json()["message"])
            except Exception as e:
                st.error(f"DB 업데이트 실패: {e}")

st.caption(f"Session ID: `{st.session_state.session_id}`")  # 디버깅용 표시
st.divider()

# === 기존 대화 출력 ===
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# === 사용자 입력 ===
if user_query := st.chat_input("법률 관련 질문을 입력하세요."):
    # 사용자 입력 표시 및 기록
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # 백엔드 API 호출
    with st.chat_message("assistant"):
        with st.spinner("답변 생성 중..."):
            try:
                response = requests.post(
                    "http://127.0.0.1:8000/ask",
                    json={
                        "query": user_query,
                        "session_id": st.session_state.session_id,
                    }
                )
                response.raise_for_status()
                data = response.json()
                answer = data.get("answer", "답변 생성에 실패했습니다.")
            except Exception as e:
                answer = f"⚠ 오류 발생: {e}"

            st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
