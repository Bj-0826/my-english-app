import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# 1. 시스템 설정 (확장성 & 직관성 중심)
st.set_page_config(page_title="Byungjoo Life OS v60", layout="wide", page_icon="🧭")

@st.cache_resource
def get_gc():
    """구글 시트 연결 엔진 (Secrets의 connections 섹션 참조)"""
    try:
        # 가독성과 연결 안정성을 위해 connections 섹션으로 통일
        creds_info = st.secrets["connections"]
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"연결 설정 에러: Secrets 항목을 확인해주세요. ({e})")
        return None

gc = get_gc()

# 시트 인스턴스 생성 (안전한 에러 핸들링)
if gc:
    try:
        target_url = st.secrets["connections"].get("spreadsheet", "https://docs.google.com/spreadsheets/d/1puWzFplStYrixwCHTyvC0NDWw1N-YacA1XkZOCaM6Jk/edit")
        sh = gc.open_by_url(target_url)
    except Exception as e:
        st.error(f"시트 로드 실패: {e}")
        st.stop()
else:
    st.stop()

# 2. 공통 유틸리티 함수
def load_data(sheet_name):
    try:
        ws = sh.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    """실시간 주가 및 환율 수집 (Yahoo Finance)"""
    if not ticker or ticker == "": return 1.0
    try:
        clean_ticker = str(ticker).strip()
        return yf.Ticker(clean_ticker).history(period="1d")['Close'].iloc[-1]
    except: return 0

def get_ai_english():
    """GPT-4o 기반 비즈니스 영어 생성"""
    client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    res = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "You are a business English tutor for Byungjoo, a Marketing PM. Provide 3 tech/marketing sentences with Korean translations."}]
    )
    return res.choices[0].message.content

# --- 3. 사이드바 내비게이션 (슈퍼 앱 구조) ---
st.sidebar.title("🧭 Byungjoo Hub")
menu = st.sidebar.radio(
    "서비스 이동", 
    ["🏠 홈 대시보드", "🏛️ 연금 자산 (Monthly)", "💰 개인 자산 (Weekly)", "🇺🇸 영어 공부", "✈️ 여행 기록", "📚 도서 관리"]
)

# --- 4. 메뉴별 기능 구현 ---

# [메뉴 1: 홈 대시보드]
if menu == "🏠 홈 대시보드":
    st.header(f"👋 Byungjoo님, 오늘의 브리핑입니다.")
    
    # 은퇴 D-Day (기존 GAS 핵심 로직 반영)
    target_date = datetime(2028, 12, 31)
    dday = (target_date - datetime.now()).days
    usd_krw = get_live_price("USDKRW=X")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("은퇴 D-Day", f"{dday}일", "📅 2028.12.31")
    c2.metric("실시간 환율 (USD/KRW)", f"{usd_krw:,.2f}원")
    c3.metric("오늘의 날짜", datetime.now().strftime("%Y-%m-%d"))
    
    st.divider()
    st.subheader("📌 바로가기")
    st.info("왼쪽 메뉴를 통해 자산 관리 및 기록을 시작하세요.")

# [메뉴 2: 연금 자산 (월간 관리)]
elif menu == "🏛️ 연금 자산 (Monthly)":
    st.header("🏛️ 연금 자산 관리 (Monthly Update)")
    st.caption("연금 계좌는 월 1회 수량 점검 및 기록 확정을 권장합니다.")
    
    df_setup = load_data("Setup")
    df_p = df_setup[df_setup['Category'] != "개인자산"]
    
    if not df_p.empty:
        with st.spinner("가격을 업데이트 중입니다..."):
            df_p['현재가'] = df_p['Ticker'].apply(get_live_price)
            df_p['평가액'] = df_p['현재가'] * df_p['Qty']
            total_p = df_p['평가액'].sum()
            
            st.metric("연금 자산 총액", f"{total_p:,.0f}원")
            st.dataframe(df_p[['Category', 'Name', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}), use_container_width=True)
            
            if st.button("💾 이번 달 연금 기록 확정 (백업)"):
                ws_data = sh.worksheet("Data")
                ws_data.append_row([datetime.now().strftime("%Y-%m-%d"), "Pension_Total", total_p])
                st.success("시트(Data 탭)에 성공적으로 저장되었습니다.")
    else: st.warning("Setup 탭에 연금 자산 데이터를 입력해주세요.")

# [메뉴 3: 개인 자산 (주간 관리)]
elif menu == "💰 개인 자산 (Weekly)":
    st.header("💰 개인 투자 자산 관리 (Weekly Update)")
    st.caption("주식 및 현금성 자산은 매주 변동성을 확인하고 수량을 업데이트하세요.")
    
    df_setup = load_data("Setup")
    df_i = df_setup[df_setup['Category'] == "개인자산"]
    
    if not df_i.empty:
        df_i['현재가'] = df_i['Ticker'].apply(get_live_price)
        df_i['평가액'] = df_i['현재가'] * df_i['Qty']
        total_i = df_i['평가액'].sum()
        
        st.metric("개인 자산 총액 (Live)", f"{total_i:,.0f}원")
        st.dataframe(df_i[['Name', 'Ticker', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}), use_container_width=True)
    else: st.info("개인자산 데이터가 없습니다. Setup 탭의 Category를 확인하세요.")

# [메뉴 4: 영어 공부]
elif menu == "🇺🇸 영어 공부":
    st.header("🎧 Business English Tutor")
    if st.button("🤖 AI 3문장 생성하기"):
        with st.spinner("AI가 문장을 구성 중..."):
            st.session_state['today_eng'] = get_ai_eng()
    
    if 'today_eng' in st.session_state:
        st.info(st.session_state['today_eng'])
        
    with st.form("eng_manual"):
        st.write("📝 직접 학습 기록 저장")
        e_in = st.text_input("English")
        k_in = st.text_input("Korean")
        if st.form_submit_button("시트에 저장"):
            sh.worksheet("English").append_row([datetime.now().strftime("%Y-%m-%d"), e_in, k_in])
            st.success("저장 완료!")

# [메뉴 5: 여행 기록]
elif menu == "✈️ 여행 기록":
    st.header("✈️ 나의 여행 아카이브")
    with st.form("travel_form"):
        col1, col2 = st.columns(2)
        t_dest = col1.text_input("목적지")
        t_date = col2.date_input("날짜", datetime.now())
        t_memo = st.text_area("여행의 기억 (맛집, 브랜드, 인사이트)")
        if st.form_submit_button("여행 기록 저장"):
            try:
                sh.worksheet("Travel").append_row([t_date.strftime("%Y-%m-%d"), t_dest, t_memo])
                st.success("새로운 여행이 기록되었습니다!")
            except: st.error("시트에 'Travel' 탭이 없습니다 (날짜, 목적지, 메모 순으로 헤더 작성 필요)")
    
    df_t = load_data("Travel")
    if not df_t.empty:
        st.subheader("최근 여정 리스트")
        st.dataframe(df_t.sort_values(by="날짜", ascending=False), use_container_width=True)

# [메뉴 6: 도서 관리]
else:
    st.header("📚 도서 관리 (준비 중)")
    st.info("다음 업데이트에서 구글 시트의 'Book' 탭과 연동됩니다.")