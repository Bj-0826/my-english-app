import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v2.9", layout="wide")

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

def load_data_integrated(s_name):
    """시트별 특성에 맞춰 데이터를 실시간 로드합니다."""
    try:
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        
        # 공통: 빈 행 제거
        df = df.dropna(how='all')
        
        if s_name in ["Data", "PersonalData"]:
            # 자산 데이터용 클리닝
            df = df.dropna(subset=['date', 'account'])
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
        else:
            # 영어 공부(Sheet1)용 클리닝: 'english' 컬럼 기준으로 빈 값 제거
            df = df.dropna(subset=['english'])
            df['date'] = df['date'].astype(str).str.strip()
            
        return df
    except:
        return pd.DataFrame()

def handle_save_integrated(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0:
        st.warning("금액을 입력해주세요.")
        return

    df = load_data_integrated(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    
    # 중복 체크
    if not df.empty and 'date' in df.columns and 'account' in df.columns:
        mask = (df['date'] == date_val) & (df['account'] == acc)
        if mask.any():
            df.loc[mask, 'amount'] = int(amt_val)
        else:
            new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
            df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
    
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ [{acc}] 저장 완료!", icon="💰")

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.title("Byungjoo Pro v2.9")
    menu = st.radio("메뉴 선택", ["💰 연금자산 관리", "💵 개인자산 관리", "🔤 영어 공부방"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 로직] ---

# 1. 연금자산
if menu == "💰 연금자산 관리":
    st.header("💰 연금자산 관리 (월 단위)")
    df_p = load_data_integrated("Data")
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
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="py_v29")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm_v29")
        t_date = f"{py}-{pm}"
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_v29")
        st.number_input("금액(원)", step=100000, key="p_amt_v29")
        st.button("연금 저장", on_click=handle_save_integrated, args=("Data", t_date, p_acc, "p_amt_v29"))

# 2. 개인자산
elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (주 단위)")
    df_per = load_data_integrated("PersonalData")
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
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="pery_v29")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="perw_v29")
        t_week = f"Y{pery}W{perw}"
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_v29")
        st.number_input("금액(원)", step=10000, key="per_amt_v29")
        st.button("개인자산 저장", on_click=handle_save_integrated, args=("PersonalData", t_week, p_acc_per, "per_amt_v29"))

# 3. 영어 공부 (복구 완료)
else:
    st.header("🔤 Byungjoo의 영어 공부 공간")
    df_en = load_data_integrated("Sheet1")
    
    tab_list, tab_quiz = st.tabs(["📖 저장된 문장", "🧠 퀴즈 테스트"])
    
    with tab_list:
        if not df_en.empty:
            st.dataframe(df_en.iloc[::-1], use_container_width=True)
        else:
            st.warning("저장된 영어 문장이 없습니다. 구글 시트의 'Sheet1'을 확인해 주세요.")
            
    with tab_quiz:
        if not df_en.empty:
            if 'q_idx' not in st.session_state: st.session_state.q_idx = df_en.sample(n=1).index[0]
            try:
                q = df_en.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어 문장을 입력하세요", key="q_in")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답입니다!"); st.balloons()
                    else: st.error(f"오답입니다. 정답: {q['english']}")
                if st.button("다음 문제"):
                    del st.session_state.q_idx
                    st.rerun()
            except:
                del st.session_state.q_idx
                st.rerun()
        else: st.info("문장이 없습니다.")