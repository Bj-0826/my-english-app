import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정 및 보안
st.set_page_config(page_title="Byungjoo Manager Pro v2.7", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [유틸리티: v43 로직 완벽 이식] ---
def get_w_label_python(w_key):
    """자바스크립트 getWLabel 함수와 동일한 주차 계산 로직"""
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        # 해당 주차의 월/주차 계산 (v43 방식)
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

@st.cache_data(ttl=0)
def load_data_safe(s_name):
    """데이터 타입 오류 및 날짜 변동을 막기 위한 안전 로딩"""
    try:
        df = conn.read(worksheet=s_name)
        if df is not None and not df.empty:
            # 금액: 콤마 제거 및 숫자 강제 변환
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            # 날짜: 시스템 개입 차단을 위해 문자열로 고정 및 정규화
            df['date'] = df['date'].astype(str).str.upper().str.strip()
            df['account'] = df['account'].astype(str).str.strip()
            return df
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])
    except: 
        return pd.DataFrame(columns=["date", "account", "amount", "memo"])

# --- [통합 저장 로직: 중복 방지 및 화면 유지] ---
def handle_save_final(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val == 0:
        st.warning("금액을 먼저 입력해주세요.")
        return

    # 데이터 최신화 후 비교
    df = load_data_safe(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    
    # 중복 체크: 날짜와 계좌가 일치하는 행을 정확히 찾음
    mask = (df['date'] == date_val) & (df['account'] == acc)
    
    if mask.any():
        df.loc[mask, 'amount'] = int(amt_val) # 기존 데이터 업데이트
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True) # 신규 추가
    
    # 시트 업데이트 실행
    conn.update(worksheet=s_name, data=df)
    
    # 상태 초기화: 금액만 0으로 비우고 캐시 삭제
    st.cache_data.clear()
    st.session_state[amt_key] = 0
    st.toast(f"✅ [{acc}] {date_val} 정보가 성공적으로 반영되었습니다!", icon="💰")

# --- [사이드바 구성] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.7")
    menu = st.radio("메뉴 이동", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 화면 로직] ---

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (월 단위)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 월간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_p.empty:
            all_m = sorted(df_p['date'].unique())
            sel_m = st.selectbox("조회 월 선택", all_m, index=len(all_m)-1)
            target = df_p[df_p['date'] == sel_m]
            cur_p = target['amount'].sum()
            
            # 은퇴 시뮬레이션
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_p + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, c2 = st.columns(2)
            c1.metric(f"{sel_m} 총 연금", f"{int(cur_p):,}원")
            c2.metric("은퇴 달성률", f"{rate:.1f}%", f"예상: {est_total/100000000:.1f}억")
            
            trend = df_p.groupby('date')['amount'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=trend['date'], y=trend['amount'], mode='lines+markers+text', 
                                     text=[f"{v/100000000:.1f}억" for v in trend['amount']], name="연금성장"))
            fig.update_layout(xaxis_type='category', title="월별 연금 흐름", height=400)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터를 입력해주세요.")

    with t2:
        st.subheader("연금 입력 (YYYY-MM)")
        c1, c2 = st.columns(2)
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="py_box")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=1, key="pm_box") # 기본 2월
        t_date = f"{py}-{pm}"
        st.info(f"선택된 기준: **{t_date}**")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_box")
        st.number_input("금액(원)", step=100000, key="p_amt_val")
        st.button("연금 저장/업데이트", on_click=handle_save_final, args=("Data", t_date, p_acc, "p_amt_val"))

elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력/수정"])
    
    with t1:
        if not df_per.empty:
            all_w = sorted(df_per['date'].unique())
            sel_w = st.selectbox("조회 주차 선택", all_w, index=len(all_w)-1, format_func=get_w_label_python)
            target = df_per[df_per['date'] == sel_w]
            cur_w = target['amount'].sum()
            st.metric(f"{get_w_label_python(sel_w)} 총 자산", f"{int(cur_w):,}원")
            
            fig = go.Figure()
            for acc in sorted(df_per['account'].unique()):
                acc_df = df_per[df_per['account'] == acc].sort_values('date')
                labels = [get_w_label_python(d) for d in acc_df['date']]
                fig.add_trace(go.Bar(x=labels, y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', title="주간 계좌 구성", height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터를 입력해주세요.")

    with t2:
        st.subheader("개인자산 입력 (Y####W##)")
        c1, c2 = st.columns(2)
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="pery_box")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="perw_box")
        t_week = f"Y{pery}W{perw}"
        st.info(f"선택된 주차: **{get_w_label_python(t_week)}**")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_box")
        st.number_input("금액(원)", step=10000, key="per_amt_val")
        st.button("개인자산 저장/업데이트", on_click=handle_save_final, args=("PersonalData", t_week, p_acc_per, "per_amt_val"))

else:
    st.header("🔤 영어 공부 리스트")
    df_en = load_data_safe("Sheet1")
    st.dataframe(df_en.iloc[::-1], use_container_width=True)