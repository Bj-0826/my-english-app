import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 앱 제목 및 설정
st.set_page_config(page_title="Byungjoo's English Vault", layout="centered")
st.title("Byungjoo의 영어 문장 금고 📚")

# 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 불러오기 함수
def load_data():
    return conn.read(ttl="0s")

df = load_data()

# --- 핵심: 저장 후 입력창 비우기 함수 ---
def save_and_clear():
    # 현재 입력창에 적힌 내용 가져오기
    new_en = st.session_state.en_input
    new_ko = st.session_state.ko_input
    
    if new_en and new_ko:
        # 1. 데이터프레임 생성 및 업데이트
        new_row = pd.DataFrame([{
            "date": str(datetime.date.today()),
            "english": new_en,
            "korean": new_ko,
            "memorized": "False"
        }])
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(data=updated_df)
        
        # 2. 입력창 비우기 (세션 상태 직접 조작)
        st.session_state.en_input = ""
        st.session_state.ko_input = ""
        
        st.success("구글 시트에 저장 완료!")
    else:
        st.warning("문장과 뜻을 모두 입력해주세요.")

# 사이드바: 문장 추가하기
with st.sidebar:
    st.header("새 문장 추가")
    # key를 부여하면 st.session_state.en_input으로 값에 접근 가능합니다.
    st.text_input("영어 문장", key="en_input")
    st.text_input("한국어 뜻", key="ko_input")
    
    # 버튼 클릭 시 위에서 만든 save_and_clear 함수 실행
    st.button("저장하기", on_click=save_and_clear)

# 메인 화면: 탭 나누기
tab1, tab2 = st.tabs(["📖 내 문장 리스트", "🧠 암기 테스트"])

with tab1:
    st.subheader("저장된 문장들")
    if not df.empty:
        # 최신 순으로 보고 싶으시면 아래 줄 주석을 해제하세요.
        # df = df.iloc[::-1]
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
        
        quiz_answer = st.text_input("영어 문장을 입력하세요", key="quiz_answer_input")
        
        if st.button("정답 확인"):
            if quiz_answer.strip().lower() == str(target['english']).strip().lower():
                st.balloons()
                st.success("정답입니다!")
                if st.button("다음 문제"):
                    del st.session_state.quiz_idx
                    st.rerun()
            else:
                st.error(f"오답입니다. 정답은: {target['english']}")
    else:
        st.warning("테스트할 문장이 없습니다.")