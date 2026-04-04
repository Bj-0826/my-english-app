import streamlit as st
import pandas as pd
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 시스템 설정
st.set_page_config(page_title="Byungjoo Hub (Full Restore)", layout="wide")

@st.cache_resource
def get_gc():
    try:
        creds_info = st.secrets["connections"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except: return None

gc = get_gc()
sh = gc.open_by_url(st.secrets["connections"].get("spreadsheet")) if gc else None

def load_df(name):
    try:
        ws = sh.worksheet(name)
        df = pd.DataFrame(ws.get_all_records())
        return df
    except: return pd.DataFrame()

# --- [사이드바 메뉴: 어제와 동일한 3개 구성] ---
st.sidebar.title("🧭 Byungjoo Hub")
menu = st.sidebar.radio("메뉴 선택", ["💰 개인자산 관리", "🏛️ 연금자산 관리", "🇺🇸 영어문장 학습"])

# --- [1. 개인자산 관리] ---
if menu == "💰 개인자산 관리":
    st.header("💰 주간 개인자산 업데이트")
    
    col1, col2 = st.columns(2)
    sel_y = col1.selectbox("년도", ["2025", "2026", "2027", "2028"], index=1)
    weeks = [f"W{i:02d}" for i in range(1, 53)]
    sel_w = col2.selectbox("주차 선택", weeks, index=13)
    target_key = f"{sel_y}-{sel_w}"

    # 입력 폼: Data 탭에 직접 저장하던 방식
    st.subheader(f"📝 {target_key} 잔액 직접 입력")
    df_setup = load_df("Setup")
    df_i = df_setup[df_setup['Category'] == "개인자산"]
    
    if not df_i.empty:
        with st.form("weekly_form"):
            new_data = []
            for _, row in df_i.iterrows():
                val = st.number_input(f"{row['Name']} 잔액", key=f"w_{row['Name']}")
                new_data.append([target_key, row['Name'], val, ""])
            if st.form_submit_button("Data 시트에 저장"):
                sh.worksheet("Data").append_rows(new_data)
                st.success("데이터가 성공적으로 저장되었습니다.")

    # 현황 리포트 (Data 탭 참조)
    df_data = load_df("Data")
    if not df_data.empty:
        curr = df_data[df_data['날짜'].astype(str) == target_key]
        if not curr.empty:
            st.bar_chart(curr.set_index('계좌명')['잔액'])
            st.dataframe(curr, use_container_width=True)

# --- [2. 연금자산 관리] ---
elif menu == "🏛️ 연금자산 관리":
    st.header("🏛️ 월간 연금자산 업데이트")
    
    col1, col2 = st.columns(2)
    sel_y = col1.selectbox("년도", ["2025", "2026", "2027", "2028"], index=1, key="py")
    months = [f"{i}월" for i in range(1, 13)]
    sel_m = col2.selectbox("월 선택", months, index=datetime.now().month-1)
    target_key = f"{sel_y}-{sel_m}"

    st.subheader(f"📝 {target_key} 연금 잔액 직접 입력")
    df_setup = load_df("Setup")
    df_p = df_setup[df_setup['Category'] != "개인자산"]
    
    if not df_p.empty:
        with st.form("monthly_form"):
            new_p = []
            for _, row in df_p.iterrows():
                val = st.number_input(f"{row['Name']} 잔액", key=f"m_{row['Name']}")
                new_p.append([target_key, row['Name'], val, ""])
            if st.form_submit_button("Data 시트에 저장"):
                sh.worksheet("Data").append_rows(new_p)
                st.success("연금 데이터 저장 완료!")

    df_data = load_df("Data")
    if not df_data.empty:
        curr_m = df_data[df_data['날짜'].astype(str) == target_key]
        if not curr_m.empty:
            st.bar_chart(curr_m.set_index('계좌명')['잔액'])
            st.dataframe(curr_m, use_container_width=True)

# --- [3. 영어문장 학습] ---
elif menu == "🇺🇸 영어문장 학습":
    st.header("🎧 영어 공부 & 테스트")
    if st.button("🤖 AI 문장 생성"):
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":"Marketing PM English sentences"}])
        st.session_state['today_eng'] = res.choices[0].message.content
    
    if 'today_eng' in st.session_state:
        st.info(st.session_state['today_eng'])
        st.divider()
        ans = st.text_area("복습 테스트")
        if st.button("결과 저장"):
            sh.worksheet("English").append_row([datetime.now().strftime("%Y-%m-%d"), "Review", ans, "완료"])
            st.success("학습 기록 저장 완료!")