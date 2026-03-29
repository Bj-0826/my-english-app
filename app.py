import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v2.4", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

@st.cache_data(ttl=0)
def load_data(s_name):
    try:
        df = conn.read(worksheet=s_name)
        if df is not None and not df.empty:
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.strip()
            return df
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])
    except: return pd.DataFrame(columns=["date", "account", "amount", "memo"])

# --- [입력창 유지 및 초기화 저장 로직] ---
def handle_save(s_name, date_val, acc, amt_key):
    amt = st.session_state[amt_key]
    df = load_data(s_name)
    mask = (df['date'] == date_val) & (df['account'] == acc)
    
    if mask.any():
        df.loc[mask, 'amount'] = int(amt)
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    conn.update(worksheet=s_name, data=df)
    
    # 입력창 값 0으로 초기화 (화면은 현재 탭 유지)
    st.session_state[amt_key] = 0
    st.toast(f"✅ [{acc}] 저장 및 업데이트 완료!", icon="💰")

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.4")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 화면 로직] ---

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (월 단위)")
    df_pen = load_data("Data")
    # '데이터 입력/수정' 탭을 기본(index=1)으로 설정할 수도 있지만, 대시보드와 선택 가능하게 둠
    tab1, tab2 = st.tabs(["📊 월간 대시보드", "📝 데이터 입력/수정"])
    
    with tab1:
        if not df_pen.empty:
            all_months = sorted(df_pen['date'].unique())
            sel_m = st.selectbox("조회할 월 선택", all_months, index=len(all_months)-1, key="view_m")
            target_df = df_pen[df_pen['date'] == sel_m]
            cur_p = target_df['amount'].sum()
            
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_p + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, c2 = st.columns(2)
            c1.metric(f"{sel_m} 총 연금", f"{int(cur_p):,}원")
            c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            
            monthly_trend = df_pen.groupby('date')['amount'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=monthly_trend['date'], y=monthly_trend['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.1f}억" for v in monthly_trend['amount']], name="연금추이"))
            fig.update_layout(xaxis_type='category', height=400)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("연금 정보 입력/수정")
        c1, c2 = st.columns(2)
        with c1: p_year = st.selectbox("연도", [2026, 2027, 2028], key="py")
        with c2: p_month = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm")
        
        t_date = f"{p_year}-{p_month}"
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa")
        st.number_input("금액(원)", step=100000, key="p_amount")
        
        # handle_save 실행 후에도 tab2에 머무름
        st.button("연금 데이터 저장", on_click=handle_save, args=("Data", t_date, p_acc, "p_amount"))

elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data("PersonalData")
    tab1, tab2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력/수정"])
    
    with tab1:
        if not df_per.empty:
            all_weeks = sorted(df_per['date'].unique())
            sel_w = st.selectbox("조회할 주차 선택", all_weeks, index=len(all_weeks)-1, format_func=get_w_label_python, key="view_w")
            target_df = df_per[df_per['date'] == sel_w]
            cur_w = target_df['amount'].sum()
            st.metric(f"{get_w_label_python(sel_w)} 총 자산", f"{int(cur_w):,}원")
            
            fig = go.Figure()
            for acc in df_per['account'].unique():
                acc_df = df_per[df_per['account'] == acc].sort_values('date')
                labels = [get_w_label_python(d) for d in acc_df['date']]
                fig.add_trace(go.Bar(x=labels, y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("개인 자산 입력/수정")
        c1, c2 = st.columns(2)
        with c1: per_y = st.selectbox("연도", [2026, 2027, 2028], key="pery")
        with c2: per_w = st.number_input("주차(Week)", min_value=1, max_value=53, value=13, key="perw")
        
        t_week = f"Y{per_y}W{per_w}"
        st.caption(f"선택 주차: {get_w_label_python(t_week)}")
        p_acc = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_a")
        st.number_input("금액(원)", step=10000, key="per_amount")
        
        st.button("개인 자산 저장", on_click=handle_save, args=("PersonalData", t_week, p_acc, "per_amount"))

else:
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data("Sheet1")
    st.dataframe(df_en.iloc[::-1], use_container_width=True)