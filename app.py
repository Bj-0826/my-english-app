import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 1. 앱 페이지 설정
st.set_page_config(page_title="Byungjoo's English Vault", layout="centered")
st.title("Byungjoo의 영어 문장 금고 📚")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 불러오기 함수
def load_data():
    return conn.read(ttl="0s")

df = load_data()

# 4. [기능] 새 문장 저장 및 입력창 비우기 함수
def save_and_clear():
    new_en = st.session_state.en_input
    new_ko = st.session_state.ko_input
    
    if new_en and new_ko:
        new_row = pd.DataFrame([{
            "date": str(datetime.date.today()),
            "english": new_en,
            "korean": new_ko,
            "memorized": "False"
        }])
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(data=updated_df)
        
        # 입력창 상태 비우기
        st.session_state.en_input = ""
        st.session_state.ko_input = ""
        st.success("✅ 구글 시트에 저장 완료!")
    else:
        st.warning("⚠️ 문장과 뜻을 모두 입력해주세요.")

# --- 퀴즈 초기화 전용 함수 (핵심 수정 포인트) ---
def reset_quiz():
    # 1. 기존 문제 인덱스 삭제
    if 'quiz_idx' in st.session_state:
        del st.session_state.quiz_idx
    # 2. 입력창에 남은 텍스트 강제 삭제
    if 'quiz_input' in st.session_state:
        st.session_state.quiz_input = ""
    # 이 함수가 끝나면 자동으로 rerun 효과가 납니다.

# 5. 사이드바 구성
with st.sidebar:
    st.header("새 문장 추가")
    st.text_input("영어 문장", key="en_input")
    st.text_input("한국어 뜻", key="ko_input")
    st.button("저장하기", on_click=save_and_clear)

# 6. 메인 화면 구성 (탭)
tab1, tab2 = st.tabs(["📖 내 문장 리스트", "🧠 암기 테스트"])

with tab1:
    st.subheader("저장된 문장들")
    if not df.empty:
        sorted_df = df.iloc[::-1]
        st.dataframe(sorted_df, use_container_width=True)
    else:
        st.info("아직 저장된 문장이 없어요.")

with tab2:
    st.subheader("오늘의 복습 퀴즈")
    if not df.empty:
        # 퀴즈용 인덱스가 없으면 랜덤 생성
        if 'quiz_idx' not in st.session_state:
            st.session_state.quiz_idx = df.sample(n=1).index[0]
        
        target = df.loc[st.session_state.quiz_idx]
        st.info(f"**뜻:** {target['korean']}")
        
        # 답변 입력창
        quiz_answer = st.text_input("위 문장의 영어는 무엇일까요?", key="quiz_input")
        
        if st.button("정답 확인"):
            if quiz_answer.strip().lower() == str(target['english']).strip().lower():
                st.balloons()
                st.success(f"🎉 정답입니다! : **{target['english']}**")
            else:
                st.error(f"❌ 아쉽네요! 정답은 : **{target['english']}**")

        # --- 수정 포인트: on_click 콜백을 사용하여 비우기 ---
        st.button("다른 문제 풀기 (새로고침)", on_click=reset_quiz)
            
    else:
        st.warning("테스트할 문장이 없습니다.")