import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 페이지 설정 및 보안
st.set_page_config(page_title="Byungjoo Master Hub v51", layout="wide")

try:
    creds_info = st.secrets["connections"]["gsheets"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1puWzFplStYrixwCHTyvC0NDWw1N-YacA1XkZOCaM6Jk/edit"
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(spreadsheet_url)
except Exception as e:
    st.error("설정 로드 실패! 시트 권한 및 Secrets(Key값)를 확인해주세요.")
    st.stop()

# 2. 데이터 처리 엔진
def load_setup_data():
    """Setup 탭에서 보유 종목 리스트 로드"""
    try:
        ws = sh.worksheet("Setup")
        return pd.DataFrame(ws.get_all_records())
    except:
        st.warning("'Setup' 탭에 데이터가 없거나 형식이 맞지 않습니다.")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    """Yahoo Finance 실시간 가격 수집"""
    if not ticker or ticker == "": return 1.0 # 펀드는 나중에 단가 보정 기능 추가 예정
    try:
        # 한국 종목(.KS, .KQ) 및 미국 종목 호환
        return yf.Ticker(str(ticker)).history(period="1d")['Close'].iloc[-1]
    except: return 0

def get_gpt_english():
    """AI 영어 3문장 생성"""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a business English tutor for Byungjoo, a Marketing PM. Provide 3 tech/marketing sentences with Korean translations."}]
    )
    return res.choices[0].message.content

# 3. 사이드바 및 메뉴
st.sidebar.title("💎 Byungjoo's Hub")
menu = st.sidebar.radio("메뉴 이동", ["📊 자산 통합 관리", "✍️ 영어 공부", "📅 여행/도서 기록"])

# 실시간 DB 로드
df_db = load_setup_data()

if menu == "📊 자산 통합 관리":
    st.header("📉 실시간 자산 대시보드")
    
    if not df_db.empty:
        with st.spinner("실시간 가격 정보를 가져오는 중..."):
            df_db['현재가'] = df_db['Ticker'].apply(get_live_price)
            df_db['평가금액'] = df_db['현재가'] * df_db['Qty']
            
            # 요약 데이터
            summary = df_db.groupby('Category')['평가금액'].sum().reset_index()
            total_sum = summary['평가금액'].sum()
            
            # 대시보드 레이아웃
            m1, m2 = st.columns([1, 2])
            m1.metric("총 자산 합계", f"{total_sum:,.0f}원")
            m2.bar_chart(summary.set_index('Category'))
            
            st.subheader("📋 세부 보유 종목 현황")
            st.dataframe(df_db[['Category', 'Name', 'Ticker', 'Qty', '평가금액']].style.format({"평가금액": "{:,.0f}", "현재가": "{:,.2f}"}), use_container_width=True)
            
            if st.button("💾 현재 상태를 'Data' 시트에 백업 (월말 기록용)"):
                ws_data = sh.worksheet("Data")
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                for _, row in summary.iterrows():
                    ws_data.append_row([now, row['Category'], row['평가금액']])
                st.success(f"{now} 기준 데이터가 시트에 기록되었습니다.")
    else:
        st.info("시트의 'Setup' 탭에 종목 정보를 입력해주세요.")

elif menu == "✍️ 영어 공부":
    st.header("🎧 Business English Tutor")
    tab_ai, tab_manual = st.tabs(["🤖 AI 자동 생성", "📝 직접 기록"])
    
    with tab_ai:
        if st.button("오늘의 3문장 생성하기"):
            st.session_state['eng_text'] = get_gpt_english()
        if 'eng_text' in st.session_state:
            st.info(st.session_state['eng_text'])
            
    with tab_manual:
        with st.form("manual_entry"):
            e_text = st.text_input("English")
            k_text = st.text_input("Korean")
            if st.form_submit_button("시트에 저장"):
                sh.worksheet("English").append_row([datetime.now().strftime("%Y-%m-%d"), e_text, k_text])
                st.success("입력한 문장이 시트에 저장되었습니다.")

else:
    st.info("여행 및 도서 기록 기능은 다음 업데이트에서 연결될 예정입니다.")