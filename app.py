import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v2.0", layout="wide")

# 스타일 설정: 깔끔한 대시보드 느낌
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; }
    div[data-testid="stExpander"] { border: none; }
    </style>
""", unsafe_allow_html=True)

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수: 자바스크립트 로직 이식] ---
def get_w_label(w_key):
    """Y2026W13 형태를 '3월 4주 (W13)'로 변환"""
    try:
        year = int(w_key[1:5]) if 'Y' in w_key else 2026
        week = int(w_key.split('W')[1]) if 'W' in w_key else int(w_key)
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week-1)
        month = d.month
        week_of_month = (d.day - 1) // 7 + 1
        return f"{month}월 {week_of_month}주 (W{week})"
    except: return w_key

@st.cache_data(ttl=0)
def load_data(s_name):
    """데이터 로드 및 금액 숫자 변환 (에러 방지용)"""
    try:
        df = conn.read(worksheet=s_name)
        if df is not None and not df.empty:
            if 'amount' in df.columns:
                df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            return df
        return pd.DataFrame()
    except: return pd.DataFrame()

def save_logic(s_name, d_val, acc, amt):
    """중복 체크 후 업데이트 또는 신규 저장 (v43 핵심 기능)"""
    df = load_data(s_name)
    new_entry = {"date": str(d_val), "account": acc, "amount": int(amt), "memo": ""}
    
    if not df.empty:
        # 날짜와 계좌가 일치하는 행이 있는지 확인 (문자열 비교로 정확도 높임)
        mask = (df['date'].astype(str) == str(d_val)) & (df['account'].astype(str) == str(acc))
        if mask.any():
            df.loc[mask, 'amount'] = int(amt) # 기존 데이터 수정
        else:
            df = pd.concat([df, pd.DataFrame([new_entry])], ignore_index=True)
    else:
        df = pd.DataFrame([new_entry])
    
    conn.update(worksheet=s_name, data=df)
    st.success(f"[{acc}] 데이터가 안전하게 반영되었습니다.")

# --- [사이드바 메뉴 구성] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.0")
    menu = st.radio("메뉴 이동", ["💰 연금자산 관리", "💵 개인자산 관리", "🔤 영어 학습 공간"])
    st.divider()
    
    # 은퇴 D-Day (상시 노출)
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 화면 로직] ---

# 1. 연금자산 관리 (Default)
if menu == "💰 연금자산 관리":
    st.header("💰 연금자산 관리 (월 단위)")
    df_pen = load_data("Data")
    
    tab1, tab2 = st.tabs(["📊 대시보드", "📝 데이터 입력"])
    
    with tab1:
        if not df_pen.empty:
            # 월별 합산 데이터 준비 (비교용)
            monthly = df_pen.groupby('date')['amount'].sum().reset_index()
            monthly = monthly.sort_values('date')
            
            cur_p = monthly.iloc[-1]['amount'] # 가장 최근 달 합계
            prev_p = monthly.iloc[-2]['amount'] if len(monthly) > 1 else cur_p
            diff = cur_p - prev_p
            
            # 은퇴 시뮬레이션 (v43 로직)
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_p + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, c2 = st.columns(2)
            c1.metric(f"{monthly.iloc[-1]['date']} 총 연금", f"{int(cur_p):,}원", f"{int(diff):,}원")
            c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=monthly['date'], y=monthly['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.1f}억" for v in monthly['amount']], textposition="top center", name="연금추이"))
            fig.update_layout(title="월별 연금자산 성장", height=400, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("데이터가 없습니다. 입력 탭에서 첫 데이터를 넣어주세요.")

    with tab2:
        with st.form("pen_form"):
            p_date = st.date_input("기준 월 선택", datetime.date.today()).strftime("%Y-%m")
            p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
            p_amt = st.number_input("금액(원)", step=100000)
            if st.form_submit_button("연금 데이터 저장"):
                save_logic("Data", p_date, p_acc, p_amt)
                st.rerun()

# 2. 개인자산 관리
elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data("PersonalData")
    
    tab1, tab2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력"])
    
    with tab1:
        if not df_per.empty:
            weekly = df_per.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_w = weekly.iloc[-1]['amount']
            cur_w_label = get_w_label(weekly.iloc[-1]['date'])
            
            st.metric(f"{cur_w_label} 총 자산", f"{int(cur_w):,}원")
            
            # 누적 막대 그래프 (v43 스타일)
            fig = go.Figure()
            accounts = df_per['account'].unique()
            for acc in accounts:
                acc_data = df_per[df_per['account'] == acc]
                fig.add_trace(go.Bar(x=acc_data['date'], y=acc_data['amount'], name=acc))
            
            fig.update_layout(barmode='stack', title="주차별 계좌 비중", height=450, template="plotly_white")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("개인 자산 내역이 없습니다.")

    with tab2:
        with st.form("per_form"):
            y_val = st.selectbox("연도", [2026, 2027, 2028])
            w_val = st.number_input("주차(Week)", min_value=1, max_value=53, value=13)
            p_date_key = f"Y{y_val}W{w_val}"
            p_acc = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
            p_amt = st.number_input("금액(원)", step=10000)
            if st.form_submit_button("개인 자산 저장"):
                save_logic("PersonalData", p_date_key, p_acc, p_amt)
                st.rerun()

# 3. 영어 학습 공간
else:
    st.header("🔤 Byungjoo의 영어 문장 금고")
    df_en = load_data("Sheet1")
    
    t1, t2 = st.tabs(["📖 문장 리스트", "🧠 암기 테스트"])
    
    with t1:
        st.subheader("최근 저장된 문장")
        if not df_en.empty:
            st.dataframe(df_en.iloc[::-1], use_container_width=True)
        else:
            st.info("아직 저장된 문장이 없습니다.")
            
    with t2:
        if not df_en.empty:
            if 'q_idx' not in st.session_state: st.session_state.q_idx = df_en.sample(n=1).index[0]
            q = df_en.loc[st.session_state.q_idx]
            st.info(f"뜻: {q['korean']}")
            ans = st.text_input("영어 정답을 입력하세요", key="q_in")
            if st.button("확인"):
                if ans.strip().lower() == q['english'].strip().lower(): st.success("정답입니다!"); st.balloons()
                else: st.error(f"오답! 정답: {q['english']}")
            if st.button("다음 문제"):
                del st.session_state.q_idx
                st.rerun()