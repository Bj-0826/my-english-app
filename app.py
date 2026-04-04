import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Pro v3.9.8", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5]); week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 ({w_key})"
    except: return w_key

def load_data_safe(s_name):
    try:
        # TTL=0으로 실시간 데이터 로드
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        
        # [핵심] 시트 헤더의 공백/대소문자 무시하고 코드와 매칭
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if s_name in ["Data", "PersonalData"]:
            df = df.dropna(subset=['date', 'account'])
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
        elif s_name == "Sheet1":
            df = df.dropna(subset=['english'])
            if 'memorized' in df.columns:
                df['memorized'] = df['memorized'].astype(str).str.strip().str.capitalize() == "True"
        return df
    except:
        return pd.DataFrame()

# --- [저장 및 수정 로직] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    
    df = load_data_safe(s_name)
    
    # Byungjoo님의 시트 구조(date, account, amount, memo) 보장
    if df.empty or 'date' not in df.columns:
        df = pd.DataFrame(columns=['date', 'account', 'amount', 'memo'])
        
    date_str = str(date_val).upper().strip()
    acc_str = str(acc).strip()
    
    mask = (df['date'] == date_str) & (df['account'] == acc_str)
    
    if mask.any(): 
        df.loc[mask, 'amount'] = int(amt_val)
    else: 
        # 기존 memo 컬럼 유지하며 데이터 추가
        new_row = pd.DataFrame([{"date": date_str, "account": acc_str, "amount": int(amt_val), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
        
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ {acc} 저장 완료!")

def handle_save_english():
    en, ko = st.session_state.new_en, st.session_state.new_ko
    if en and ko:
        df_en = load_data_safe("Sheet1")
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": False}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(worksheet="Sheet1", data=df_en)
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✅ 문장 저장 완료!")

def next_quiz_question():
    if 'q_idx' in st.session_state: del st.session_state.q_idx
    if 'q_in' in st.session_state: st.session_state.q_in = ""

# --- [사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.9.8")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [1. 연금자산] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (Data)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    with t1:
        if not df_p.empty:
            all_dates = sorted(df_p['date'].unique())
            recent_dates = all_dates[-3:]
            df_recent = df_p[df_p['date'].isin(recent_dates)]
            m_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur = m_total.iloc[-1]['amount']
            prev = m_total.iloc[-2]['amount'] if len(m_total)>1 else cur
            diff = cur - prev
            c1, c2 = st.columns(2)
            c1.metric(f"{recent_dates[-1]} 합계", f"{int(cur):,}원")
            c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_p.iloc[::-1], use_container_width=True)

    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2025, 2026, 2027, 2028], key="p_y")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("연금 저장", on_click=handle_save_asset, args=("Data", f"{py}-{pm}", p_acc, "p_amt"))

# --- [2. 개인자산] ---
elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리 (PersonalData)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력/수정"])
    with t1:
        if not df_per.empty:
            all_w = sorted(df_per['date'].unique())
            recent_w = all_w[-3:]
            df_recent = df_per[df_per['date'].isin(recent_w)]
            w_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur = w_total.iloc[-1]['amount']
            prev = w_total.iloc[-2]['amount'] if len(w_total)>1 else cur
            diff = cur - prev
            c1, c2 = st.columns(2)
            c1.metric(f"{get_w_label_python(recent_w[-1])} 합계", f"{int(cur):,}원")
            c2.metric("전주 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=400)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_per.iloc[::-1], use_container_width=True)

    with t2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2025, 2026, 2027, 2028], key="per_y")
        perw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

# --- [3. 영어공부] ---
else:
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data_safe("Sheet1")
    t_list, t_input, t_quiz = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈 테스트"])
    
    with t_list:
        if not df_en.empty:
            edited_df = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1],
                column_config={"memorized": st.column_config.CheckboxColumn("암기완료 ✅")},
                disabled=["date", "english", "korean"], key="en_editor")
            if st.button("암기 상태 저장"):
                df_en.update(edited_df)
                conn.update(worksheet="Sheet1", data=df_en)
                st.toast("✅ 업데이트 완료!"); st.rerun()
        
    with t_input:
        st.text_input("영어 문장", key="new_en")
        st.text_input("한글 뜻", key="new_ko")
        st.button("문장 저장", on_click=handle_save_english)

    with t_quiz:
        if not df_en.empty:
            unmem = df_en[df_en['memorized'] == False]
            if not unmem.empty:
                if 'q_idx' not in st.session_state or st.session_state.q_idx not in unmem.index:
                    st.session_state.q_idx = unmem.sample(n=1).index[0]
                q = unmem.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력", key="q_in")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("정답 확인"):
                        if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                        else: st.error(f"오답! 정답: {q['english']}")
                with c2: st.button("다음 문제", on_click=next_quiz_question)