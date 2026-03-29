import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Manager Pro v3.7", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5]); week_num = int(w_key.split('W')[1])
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
            # 데이터 타입 통일 (문자열로 관리)
            df['memorized'] = df['memorized'].astype(str).str.capitalize()
        return df
    except: return pd.DataFrame()

# --- [저장 로직] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    df = load_data_safe(s_name)
    if not df.empty:
        mask = (df['date'] == date_val) & (df['account'] == acc)
        if mask.any(): df.loc[mask, 'amount'] = int(amt_val)
        else: df = pd.concat([df, pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])], ignore_index=True)
    else: df = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast("💰 자산 저장 완료!")

def handle_save_english():
    en, ko = st.session_state.new_en, st.session_state.new_ko
    if en and ko:
        df_en = load_data_safe("Sheet1")
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": "False"}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(worksheet="Sheet1", data=df_en)
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✍️ 영어 문장 추가 완료!")

def mark_as_memorized(idx):
    df_en = load_data_safe("Sheet1")
    df_en.at[idx, 'memorized'] = "True"
    conn.update(worksheet="Sheet1", data=df_en)
    st.toast("✅ 암기 완료 처리되었습니다!")
    st.rerun()

def next_quiz_question():
    if 'q_idx' in st.session_state: del st.session_state.q_idx
    if 'q_in' in st.session_state: st.session_state.q_in = ""

# --- [사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.7")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_p.empty:
            recent_dates = sorted(df_p['date'].unique())[-3:]
            df_recent = df_p[df_p['date'].isin(recent_dates)]
            m_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur, prev = m_total.iloc[-1]['amount'], m_total.iloc[-2]['amount'] if len(m_total)>1 else m_total.iloc[-1]['amount']
            diff = cur - prev
            c1, c2 = st.columns(2)
            c1.metric(f"{recent_dates[-1]} 합계", f"{int(cur):,}원")
            c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', height=400)
            st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("연금 저장", on_click=handle_save_asset, args=("Data", f"{py}-{pm}", p_acc, "p_amt"))

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_per.empty:
            recent_w = sorted(df_per['date'].unique())[-3:]
            df_recent = df_per[df_per['date'].isin(recent_w)]
            w_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur, prev = w_total.iloc[-1]['amount'], w_total.iloc[-2]['amount'] if len(w_total)>1 else w_total.iloc[-1]['amount']
            diff = cur - prev
            c1, c2 = st.columns(2)
            c1.metric(f"{get_w_label_python(recent_w[-1])} 합계", f"{int(cur):,}원")
            c2.metric("전주 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', height=400)
            st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2026, 2027, 2028], key="per_y")
        perw = c2.number_input("주차", 1, 53, 13, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

else:
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data_safe("Sheet1")
    t_list, t_input, t_quiz = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈 테스트"])
    
    with t_list:
        if not df_en.empty:
            for idx, row in df_en.iloc[::-1].iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 3, 1])
                    col1.write(f"**{row['english']}**")
                    col2.write(row['korean'])
                    if row['memorized'] == "False":
                        if col3.button("외웠어요! ✅", key=f"mem_{idx}"): mark_as_memorized(idx)
                    else:
                        col3.write("✨ 암기완료")
                    st.divider()
        else: st.info("문장이 없습니다.")
        
    with t_input:
        st.text_input("영어 문장", key="new_en")
        st.text_input("한글 뜻", key="new_ko")
        st.button("문장 저장", on_click=handle_save_english)

    with t_quiz:
        # 암기 안 된(False) 문장만 필터링해서 퀴즈 출제
        unmemorized = df_en[df_en['memorized'] == "False"]
        if not unmemorized.empty:
            if 'q_idx' not in st.session_state or st.session_state.q_idx not in unmemorized.index:
                st.session_state.q_idx = unmemorized.sample(n=1).index[0]
            q = unmemorized.loc[st.session_state.q_idx]
            st.info(f"뜻: {q['korean']}")
            ans = st.text_input("영어로 입력", key="q_in")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                    else: st.error(f"오답! 정답: {q['english']}")
            with c2: st.button("다음 문제", on_click=next_quiz_question)
        else: st.success("🎉 모든 문장을 다 외우셨습니다! 새로운 문장을 추가해 보세요.")