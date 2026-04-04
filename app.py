import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# [1] 기본 설정
st.set_page_config(page_title="Byungjoo Life OS v74", layout="wide", page_icon="🧭")

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
        df.columns = [c.replace(' ', '') for c in df.columns] # 헤더 공백 처리
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_live_price(ticker):
    if not ticker or ticker in ["", "-"]: return 0
    try:
        data = yf.Ticker(str(ticker).strip()).history(period="1d")
        return data['Close'].iloc[-1] if not data.empty else 0
    except: return 0

# --- [사이드바 메뉴] ---
st.sidebar.title("🧭 Byungjoo Hub v74")
menu = st.sidebar.radio("서비스 이동", ["🏠 홈", "💰 개인자산(Weekly)", "🏛️ 연금자산(Monthly)", "✈️ 여행관리(Main/Plan)", "🇺🇸 영어공부/테스트", "📚 도서기록"])

# --- [메뉴 1: 홈] ---
if menu == "🏠 홈":
    st.header("👋 Byungjoo님, 오늘을 리포트합니다.")
    dday = (datetime(2028, 12, 31) - datetime.now()).days
    usd = get_live_price("USDKRW=X")
    c1, c2 = st.columns(2)
    c1.metric("은퇴 D-Day", f"{dday}일", "🎯 2028-12-31")
    c2.metric("실시간 환율 (USD)", f"{usd:,.2f}원")

# --- [메뉴 2: 개인자산 (Weekly + Ticker)] ---
elif menu == "💰 개인자산(Weekly)":
    st.header("💰 주간 개인자산 리포트")
    
    col_y, col_w = st.columns(2)
    sel_y = col_y.selectbox("년도", ["2025", "2026", "2027", "2028"], index=1)
    weeks = [f"W{i:02d}" for i in range(1, 53)]
    sel_w = col_w.selectbox("주차", weeks, index=13)
    target_key = f"{sel_y}-{sel_w}"
    
    # 1. 실시간 가격 반영 (Setup 기반)
    df_s = load_df("Setup")
    df_i = df_s[df_s['Category'] == "개인자산"].copy()
    
    if not df_i.empty:
        df_i['현재가'] = df_i['Ticker'].apply(get_live_price)
        df_i['평가액'] = df_i.apply(lambda x: x['현재가'] * x['Qty'] if x['현재가'] > 0 else x['Qty'], axis=1)
        curr_total = df_i['평가액'].sum()
        
        # 2. 전주 대비 증감 (%)
        df_w_hist = load_df("Personal_Weekly")
        prev_idx = weeks.index(sel_w) - 1
        prev_key = f"{sel_y}-{weeks[prev_idx]}" if prev_idx >= 0 else ""
        
        prev_total = 0
        if not df_w_hist.empty:
            p_data = df_w_hist[df_w_hist['날짜'].astype(str) == prev_key]
            prev_total = pd.to_numeric(p_data['잔액'], errors='coerce').sum()
            
        diff = curr_total - prev_total
        per = (diff / prev_total * 100) if prev_total > 0 else 0
        
        st.metric(f"{target_key} 실시간 총 자산", f"{curr_total:,.0f}원", delta=f"{diff:,.0f}원 ({per:.1f}%)")
        
        ca, cb = st.columns(2)
        ca.write("🏦 종목별 잔액 (막대)")
        ca.bar_chart(df_i.set_index('Name')['평가액'])
        cb.write("📉 자산 상세 내역")
        st.dataframe(df_i[['Name', 'Ticker', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}))

# --- [메뉴 3: 연금자산 (Monthly + Ticker)] ---
elif menu == "🏛️ 연금자산(Monthly)":
    st.header("🏛️ 월간 연금자산 관리")
    cy, cm = st.columns(2)
    sel_y = cy.selectbox("년도", ["2025", "2026", "2027", "2028"], index=1, key="py")
    sel_m = cm.selectbox("월", [f"{i}월" for i in range(1, 13)], index=datetime.now().month-1)
    
    df_s = load_df("Setup")
    df_p = df_s[df_s['Category'] != "개인자산"].copy()
    df_p['현재가'] = df_p['Ticker'].apply(get_live_price)
    df_p['평가액'] = df_p.apply(lambda x: x['현재가'] * x['Qty'] if x['현재가'] > 0 else x['Qty'], axis=1)
    
    st.metric(f"{sel_m} 연금 총 평가액", f"{df_p['평가액'].sum():,.0f}원")
    st.dataframe(df_p[['Category', 'Name', 'Ticker', 'Qty', '평가액']].style.format({"평가액": "{:,.0f}"}))

# --- [메뉴 4: 여행 관리 (스키마 100% 반영)] ---
elif menu == "✈️ 여행관리(Main/Plan)":
    st.header("✈️ 여행 통합 분석 리포트")
    df_m = load_df("Travel_Main")
    df_p = load_df("Travel_Plan")
    
    if not df_m.empty:
        sel_id = st.selectbox("🎯 여행지 선택", df_m['ID'].unique())
        m_row = df_m[df_m['ID'] == sel_id].iloc[0]
        p_rows = df_p[df_p['여행ID'].astype(str) == str(sel_id)]
        
        spent = pd.to_numeric(p_rows['실제지출'], errors='coerce').sum()
        budget = pd.to_numeric(m_row['총예산'], errors='coerce')
        
        c1, c2, c3 = st.columns(3)
        c1.metric("여행지", m_row['여행지'])
        c2.metric("총 예산", f"{budget:,.0f}원")
        c3.metric("현재 총 지출", f"{spent:,.0f}원", delta=f"{budget-spent:,.0f}원 남음")
        
        if not p_rows.empty:
            st.divider()
            col_a, col_b = st.columns(2)
            col_a.write("📅 날짜별 지출 추이")
            col_a.line_chart(p_rows.groupby('날짜')['실제지출'].sum())
            col_b.write("💳 지불수단별 비중 (현금/카드)")
            col_b.bar_chart(p_rows.groupby('지불수단')['실제지출'].sum())
            st.dataframe(p_rows, use_container_width=True)

# --- [메뉴 5: 영어 공부 & 테스트] ---
elif menu == "🇺🇸 영어공부/테스트":
    st.header("🎧 English Mastery")
    if st.button("🤖 AI 오늘의 비즈니스 영어 생성"):
        client = openai.OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role":"system","content":"Marketing PM Business English 3 sentences"}])
        st.session_state['eng_v74'] = res.choices[0].message.content
    
    if 'eng_v74' in st.session_state:
        st.success("오늘의 문장")
        st.write(st.session_state['eng_v74'])
        st.divider()
        st.subheader("📝 복습 테스트 (가리고 입력)")
        ans = st.text_area("Answer here...")
        if st.button("제출 및 저장"):
            sh.worksheet("English").append_row([datetime.now().strftime("%Y-%m-%d"), "Review", ans, "완료"])
            st.success("기록 완료!")

else:
    st.header("📚 도서 기록")
    st.dataframe(load_df("Book"))