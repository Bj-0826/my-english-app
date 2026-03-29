import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v3.4", layout="wide")

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
            df['account'] = df['account'].astype(str).str.strip()
        elif s_name == "Sheet1":
            df = df.dropna(subset=['english'])
        return df
    except: return pd.DataFrame()

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
    st.title("Byungjoo Pro v3.4")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    d_day = (ret_date - datetime.date.today()).days
    st.metric("은퇴 D-Day", f"D-{d_day}")

# --- [메인 로직] ---

if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (최근 3개월)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    
    with t1:
        if not df_p.empty:
            all_dates = sorted(df_p['date'].unique())
            recent_dates = all_dates[-3:]
            df_recent = df_p[df_p['date'].isin(recent_dates)]
            monthly_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_val = monthly_total.iloc[-1]['amount']
            prev_val = monthly_total.iloc[-2]['amount'] if len(monthly_total) > 1 else cur_val
            diff = cur_val - prev_val
            diff_per = (diff / prev_val * 100) if prev_val != 0 else 0
            
            mon_left = (ret_date.year - datetime.date.today().year) * 12 + (ret_date.month - datetime.date.today().month)
            est_total = cur_val + (2800000 * mon_left) + 390000000
            rate = (est_total / 1200000000) * 100
            
            c1, col_delta, c3 = st.columns([2, 2, 1])
            c1.metric(f"{recent_dates[-1]} 합계", f"{int(cur_val):,}원")
            col_delta.metric("지난달 대비 증감", f"{diff_per:+.1f}%", f"{int(diff):+,}원")
            
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc].sort_values('date')
                fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        with c1: py = st.selectbox("연도", [2026, 2027, 2028], key="p_y")
        with c2: pm = st.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="p_a")
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("연금 저장", on_click=handle_save_final, args=("Data", f"{py}-{pm}", p_acc, "p_amt"))

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리 (최근 3주)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    
    with t1:
        if not df_per.empty:
            all_w = sorted(df_per['date'].unique())
            recent_w = all_w[-3:]
            df_recent = df_per[df_per['date'].isin(recent_w)]
            weekly_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_w_val = weekly_total.iloc[-1]['amount']
            prev_w_val = weekly_total.iloc[-2]['amount'] if len(weekly_total) > 1 else cur_w_val
            w_diff = cur_w_val - prev_w_val
            w_diff_per = (w_diff / prev_w_val * 100) if prev_w_val != 0 else 0
            
            c1, col_delta = st.columns(2)
            c1.metric(f"{get_w_label_python(recent_w[-1])} 합계", f"{int(cur_w_val):,}원")
            col_delta.metric("지난주 대비 증감", f"{w_diff_per:+.1f}%", f"{int(w_diff):+,}원")
            
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc].sort_values('date')
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        with c1: pery = st.selectbox("연도", [2026, 2027, 2028], key="per_y")
        with c2: perw = st.number_input("주차(1-53)", 1, 53, 13, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_a")
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_final, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

# --- [영어 공부 섹션 복구] ---
else:
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data_safe("Sheet1")
    tab_list, tab_input, tab_quiz = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈 테스트"])
    
    with tab_list:
        if not df_en.empty:
            st.dataframe(df_en.iloc[::-1], use_container_width=True)
        else: st.info("저장된 문장이 없습니다.")
        
    with tab_input:
        st.subheader("새로운 영어 문장 추가")
        new_en = st.text_input("영어 문장")
        new_ko = st.text_input("한글 뜻")
        if st.button("문장 저장"):
            if new_en and new_ko:
                new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": new_en, "korean": new_ko, "memorized": "False"}])
                df_en = pd.concat([df_en, new_row], ignore_index=True)
                conn.update(worksheet="Sheet1", data=df_en)
                st.success("영어 문장이 저장되었습니다!")
                st.rerun()
            else: st.warning("내용을 모두 입력해주세요.")

    with tab_quiz:
        if not df_en.empty:
            if 'q_idx' not in st.session_state: st.session_state.q_idx = df_en.sample(n=1).index[0]
            q = df_en.loc[st.session_state.q_idx]
            st.info(f"뜻: {q['korean']}")
            ans = st.text_input("영어로 입력하세요", key="q_in")
            if st.button("정답 확인"):
                if ans.strip().lower() == str(q['english']).strip().lower(): 
                    st.success("정답입니다!"); st.balloons()
                else: st.error(f"오답입니다. 정답: {q['english']}")
            if st.button("다음 문제"):
                del st.session_state.q_idx
                st.rerun()
        else: st.info("문장이 없습니다.")