import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 앱 제목
st.title("Byungjoo의 영어 문장 금고 (Google Sheets Ver.) 📚")

# 구글 시트 연결 설정
conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 불러오기 함수
def load_data():
    return conn.read(ttl="0s") # 실시간 데이터를 가져오기 위해 ttl을 0으로 설정

df = load_data()

# 사이드바: 문장 추가하기
with st.sidebar:
    st.header("새 문장 추가")
    new_en = st.text_input("영어 문장")
    new_ko = st.text_input("한국어 뜻")
    
    if st.button("저장하기"):
        if new_en and new_ko:
            new_row = pd.DataFrame([{
                "date": str(datetime.date.today()),
                "english": new_en,
                "korean": new_ko,
                "memorized": "False"
            }])
            updated_df = pd.concat([df, new_row], ignore_index=True)
            conn.update(data=updated_df)
            st.success("구글 시트에 저장 완료!")
            st.rerun()
        else:
            st.warning("문장과 뜻을 모두 입력해주세요.")

# 메인 화면: 탭 나누기
tab1, tab2 = st.tabs(["📖 내 문장 리스트", "🧠 암기 테스트"])

with tab1:
    st.subheader("저장된 문장들")
    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("아직 저장된 문장이 없어요.")

with tab2:
    st.subheader("오늘의 복습 퀴즈")
    if not df.empty:
        if 'quiz_idx' not in st.session_state:
            st.session_state.quiz_idx = df.sample(n=1).index[0]
        
        target = df.loc[st.session_state.quiz_idx]
        st.write(f"**뜻:** {target['korean']}")
        user_answer = st.text_input("영어 문장을 입력하세요")
        
        if st.button("정답 확인"):
            if user_answer.strip().lower() == str(target['english']).strip().lower():
                st.balloons()
                st.success("정답입니다!")
                if st.button("다음 문제"):
                    del st.session_state.quiz_idx
                    st.rerun()
            else:
                st.error(f"오답입니다. 정답은: {target['english']}")
    else:
        st.warning("테스트할 문장이 없습니다.")