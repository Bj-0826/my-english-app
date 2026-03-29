import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v2.1", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수: v43 로직 정밀 이식] ---
def get_w_label_python(w_key):
    """v43의 getWLabel 함수를 파이썬으로 완벽 이식"""
    try:
        year_part = w_key[1:5] if 'Y' in w_key else "2026"
        week_part = w_key.split('W')[1] if 'W' in w_key else w_key
        year = int(year_part)
        week_num = int(week_part)
        # 주차의 시작일 계산
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

@st.cache_data(ttl=0)
def load_data(s_name):
    """데이터 로드 및 형식 강제 변환 (에러 방지)"""
    try:
        df = conn.read(worksheet=s_name)
        if df is not None and not df.empty:
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.strip() # 문자열로 비교하기 위해 공백 제거
            return df
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])
    except: return pd.DataFrame(columns=["date", "account", "amount", "memo"])

# --- [핵심 수정: 저장 및 입력창 비우기 콜백] ---
def save_pension():
    s_name = "Data"
    date_val = st.session_state.p_date.strftime("%Y-%m")
    acc = st.session_state.p_acc
    amt = st.session_state.p_amt
    
    df = load_data(s_name)
    mask = (df['date'] == date_val) & (df['account'] == acc)
    
    if mask.any():
        df.loc[mask, 'amount'] = int(amt)
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    conn.update(worksheet=s_name, data=df)
    # 입력창 초기화
    st.session_state.p_amt = 0
    st.success(f"[{acc}] 업데이트 완료!")

def save_personal():
    s_name = "PersonalData"
    date_val = f"Y{st.session_state.per_y}W{st.session_state.per_w}"
    acc = st.session_state.per_acc
    amt = st.session_state.per_amt
    
    df = load_data(s_name)
    mask = (df['date'] == date_val) & (df['account'] == acc)
    
    if mask.any():
        df.loc[mask, 'amount'] = int(amt)
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    conn.update(worksheet=s_name, data=df)
    st.session_state.per_amt = 0
    st.success(f"[{acc}] 업데이트 완료!")

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.1")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 로직] ---

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (월 단위)")
    df_pen = load_data("Data")
    
    tab1, tab2 = st.tabs(["📊 대시보드", "📝 데이터 입력"])
    
    with tab1:
        if not df_pen.empty:
            monthly = df_pen.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_p = monthly.iloc[-1]['amount']
            prev_p = monthly.iloc[-2]['amount'] if len(monthly) > 1 else cur_p
            diff = cur_p - prev_p
            
            # 은퇴 시뮬레이션 v43
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_p + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, c2 = st.columns(2)
            c1.metric(f"{monthly.iloc[-1]['date']} 총 연금", f"{int(cur_p):,}원", f"{int(diff):,}원")
            c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            
            # 그래프 수정: 월 단위를 문자열로 취급하여 주간 단위 변환 방지
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=monthly['date'], y=monthly['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.1f}억" for v in monthly['amount']], 
                                     textposition="top center", name="연금추이"))
            fig.update_layout(title="월별 연금자산 성장", xaxis_type='category', height=400)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with tab2:
        st.subheader("연금 정보 입력")
        st.date_input("기준 월", datetime.date.today(), key="p_date")
        st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="p_acc")
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("저장하기", on_click=save_pension)

elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data("PersonalData")
    
    tab1, tab2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력"])
    
    with tab1:
        if not df_per.empty:
            # 주간 데이터 라벨 적용
            weekly_sum = df_per.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_w_label = get_w_label_python(weekly_sum.iloc[-1]['date'])
            st.metric(f"{cur_w_label} 총 자산", f"{int(weekly_sum.iloc[-1]['amount']):,}원")
            
            fig = go.Figure()
            # 계좌별 스택 차트
            for acc in df_per['account'].unique():
                acc_df = df_per[df_per['account'] == acc].sort_values('date')
                # 날짜를 라벨로 변환하여 표시
                labels = [get_w_label_python(d) for d in acc_df['date']]
                fig.add_trace(go.Bar(x=labels, y=acc_df['amount'], name=acc))
            
            fig.update_layout(barmode='stack', title="주차별 계좌 비중", xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with tab2:
        st.subheader("개인 자산 입력")
        st.selectbox("연도", [2026, 2027, 2028], key="per_y")
        st.number_input("주차(Week)", min_value=1, max_value=53, value=13, key="per_w")
        st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc")
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인 자산 저장", on_click=save_personal)

else:
    # 기존 영어 학습 로직
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data("Sheet1")
    st.dataframe(df_en.iloc[::-1], use_container_width=True)