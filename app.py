import streamlit as st
import pandas as pd
import datetime
import os

# 데이터 저장 파일 설정 (CSV 형식)
DB_FILE = "my_english_sentences.csv"

# 데이터 불러오기 함수
def load_data():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    else:
        return pd.DataFrame(columns=["date", "english", "korean", "memorized"])

# 앱 제목
st.title("Byungjoo의 영어 문장 금고 📚")

# 사이드바: 문장 추가하기
with st.sidebar:
    st.header("새 문장 추가")
    new_en = st.text_input("영어 문장")
    new_ko = st.text_input("한국어 뜻")
    if st.button("저장하기"):
        df = load_data()
        new_data = pd.DataFrame([[datetime.date.today(), new_en, new_ko, False]], 
                                columns=["date", "english", "korean", "memorized"])
        df = pd.concat([df, new_data], ignore_index=True)
        df.to_csv(DB_FILE, index=False)
        st.success("저장 완료!")

# 메인 화면: 탭 나누기
tab1, tab2 = st.tabs(["📖 내 문장 리스트", "🧠 암기 테스트"])

with tab1:
    st.subheader("저장된 문장들")
    df = load_data()
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("아직 저장된 문장이 없어요.")

with tab2:
    st.subheader("오늘의 복습 퀴즈")
    df = load_data()
    if not df.empty:
        # 랜덤하게 한 문장 추출
        if 'quiz_idx' not in st.session_state:
            st.session_state.quiz_idx = df.sample(n=1).index[0]
        
        target = df.loc[st.session_state.quiz_idx]
        
        st.write(f"**뜻:** {target['korean']}")
        user_answer = st.text_input("영어 문장을 입력하세요 (대소문자 구분 없음)")
        
        if st.button("정답 확인"):
            if user_answer.strip().lower() == target['english'].strip().lower():
                st.balloons()
                st.success("정답입니다! 완벽해요.")
                # 다음 문제를 위해 인덱스 초기화 준비
                if st.button("다음 문제"):
                    del st.session_state.quiz_idx
                    st.rerun()
            else:
                st.error(f"아쉽네요! 정답은: {target['english']}")
    else:
        st.warning("테스트할 문장이 없습니다.")