import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Pro v3.9.6", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [설정: 시트 탭 이름 확인 필수!] ---
# 구글 시트 하단 탭 이름이 '시트1'인지 'Sheet1'인지 확인 후 아래를 수정하세요.
ENGLISH_SHEET_NAME = "시트1"  # <-- 여기서 이름을 실제 탭 이름과 똑같이 맞추세요!

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        if 'W' not in w_key: return w_key
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

def load_data_safe(s_name):
    try:
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str).str.strip().str.upper()
        
        if s_name in ["Data", "PersonalData"]:
            if 'amount' in df.columns:
                df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        
        elif s_name == ENGLISH_SHEET_NAME:
            if 'memorized' not in df.columns:
                df['memorized'] = False
            else:
                df['memorized'] = df['memorized'].astype(str).str.upper() == "TRUE"
        return df
    except Exception as e:
        st.error(f"❌ '{s_name}' 탭을 불러오지 못했습니다. (원인: {e})")
        return pd.DataFrame()

# --- [저장 로직] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    df = load_data_safe(s_name)
    if df.empty: df = pd.DataFrame(columns=['date', 'account', 'amount'])
    target_date = str(date_val).strip().upper()
    mask = (df['date'] == target_date) & (df['account'] == str(acc))
    if mask.any(): df.loc[mask, 'amount'] = int(amt_val)
    else: df = pd.concat([df, pd.DataFrame([{"date": target_date, "account": str(acc), "amount": int(amt_val)}])], ignore_index=True)
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ {acc} 저장 완료!")

def handle_save_english():
    en, ko = st.session_state.new_en, st.session_state.new_ko
    if en and ko:
        df_en = load_data_safe(ENGLISH_SHEET_NAME)
        if df_en.empty: df_en = pd.DataFrame(columns=['date', 'english', 'korean', 'memorized'])
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": False}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(worksheet=ENGLISH_SHEET_NAME, data=df_en)
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✅ 문장 저장 완료!")

def next_quiz_question():
    if 'q_idx' in st.session_state: del st.session_state.q_idx
    if 'q_in' in st.session_state: st.session_state.q_in = ""

# --- [사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.9.6")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_p.empty and 'date' in df_p.columns:
            available_dates = sorted([str(d) for d in df_p['date'].unique()])
            if available_dates:
                recent_dates = available_dates[-3:]
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
        else: st.info("'Data' 탭에 데이터가 없습니다.")

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_per.empty and 'date' in df_per.columns:
            available_weeks = sorted([str(d) for d in df_per['date'].unique()])
            if available_weeks:
                recent_w = available_weeks[-3:]
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
        else: st.info("'PersonalData' 탭에 데이터가 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2026, 2027, 2028], key="per_y")
        pw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{py}W{pw}", p_acc, "per_amt"))

else:
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data_safe(ENGLISH_SHEET_NAME)
    t_list, t_input, t_quiz = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈 테스트"])
    
    with t_list:
        if not df_en.empty and 'english' in df_en.columns:
            display_df = df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1]
            edited_df = st.data_editor(display_df, use_container_width=True, key="en_editor")
            if st.button("변경사항 저장"):
                df_en.update(edited_df)
                conn.update(worksheet=ENGLISH_SHEET_NAME, data=df_en)
                st.toast("✅ 업데이트 완료!")
        else: st.warning(f"⚠️ '{ENGLISH_SHEET_NAME}' 탭을 찾을 수 없습니다. 시트 이름을 확인해 주세요.")
        
    with t_input:
        st.text_input("영어 문장", key="new_en")
        st.text_input("한글 뜻", key="new_ko")
        st.button("문장 저장", on_click=handle_save_english)

    with t_quiz:
        if not df_en.empty and 'english' in df_en.columns:
            unmem = df_en[df_en['memorized'] == False]
            if not unmem.empty:
                if 'q_idx' not in st.session_state: st.session_state.q_idx = unmem.sample(n=1).index[0]
                q = unmem.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력", key="q_in")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                    else: st.error(f"오답! 정답: {q['english']}")
                st.button("다음 문제", on_click=next_quiz_question)
            else: st.success("🎉 완료!")