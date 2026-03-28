import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 페이지 설정
st.set_page_config(page_title="Byungjoo's Life Manager", layout="wide")
st.title("Byungjoo 통합 매니저 Pro 🚀")

# 은퇴 시뮬레이션 설정 (v43 로직)
target_amt = 1200000000 # 12억
retirement_date = datetime.date(2028, 12, 31)
today = datetime.date.today()
mon_left = (retirement_date.year - today.year) * 12 + (retirement_date.month - today.month)
d_day = (retirement_date - today).days

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 데이터 로드 함수 (탭별로 호출)
def get_data(sheet_name):
    try:
        return conn.read(worksheet=sheet_name, ttl="0s")
    except:
        return pd.DataFrame()

# 4. 저장 로직 (중복 체크 및 업데이트)
def save_asset_data(type_mode, date_val, acc, amt):
    sheet_name = "Data" if type_mode == "PENSION" else "PersonalData"
    df = get_data(sheet_name)
    
    # 새 데이터 행
    new_entry = {"date": str(date_val), "account": acc, "amount": int(amt), "memo": ""}
    
    if not df.empty:
        # 동일 날짜, 동일 계좌가 있는지 확인
        mask = (df['date'].astype(str) == str(date_val)) & (df['account'] == acc)
        if mask.any():
            df.loc[mask, 'amount'] = int(amt) # 수정
        else:
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True) # 신규
    else:
        df = pd.DataFrame([new_entry])
        
    conn.update(worksheet=sheet_name, data=df)
    st.success(f"[{acc}] 저장 완료!")

def save_english():
    df = get_data("Sheet1")
    new_row = pd.DataFrame([{"date": str(today), "english": st.session_state.en_in, "korean": st.session_state.ko_in, "memorized": "False"}])
    conn.update(worksheet="Sheet1", data=pd.concat([df, new_row], ignore_index=True))
    st.session_state.en_in = ""; st.session_state.ko_in = ""
    st.success("영어 문장 저장 완료!")

# 5. 사이드바 - 입력 및 D-Day
with st.sidebar:
    st.metric("은퇴까지", f"D-{d_day}", f"{mon_left}개월 남음")
    st.divider()
    menu = st.radio("메뉴 선택", ["💰 자산 관리", "🔤 영어 공부"])
    
    if menu == "💰 자산 관리":
        st.subheader("자산 기록")
        a_type = st.selectbox("구분", ["연금자산", "개인자산"])
        # 날짜 선택 (연금은 월 단위, 개인은 주 단위 느낌으로 일자 선택)
        a_date = st.date_input("기준 날짜", today)
        acc_list = ['퇴직연금', 'IRP', 'ISA', '개인연금'] if a_type == "연금자산" else ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타']
        a_acc = st.selectbox("계좌 선택", acc_list)
        a_amt = st.number_input("금액(원)", step=10000)
        if st.button("자산 저장"):
            m = "PENSION" if a_type == "연금자산" else "PERSONAL"
            save_asset_data(m, a_date, a_acc, a_amt)
            st.rerun()
            
    else:
        st.subheader("영어 문장 추가")
        st.text_input("영어", key="en_in")
        st.text_input("뜻", key="ko_in")
        st.button("공부 기록", on_click=save_english)

# 6. 메인 화면 - 대시보드 및 리스트
df_en = get_data("Sheet1")
df_pen = get_data("Data")
df_per = get_data("PersonalData")

t1, t2, t3 = st.tabs(["📊 대시보드", "📖 리스트 보기", "🧠 퀴즈"])

with t1:
    # 은퇴 시뮬레이션 계산
    cur_p = df_pen['amount'].sum() if not df_pen.empty else 0
    cur_per = df_per['amount'].sum() if not df_per.empty else 0
    total = cur_p + cur_per
    
    # v43 시뮬레이션 수식 적용
    exp_total = cur_p + (2800000 * mon_left) + 390000000
    rate = (exp_total / target_amt) * 100
    
    c1, c2 = st.columns(2)
    c1.metric("현재 총 자산", f"{total:,}원")
    c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {exp_total/100000000:.1f}억")
    
    # 차트 시각화 (Plotly)
    if not df_pen.empty:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_pen['date'], y=df_pen['amount'], mode='lines+markers', name='연금추이'))
        fig.update_layout(title="자산 성장 흐름", height=350)
        st.plotly_chart(fig, use_container_width=True)

with t2:
    st.write("📂 최근 자산 내역 (개인)")
    st.dataframe(df_per.iloc[::-1], use_container_width=True)
    st.write("📖 최근 영어 문장")
    st.dataframe(df_en.iloc[::-1], use_container_width=True)

with t3:
    # 기존 퀴즈 로직 (간략화)
    if not df_en.empty:
        if 'q_idx' not in st.session_state: st.session_state.q_idx = df_en.sample(n=1).index[0]
        q = df_en.loc[st.session_state.q_idx]
        st.info(f"뜻: {q['korean']}")
        ans = st.text_input("영어 정답 입력", key="q_in")
        if st.button("확인"):
            if ans.strip().lower() == q['english'].strip().lower(): st.success("정답!"); st.balloons()
            else: st.error(f"오답! 정답: {q['english']}")
        if st.button("다음 문제"):
            del st.session_state.q_idx
            st.session_state.q_in = ""
            st.rerun()