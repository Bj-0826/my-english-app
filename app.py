import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v2.8", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수: 캐시 없이 실시간 로드] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

def load_data_realtime(s_name):
    """캐시를 사용하지 않고 실시간으로 시트를 읽어오며 유령 데이터를 제거합니다."""
    try:
        # ttl=0을 설정하여 캐시를 사용하지 않음
        df = conn.read(worksheet=s_name, ttl=0)
        if df is not None and not df.empty:
            # 1. 날짜나 계좌가 비어있는 '유령 행' 삭제
            df = df.dropna(subset=['date', 'account'])
            # 2. 금액 숫자 변환
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            # 3. 텍스트 정규화
            df['date'] = df['date'].astype(str).str.upper().str.strip()
            df = df[df['date'] != 'NAN'] # 잘못된 데이터 제거
            return df
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])
    except: 
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])

# --- [저장 로직] ---
def handle_save_final(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val == 0:
        st.warning("금액을 입력해주세요.")
        return

    df = load_data_realtime(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    
    mask = (df['date'] == date_val) & (df['account'] == acc)
    
    if mask.any():
        df.loc[mask, 'amount'] = int(amt_val)
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    conn.update(worksheet=s_name, data=df)
    
    # 상태 초기화
    st.session_state[amt_key] = 0
    st.toast(f"✅ [{acc}] 저장 완료!", icon="💰")

# --- [메인 로직 시작] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.8")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리")
    df_p = load_data_realtime("Data")
    t1, t2 = st.tabs(["📊 월간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_p.empty and len(df_p) > 0:
            all_m = sorted(df_p['date'].unique())
            sel_m = st.selectbox("조회 월", all_m, index=len(all_m)-1)
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
        else:
            st.info("시트에 데이터가 없습니다. 입력 탭에서 데이터를 넣어주세요.")

    with t2:
        st.subheader("연금 입력")
        c1, c2 = st.columns(2)
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="py_v")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm_v")
        t_date = f"{py}-{pm}"
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_v")
        st.number_input("금액(원)", step=100000, key="p_amt_v")
        st.button("연금 저장", on_click=handle_save_final, args=("Data", t_date, p_acc, "p_amt_v"))

elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리")
    df_per = load_data_realtime("PersonalData")
    t1, t2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_per.empty:
            all_w = sorted(df_per['date'].unique())
            sel_w = st.selectbox("조회 주차", all_w, index=len(all_w)-1, format_func=get_w_label_python)
            cur_w = df_per[df_per['date'] == sel_w]['amount'].sum()
            st.metric(f"{get_w_label_python(sel_w)} 총합", f"{int(cur_w):,}원")
            
            fig = go.Figure()
            for acc in sorted(df_per['account'].unique()):
                acc_df = df_per[df_per['account'] == acc].sort_values('date')
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t2:
        st.subheader("개인자산 입력")
        c1, c2 = st.columns(2)
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="pery_v")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="perw_v")
        t_week = f"Y{pery}W{perw}"
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_v")
        st.number_input("금액(원)", step=10000, key="per_amt_v")
        st.button("개인자산 저장", on_click=handle_save_final, args=("PersonalData", t_week, p_acc_per, "per_amt_v"))

else:
    st.header("🔤 영어 공부")
    df_en = load_data_realtime("Sheet1")
    st.dataframe(df_en.iloc[::-1], use_container_width=True)