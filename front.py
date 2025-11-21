import streamlit as st
import requests

# 페이지 설정
st.set_page_config(page_title="Law AI AGENT", layout="centered")
st.title("Law AI AGENT")

# === 고유 세션 ID 생성 (대화 연결용) ===
if "session_id" not in st.session_state:
    res = requests.get("http://127.0.0.1:8000/").json()
    # session_id, active_conv_id, history, title
    st.session_state.session_id = res["session_id"]
    st.session_state.active_conv_id = res.get("active_conv_id", None)
    st.session_state.active_conv_title = res.get("title", "")

# === 사이드바 ===
with st.sidebar:
    # === 대화 목록 가져오기 ===
    try:
        res = requests.get(
            "http://127.0.0.1:8000/get_conversations",
            params={"session_id": st.session_state.session_id}
        )
        data = res.json()

        if data["status"] == "ok":
            conv_list = data["conversations"]
        else:
            st.error(data["message"])
            conv_list = []
    except Exception as e:
        st.error(f"대화 목록 불러오기 오류: {e}")
        conv_list = []

    st.subheader("대화 관리")
    # -----------------------
    # 1) 새 대화 생성 기능
    # -----------------------
    if st.button("새 대화"):
        with st.spinner("새 대화 생성 중..."):
            try:
                res = requests.post(
                    "http://127.0.0.1:8000/new_conversation",
                    params={"session_id": st.session_state.session_id}
                )
                data = res.json()

                if data["status"] == "error":
                    st.error(data["message"])
                else:
                    st.success(f"새 대화 생성됨: {data['title']}")
                    st.session_state.active_conv_id = data["conversation_id"]
                    st.rerun()

            except Exception as e:
                st.error(f"오류 발생: {e}")

    # -----------------------
    # 2) 대화 다운로드 기능
    # -----------------------
    if st.button("대화 다운로드"):
        with st.spinner("대화 파일 생성 중..."):
            if st.session_state.active_conv_id is None:
                st.error("대화가 없습니다.")
            else:
                try:
                    res = requests.get(
                        "http://127.0.0.1:8000/download_conversation",
                        params={
                            "session_id": st.session_state.session_id,
                            "conversation_id": st.session_state.active_conv_id
                        }
                    )
                    res.raise_for_status()
                    file_bytes = res.text
                    st.download_button(
                        label="파일 생성 완료. 다운로드하려면 누르세요",
                        data=file_bytes,
                        file_name=f"conversation_{st.session_state.active_conv_id[6:6+5]}.txt",
                        mime="text/plain"
                    )
                except Exception as e:
                    st.error(f"오류 발생: {e}")

    # -----------------------
    # 3) 대화 삭제 기능
    # -----------------------
    if st.button("대화 삭제"):
        with st.spinner("대화 삭제 중..."):
            if st.session_state.active_conv_id is None:
                st.error("대화가 없습니다.")
            else:
                try:
                    res = requests.delete(
                        "http://127.0.0.1:8000/delete_conversation",
                        params={
                            "session_id": st.session_state.session_id,
                            "conversation_id": st.session_state.active_conv_id
                        }
                    )
                    data = res.json()

                    if data["status"] == "error":
                        st.error(data["message"])
                    else:
                        st.success(data["message"])
                        st.session_state.active_conv_id = data["active_conv_id"]
                        st.session_state.active_conv_title = ""
                        st.rerun()

                except Exception as e:
                    st.error(f"오류 발생: {e}")

    st.divider()
    
    # === 대화 목록 표시 ===
    st.write("### 대화 목록")

    for conv in conv_list:
        btn_label = conv["title"]
        conv_id = conv["conversation_id"]

        if st.button(btn_label, key=f"conv_{conv_id}"):
            # 전환 요청
            try:
                switch_res = requests.post(
                    "http://127.0.0.1:8000/switch_conversation",
                    params={
                        "session_id": st.session_state.session_id,
                        "conversation_id": conv_id
                    }
                ).json()

                if switch_res["status"] == "ok":
                    st.session_state.active_conv_id = conv_id
                    st.session_state.active_conv_title = switch_res["title"]
                    st.rerun()
                else:
                    st.error(switch_res["message"])

            except Exception as e:
                st.error(f"전환 오류: {e}")

    st.divider()
    
    st.subheader("⚙ 시스템 관리")
    # if st.button("전처리"):
    if st.button("DB 업데이트"):
        with st.spinner("DB 갱신 중..."):
            try:
                res = requests.post("http://127.0.0.1:8000/update_db")
                res.raise_for_status()
                st.success(res.json()["message"])
            except Exception as e:
                st.error(f"DB 업데이트 실패: {e}")

# 현재 active conversation을 매번 백엔드에서 받아오기
if st.session_state.active_conv_id:
    conv_detail = requests.get(
        "http://127.0.0.1:8000/get_conversation_detail",
        params={
            "session_id": st.session_state.session_id,
            "conversation_id": st.session_state.active_conv_id
        }
    ).json()

    history = conv_detail.get("history", [])
    st.session_state.active_conv_title = conv_detail.get("title", "")
else:
    history = []

# === 세션ID, 대화ID 표시, 대화출력 ===
st.caption(
    f"Session ID: `{st.session_state.session_id}`<br>"
    f"Conversation ID: `{st.session_state.active_conv_id}`<br>"
    f"Title: `{st.session_state.active_conv_title}`<br>",
    unsafe_allow_html=True
)
st.divider()

for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# === 사용자 입력 ===
if user_query := st.chat_input("법률 관련 질문을 입력하세요."):
    if st.session_state.active_conv_id == None:
        st.warning("대화를 생성하거나 선택하세요.")
        st.stop()
    
    # 사용자 입력 표시
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
                        "conv_id": st.session_state.active_conv_id
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "ok":
                    answer = data.get("answer", "답변을 받아오지 못했습니다.")
                else:
                    answer = f"오류: {data}"
            except Exception as e:
                answer = f"⚠ 오류 발생: {e}"
            
            st.markdown(answer)