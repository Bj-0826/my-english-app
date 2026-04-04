import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 시스템 설정
st.set_page_config(page_title="Byungjoo Life OS v59", layout="wide", page_icon="🧭")

@st.cache_resource
def get_gc():
    try:
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except: return None

gc = get_gc()
sh = gc.open_by_url(st.secrets["connections"]["spreadsheet"]) if gc else None

# 2. 핵심 유틸리티
def load_data(sheet_name):
    try:
        ws = sh.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    if not ticker or ticker == "": return 1.0
    try:
        return yf.Ticker(str(ticker).strip()).history(period="1d")['Close'].iloc[-1]
    except: return 0

# --- 3. 사이드바 메뉴 ---
st.sidebar.title("🧭 Byungjoo Hub")
menu = st.sidebar.radio("메뉴 선택", ["🏠 홈 대시보드", "🏛️ 연금 자산 (Monthly)", "💰 개인 자산 (Weekly)", "🇺🇸 영어 공부", "✈️ 여행 기록"])

# --- 4. 메뉴별 기능 구현 ---

if menu == "🏠 홈 대시보드":
    st.header(f"👋 Byungjoo님, 좋은 하루입니다!")
    
    # 은퇴 D-Day 및 환율 (기존 GAS 핵심 로직)
    target_date = datetime(2028, 12, 31)
    dday = (target_date - datetime.now()).days
    usd_krw = get_live_price("USDKRW=X")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("은퇴 D-Day", f"{dday}일", "📅 2028.12.31")
    c2.metric("실시간 환율", f"{usd_krw:,.2f}원")
    c3.metric("오늘의 날짜", datetime.now().strftime("%Y-%m-%d"))

elif menu == "🏛️ 연금 자산 (Monthly)":
    st.header("🏛️ 연금 자산 월간 관리")
    st.caption("연금은 장기 자산이므로 월 1회 확정 기록(백업)을 권장합니다.")
    
    df_setup = load_data("Setup")
    df_pension = df_setup[df_setup['Category'] != "개인자산"]
    
    if not df_pension.empty:
        df_pension['현재가'] = df_pension['Ticker'].apply(get_live_price)
        df_pension['평가액'] = df_pension['현재가'] * df_pension['Qty']
        total_p = df_pension['평가액'].sum()
        
        st.metric("연금 자산 총액", f"{total_p:,.0f}원")
        st.dataframe(df_pension[['Category', 'Name', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}), use_container_width=True)
        
        if st.button("💾 이번 달 연금 잔고 확정 기록 (월간 업데이트)"):
            ws_data = sh.worksheet("Data")
            ws_data.append_row([datetime.now().strftime("%Y-%m-%d"), "Pension_Total", total_p])
            st.success("월간 기록이 완료되었습니다.")

elif menu == "💰 개인 자산 (Weekly)":
    st.header("💰 개인 투자 자산 주간 관리")
    st.caption("주식 및 현금 자산은 매주 수량을 점검하여 실시간 변동을 확인하세요.")
    
    df_setup = load_data("Setup")
    df_personal = df_setup[df_setup['Category'] == "개인자산"]
    
    if not df_personal.empty:
        df_personal['현재가'] = df_personal['Ticker'].apply(get_live_price)
        df_personal['평가액'] = df_personal['현재가'] * df_personal['Qty']
        total_i = df_personal['평가액'].sum()
        
        st.metric("개인 자산 총액 (Live)", f"{total_i:,.0f}원")
        st.dataframe(df_personal[['Name', 'Ticker', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}), use_container_width=True)
        
        st.info("💡 팁: 매주 일요일 저녁에 수량을 점검하고 시트의 Setup 탭을 업데이트해 주세요.")

elif menu == "🇺🇸 영어 공부":
    # (기존 GPT-4o 및 수동 저장 로직 유지)
    st.header("🎧 Business English Tutor")
    if st.button("오늘의 3문장 생성"):
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a business English tutor for a Marketing PM. Provide 3 tech/marketing sentences with Korean translations."}]
        )
        st.session_state['eng'] = res.choices[0].message.content
    if 'eng' in st.session_state:
        st.info(st.session_state['eng'])

elif menu == "✈️ 여행 기록":
    # (기존 여행 기록 CRUD 로직 유지)
    st.header("✈️ 나의 여행 아카이브")
    with st.form("travel_form"):
        t_dest = st.text_input("목적지")
        t_date = st.date_input("날짜", datetime.now())
        t_memo = st.text_area("메모")
        if st.form_submit_button("저장"):
            sh.worksheet("Travel").append_row([t_date.strftime("%Y-%m-%d"), t_dest, t_memo])
            st.success("저장 완료!")
    
    df_t = load_data("Travel")
    if not df_t.empty:
        st.dataframe(df_t.sort_values(by="날짜", ascending=False), use_container_width=True)