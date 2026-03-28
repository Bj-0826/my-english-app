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
    # 실시간 반영을 위해 캐시(ttl)를 0으로 설정
    return conn.read(ttl="0s")

df = load_data()

# 4. [기능] 새 문장 저장 및 입력창 비우기 함수
def save_and_clear():
    # 사이드바 입력창의 key 값을 가져옴
    new_en = st.session_state.en_input
    new_ko = st.session_state.ko_input
    
    if new_en and new_ko:
        # 데이터프레임 생성
        new_row = pd.DataFrame([{
            "date": str(datetime.date.today()),
            "english": new_en,
            "korean": new_ko,
            "memorized": "False"
        }])
        # 기존 데이터에 추가 후 구글 시트 업데이트
        updated_df = pd.concat([df, new_row], ignore_index=True)
        conn.update(data=updated_df)
        
        # 입력창 상태 비우기
        st.session_state.en_input = ""
        st.session_state.ko_input = ""
        
        st.success("✅ 구글 시트에 저장 완료!")
    else:
        st.warning("⚠️ 문장과 뜻을 모두 입력해주세요.")

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
        # 최신 저장된 문장이 위로 오게 정렬
        sorted_df = df.iloc[::-1]
        st.dataframe(sorted_df, use_container_width=True)
    else:
        st.info("아직 저장된 문장이 없어요. 사이드바에서 추가해보세요!")

with tab2:
    st.subheader("오늘의 복습 퀴즈")
    if not df.empty:
        # 퀴즈용 인덱스가 없으면 랜덤으로 하나 생성
        if 'quiz_idx' not in st.session_state:
            st.session_state.quiz_idx = df.sample(n=1).index[0]
        
        target = df.loc[st.session_state.quiz_idx]
        st.info(f"**뜻:** {target['korean']}")
        
        # 답변 입력창 (key를 부여하여 상태 관리)
        quiz_answer = st.text_input("위 문장의 영어는 무엇일까요?", key="quiz_input")
        
        # 정답 확인 버튼
        if st.button("정답 확인"):
            if quiz_answer.strip().lower() == str(target['english']).strip().lower():
                st.balloons()
                st.success(f"🎉 정답입니다! : **{target['english']}**")
            else:
                st.error(f"❌ 아쉽네요! 정답은 : **{target['english']}**")

        # --- 다음 문제로 넘어가기 위한 초기화 로직 ---
        if st.button("다른 문제 풀기 (새로고침)"):
            # 세션에서 인덱스와 입력창 값 삭제
            if 'quiz_idx' in st.session_state:
                del st.session_state.quiz_idx
            if 'quiz_input' in st.session_state:
                st.session_state.quiz_input = ""
            st.rerun() # 앱 재실행으로 새 문제 로드
            
    else:
        st.warning("테스트할 문장이 없습니다. 먼저 문장을 추가해주세요.")