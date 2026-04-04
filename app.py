import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 페이지 설정
st.set_page_config(page_title="Byungjoo Master Hub v53", layout="wide")

# 2. 연결 엔진 (가장 확실한 진단 모드 로직 채택)
@st.cache_resource
def get_gspread_client():
    try:
        # Secrets에서 직접 정보를 가져옴
        creds_info = st.secrets["connections"]["gsheets"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"연결 실패: {e}")
        return None

gc = get_gspread_client()

if gc:
    try:
        # Byungjoo님의 실제 시트 주소 (Secrets 설정값 우선)
        target_url = st.secrets["connections"].get("spreadsheet", "https://docs.google.com/spreadsheets/d/1puWzFplStYrixwCHTyvC0NDWw1N-YacA1XkZOCaM6Jk/edit")
        sh = gc.open_by_url(target_url)
    except Exception as e:
        st.error(f"시트를 열 수 없습니다: {e}")
        st.stop()
else:
    st.stop()

# 3. 데이터 및 기능 함수
def load_setup_data():
    try:
        ws = sh.worksheet("Setup")
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    if not ticker or ticker == "": return 1.0
    try:
        return yf.Ticker(str(ticker).strip()).history(period="1d")['Close'].iloc[-1]
    except: return 0

def get_gpt_english():
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a business English tutor for Byungjoo, a Marketing PM. Provide 3 tech/marketing sentences with Korean translations."}]
    )
    return res.choices[0].message.content

# 4. 메뉴 및 UI
st.sidebar.title("💎 Byungjoo's Hub")
menu = st.sidebar.radio("메뉴 이동", ["📊 자산 통합 관리", "✍️ 영어 공부"])

if menu == "📊 자산 통합 관리":
    st.header("📉 실시간 자산 대시보드")
    df_db = load_setup_data()
    
    if not df_db.empty:
        with st.spinner("데이터 동기화 중..."):
            df_db['현재가'] = df_db['Ticker'].apply(get_live_price)
            df_db['평가금액'] = df_db['현재가'] * df_db['Qty']
            summary = df_db.groupby('Category')['평가금액'].sum().reset_index()
            
            m1, m2 = st.columns([1, 2])
            m1.metric("총 자산 합계", f"{summary['평가금액'].sum():,.0f}원")
            m2.bar_chart(summary.set_index('Category'))
            st.dataframe(df_db[['Category', 'Name', 'Qty', '평가금액']].sort_values(by="평가금액", ascending=False), use_container_width=True)
            
            if st.button("💾 데이터 백업"):
                ws_data = sh.worksheet("Data")
                ws_data.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), "Total", summary['평가금액'].sum()])
                st.success("백업 완료!")
    else:
        st.info("Setup 탭을 확인해주세요.")

elif menu == "✍️ 영어 공부":
    if st.button("오늘의 3문장 생성"):
        st.session_state['eng'] = get_gpt_english()
    if 'eng' in st.session_state:
        st.info(st.session_state['eng'])