import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v3.1", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

def load_data_safe(s_name):
    try:
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        df = df.dropna(how='all')
        if s_name in ["Data", "PersonalData"]:
            df = df.dropna(subset=['date', 'account'])
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
        else:
            df = df.dropna(subset=['english'])
        return df
    except: return pd.DataFrame()

# --- [통합 저장 로직] ---
def handle_save_final(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0:
        st.warning("금액을 입력해주세요.")
        return
    df = load_data_safe(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    if not df.empty:
        mask = (df['date'] == date_val) & (df['account'] == acc)
        if mask.any(): df.loc[mask, 'amount'] = int(amt_val)
        else:
            new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
            df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
    
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ [{acc}] 저장 완료!", icon="💰")

# --- [사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.1")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 로직] ---

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (최근 3개월 분석)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    
    with t1:
        if not df_p.empty:
            # 1. 최근 3개월 데이터 추출
            monthly_total = df_p.groupby('date')['amount'].sum().reset_index().sort_values('date')
            recent_3m = monthly_total.tail(3)
            
            # 2. 증감률 계산 (Delta)
            cur_m_val = recent_3m.iloc[-1]['amount']
            prev_m_val = recent_3m.iloc[-2]['amount'] if len(recent_3m) > 1 else cur_m_val
            delta_val = cur_m_val - prev_m_val
            delta_percent = (delta_val / prev_m_val * 100) if prev_m_val != 0 else 0
            
            # 은퇴 계산기
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_m_val + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            col1, col2, col3 = st.columns(3)
            col1.metric("현재 총 연금", f"{int(cur_m_val):,}원", f"{delta_percent:.1f}% ({int(delta_val):,}원)")
            col2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            col3.metric("기준 월", recent_3m.iloc[-1]['date'])
            
            # 3개월 그래프
            fig = go.Figure(go.Scatter(x=recent_3m['date'], y=recent_3m['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.2f}억" for v in recent_3m['amount']], textposition="top center"))
            fig.update_layout(xaxis_type='category', title="최근 3개월 연금 추이", height=400)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="py_p")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm_p")
        t_date = f"{py}-{pm}"
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_p")
        st.number_input("금액(원)", step=100000, key="p_amt_p")
        st.button("연금 저장", on_click=handle_save_final, args=("Data", t_date, p_acc, "p_amt_p"))

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리 (최근 3주 분석)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    
    with t1:
        if not df_per.empty:
            # 1. 최근 3주 데이터 추출
            weekly_total = df_per.groupby('date')['amount'].sum().reset_index().sort_values('date')
            recent_3w = weekly_total.tail(3)
            
            # 2. 증감률 계산
            cur_w_val = recent_3w.iloc[-1]['amount']
            prev_w_val = recent_3w.iloc[-2]['amount'] if len(recent_3w) > 1 else cur_w_val
            w_delta = cur_w_val - prev_w_val
            w_delta_per = (w_delta / prev_w_val * 100) if prev_w_val != 0 else 0
            
            col1, col2 = st.columns(2)
            col1.metric(f"{get_w_label_python(recent_3w.iloc[-1]['date'])} 합계", f"{int(cur_w_val):,}원", f"{w_delta_per:.1f}%")
            col2.info("최근 3주간의 자산 변동을 확인합니다.")
            
            # 3주 그래프
            fig = go.Figure()
            for acc in sorted(df_per['account'].unique()):
                acc_df = df_per[df_per['account'] == acc].sort_values('date').tail(3)
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', title="최근 3주 계좌별 비중", height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="pery_p")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="perw_p")
        t_week = f"Y{pery}W{perw}"
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_p")
        st.number_input("금액(원)", step=10000, key="per_amt_p")
        st.button("개인자산 저장", on_click=handle_save_final, args=("PersonalData", t_week, p_acc_per, "per_amt_p"))

else:
    st.header("🔤 영어 공부")
    df_en = load_data_safe("Sheet1")
    if not df_en.empty: st.dataframe(df_en.iloc[::-1], use_container_width=True)