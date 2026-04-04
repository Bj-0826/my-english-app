import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 페이지 설정 및 보안 로드
st.set_page_config(page_title="Byungjoo Master Hub v52", layout="wide")

try:
    creds_info = st.secrets["connections"]["gsheets"]
    OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1puWzFplStYrixwCHTyvC0NDWw1N-YacA1XkZOCaM6Jk/edit"
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(spreadsheet_url)
except Exception as e:
    st.error("설정 로드 실패! 시트 권한(편집자 초대) 및 Secrets를 확인해주세요.")
    st.stop()

# 2. 데이터 처리 엔진
def load_setup_data():
    """시트의 Setup 탭에서 실시간 종목 리스트 로드"""
    try:
        ws = sh.worksheet("Setup")
        return pd.DataFrame(ws.get_all_records())
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    """Yahoo Finance 실시간 가격 수집"""
    if not ticker or ticker == "": return 1.0 # 펀드는 나중에 보정 기능 추가
    try:
        # 공백 제거 및 문자열 처리
        clean_ticker = str(ticker).strip()
        return yf.Ticker(clean_ticker).history(period="1d")['Close'].iloc[-1]
    except: return 0

def get_gpt_english():
    """AI 영어 3문장 생성 (Business English for PM)"""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a business English tutor for Byungjoo, a Marketing PM. Provide 3 tech/marketing sentences with Korean translations."}]
    )
    return res.choices[0].message.content

# 3. 사이드바 메뉴
st.sidebar.title("💎 Byungjoo's Hub")
menu = st.sidebar.radio("메뉴 이동", ["📊 자산 통합 관리", "✍️ 영어 공부", "📅 여행/도서 기록"])

# 실시간 시트 데이터 로드
df_db = load_setup_data()

if menu == "📊 자산 통합 관리":
    st.header("📉 실시간 자산 대시보드")
    
    if not df_db.empty:
        with st.spinner("실시간 금융 데이터를 동기화 중입니다..."):
            df_db['현재가'] = df_db['Ticker'].apply(get_live_price)
            df_db['평가금액'] = df_db['현재가'] * df_db['Qty']
            
            # 카테고리별 요약
            summary = df_db.groupby('Category')['평가금액'].sum().reset_index()
            total_sum = summary['평가금액'].sum()
            
            # 대시보드 레이아웃
            m1, m2 = st.columns([1, 2])
            m1.metric("총 자산 합계", f"{total_sum:,.0f}원")
            m2.bar_chart(summary.set_index('Category'))
            
            st.subheader("📋 세부 보유 종목 현황")
            # 시인성을 위해 평가금액 내림차순 정렬
            st.dataframe(df_db[['Category', 'Name', 'Ticker', 'Qty', '평가금액']].sort_values(by="평가금액", ascending=False).style.format({"평가금액": "{:,.0f}"}), use_container_width=True)
            
            if st.button("💾 현재 상태를 시트(Data 탭)에 백업"):
                try:
                    ws_data = sh.worksheet("Data")
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    for _, row in summary.iterrows():
                        ws_data.append_row([now, row['Category'], row['평가금액']])
                    st.success(f"{now} 기준 데이터가 백업되었습니다.")
                except:
                    st.error("'Data' 탭을 시트에서 찾을 수 없습니다.")
    else:
        st.info("시트의 'Setup' 탭에 데이터를 입력해주세요. (헤더: Category, Name, Ticker, Qty, Type)")

elif menu == "✍️ 영어 공부":
    st.header("🎧 Business English Tutor")
    tab_ai, tab_manual = st.tabs(["🤖 AI 자동 생성", "📝 직접 기록"])
    
    with tab_ai:
        if st.button("오늘의 3문장 생성하기"):
            with st.spinner("AI가 문장을 구성 중입니다..."):
                st.session_state['eng_text'] = get_gpt_english()
        if 'eng_text' in st.session_state:
            st.info(st.session_state['eng_text'])
            
    with tab_manual:
        with st.form("manual_entry"):
            e_text = st.text_input("English Sentence")
            k_text = st.text_input("한글 번역")
            if st.form_submit_button("시트(English 탭)에 저장"):
                try:
                    sh.worksheet("English").append_row([datetime.now().strftime("%Y-%m-%d"), e_text, k_text])
                    st.success("저장 완료!")
                except:
                    st.error("'English' 탭을 시트에서 찾을 수 없습니다.")

else:
    st.info("📅 여행 기록 및 📚 도서 기록 기능은 다음 업데이트(v53)에서 추가될 예정입니다.")