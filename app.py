import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime

# 앱 제목
st.set_page_config(page_title="Byungjoo's English Vault", layout="centered")
st.title("Byungjoo의 영어 문장 금고 📚")

# 구글 시트 연결 설정
conn = st.connection("gsheets", type=GSheetsConnection)

# 데이터 불러오기 함수
def load_data():
    return conn.read(ttl="0s")

df = load_data()

# 세션 상태 초기화 (입력창 비우기용)
if "new_en" not in st.session_state:
    st.session_state.new_en = ""
if "new_ko" not in st.session_state:
    st.session_state.new_ko = ""

# 사이드바: 문장 추가하기
with st.sidebar:
    st.header("새 문장 추가")
    # key 설정을 통해 세션 상태와 연결
    new_en = st.text_input("영어 문장", key="en_input", value=st.session_state.new_en)
    new_ko = st.text_input("한국어 뜻", key="ko_input", value=st.session_state.new_ko)
    
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
            
            # 저장 성공 후 세션 상태의 값을 비움
            st.session_state.new_en = ""
            st.session_state.new_ko = ""
            
            st.success("구글 시트에 저장 완료!")
            st.rerun() # 화면을 다시 그려서 입력창을 비운 상태로 노출
        else:
            st.warning("문장과 뜻을 모두 입력해주세요.")

# 메인 화면: 탭 나누기 (기존과 동일)
tab1, tab2 = st.tabs(["📖 내 문장 리스트", "🧠 암기 테스트"])

with tab1:
    st.subheader("저장된 문장들")
    if not df.empty:
        # 최신 저장 문장이 위로 오게 하려면 아래 줄 주석 해제
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
        
        # 퀴즈 입력창도 제출 후 비워지도록 설정 가능
        quiz_answer = st.text_input("영어 문장을 입력하세요", key="quiz_input")
        
        if st.button("정답 확인"):
            if quiz_answer.strip().lower() == str(target['english']).strip().lower():
                st.balloons()
                st.success("정답입니다! 완벽해요.")
                if st.button("다음 문제"):
                    del st.session_state.quiz_idx
                    st.rerun()
            else:
                st.error(f"아쉽네요! 정답은: {target['english']}")
    else:
        st.warning("테스트할 문장이 없습니다.")