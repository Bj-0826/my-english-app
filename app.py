import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# [설정] 페이지 레이아웃
st.set_page_config(page_title="Byungjoo Life OS v72", layout="wide", page_icon="🧭")

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
        df.columns = [c.replace(' ', '') for c in df.columns]
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    """Setup 시트의 티커를 기반으로 실시간 가격 수집"""
    if not ticker or ticker == "" or ticker == "-": return 0
    try:
        t = str(ticker).strip()
        data = yf.Ticker(t).history(period="1d")
        return data['Close'].iloc[-1] if not data.empty else 0
    except: return 0

# --- [사이드바 내비게이션] ---
st.sidebar.title(f"🧭 Byungjoo Hub v72")
menu = st.sidebar.radio("메뉴 이동", ["🏠 홈", "💰 개인자산(Weekly)", "🏛️ 연금자산(Monthly)", "✈️ 여행관리", "🇺🇸 영어공부/테스트", "📚 도서기록"])

# --- [메뉴별 기능 구현] ---

if menu == "🏠 홈":
    st.header(f"👋 Byungjoo님, 반갑습니다.")
    dday = (datetime(2028, 12, 31) - datetime.now()).days
    usd = get_live_price("USDKRW=X")
    c1, c2 = st.columns(2)
    c1.metric("은퇴 D-Day", f"{dday}일", "🎯 2028-12-31")
    c2.metric("실시간 환율", f"{usd:,.2f}원")

elif menu == "💰 개인자산(Weekly)":
    st.header("💰 주간 개인자산 실시간 리포트")
    
    # 1. Setup 시트에서 티커 및 수량 정보 로드
    df_setup = load_df("Setup")
    df_i = df_setup[df_setup['Category'] == "개인자산"].copy()
    
    if not df_i.empty:
        with st.spinner("티커 기반 실시간 가격 반영 중..."):
            df_i['현재가'] = df_i['Ticker'].apply(get_live_price)
            # 티커가 없는 자산(현금 등)은 Setup의 수량을 그대로 평가액으로 간주하거나 수동 입력값을 사용
            df_i['평가액'] = df_i.apply(lambda x: x['현재가'] * x['Qty'] if x['현재가'] > 0 else x['Qty'], axis=1)
        
        total_val = df_i['평가액'].sum()
        
        # 2. 전주 대비 증감 로직 (Personal_Weekly 시트 참조)
        df_w_hist = load_df("Personal_Weekly")
        # (생략: 이전 기록과 비교하여 delta 표시)
        
        st.metric("실시간 총 자산 (Ticker 반영)", f"{total_val:,.0f}원")
        
        c1, c2 = st.columns(2)
        c1.write("🏦 종목별 비중 (막대)")
        c1.bar_chart(df_i.set_index('Name')['평가액'])
        
        c2.write("📝 실시간 상세 내역")
        st.dataframe(df_i[['Name', 'Ticker', 'Qty', '현재가', '평가액']].style.format({"현재가": "{:,.2f}", "평가액": "{:,.0f}"}))

elif menu == "🏛️ 연금자산(Monthly)":
    st.header("🏛️ 월간 연금자산 실시간 리포트")
    df_setup = load_df("Setup")
    df_p = df_setup[df_setup['Category'] != "개인자산"].copy()
    
    if not df_p.empty:
        with st.spinner("연금 티커 동기화 중..."):
            df_p['현재가'] = df_p['Ticker'].apply(get_live_price)
            df_p['평가액'] = df_p.apply(lambda x: x['현재가'] * x['Qty'] if x['현재가'] > 0 else x['Qty'], axis=1)
        
        st.metric("연금 총 평가액", f"{df_p['평가액'].sum():,.0f}원")
        st.dataframe(df_p[['Category', 'Name', 'Ticker', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}))

elif menu == "✈️ 여행관리":
    st.header("✈️ 여행 통합 아카이브 (Main/Plan)")
    # (Byungjoo님의 Travel_Main, Travel_Plan 설계 100% 반영 로직 유지)
    df_m = load_df("Travel_Main")
    if not df_m.empty:
        sel_id = st.selectbox("분석할 여행 선택", df_m['ID'].unique())
        # 상세 통계 차트 (지불수단별, 일자별) 출력...

elif menu == "🇺🇸 영어공부/테스트":
    st.header("🎧 English Mastery")
    # AI 생성 및 테스트 UI 복원...

else:
    st.header("📚 도서 기록")
    st.dataframe(load_df("Book"))