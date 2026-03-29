import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v3.0", layout="wide")

# 2. 구글 시트 연결 (가장 안정적인 설정)
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수: 실시간 데이터 로드] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

def load_data_safe(s_name):
    """캐시 없이 실시간으로 시트 데이터를 안전하게 로드"""
    try:
        # worksheet 인자를 명확히 전달
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        
        df = df.dropna(how='all') # 빈 행 제거
        
        if s_name in ["Data", "PersonalData"]:
            df = df.dropna(subset=['date', 'account'])
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
        else:
            df = df.dropna(subset=['english'])
            df['date'] = df['date'].astype(str).str.strip()
        return df
    except Exception as e:
        return pd.DataFrame()

# --- [수정된 저장 로직: APIError 방지] ---
def handle_save_final(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0:
        st.warning("금액을 입력해주세요.")
        return

    # 최신 데이터 다시 읽기
    df = load_data_safe(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    
    if not df.empty:
        mask = (df['date'] == date_val) & (df['account'] == acc)
        if mask.any():
            df.loc[mask, 'amount'] = int(amt_val)
        else:
            new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
            df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
    
    # [핵심 수정] update 시 worksheet 이름을 명시적으로 다시 전달
    try:
        conn.update(worksheet=s_name, data=df)
        st.session_state[amt_key] = 0
        st.toast(f"✅ [{acc}] 저장 완료!", icon="💰")
    except Exception as e:
        st.error(f"저장 중 오류가 발생했습니다. 구글 시트 권한이나 설정을 확인해주세요: {e}")

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.0")
    menu = st.radio("메뉴 선택", ["💰 연금자산 관리", "💵 개인자산 관리", "🔤 영어 공부방"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 로직] ---

if menu == "💰 연금자산 관리":
    st.header("💰 연금자산 관리 (월 단위)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 월간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_p.empty:
            all_m = sorted(df_p['date'].unique())
            sel_m = st.selectbox("조회 월 선택", all_m, index=len(all_m)-1)
            target = df_p[df_p['date'] == sel_m]
            cur_p = target['amount'].sum()
            
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_p + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, c2 = st.columns(2)
            c1.metric(f"{sel_m} 총 연금", f"{int(cur_p):,}원")
            c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            
            trend = df_p.groupby('date')['amount'].sum().reset_index()
            fig = go.Figure(go.Scatter(x=trend['date'], y=trend['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.1f}억" for v in trend['amount']]))
            fig.update_layout(xaxis_type='category', height=400)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("연금 데이터가 없습니다.")

    with t2:
        st.subheader("연금 정보 입력")
        c1, c2 = st.columns(2)
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="py_v3")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm_v3")
        t_date = f"{py}-{pm}"
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_v3")
        st.number_input("금액(원)", step=100000, key="p_amt_v3")
        st.button("연금 저장", on_click=handle_save_final, args=("Data", t_date, p_acc, "p_amt_v3"))

elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_per.empty:
            all_w = sorted(df_per['date'].unique())
            sel_w = st.selectbox("조회 주차 선택", all_w, index=len(all_w)-1, format_func=get_w_label_python)
            cur_w = df_per[df_per['date'] == sel_w]['amount'].sum()
            st.metric(f"{get_w_label_python(sel_w)} 총합", f"{int(cur_w):,}원")
            
            fig = go.Figure()
            for acc in sorted(df_per['account'].unique()):
                acc_df = df_per[df_per['account'] == acc].sort_values('date')
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("개인자산 데이터가 없습니다.")

    with t2:
        st.subheader("개인자산 정보 입력")
        c1, c2 = st.columns(2)
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="pery_v3")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="perw_v3")
        t_week = f"Y{pery}W{perw}"
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_v3")
        st.number_input("금액(원)", step=10000, key="per_amt_v3")
        st.button("개인자산 저장", on_click=handle_save_final, args=("PersonalData", t_week, p_acc_per, "per_amt_v3"))

else:
    st.header("🔤 Byungjoo의 영어 공부 공간")
    df_en = load_data_safe("Sheet1")
    if not df_en.empty:
        st.dataframe(df_en.iloc[::-1], use_container_width=True)
    else:
        st.info("데이터가 없습니다.")