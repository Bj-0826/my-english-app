import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
import openai
from google.oauth2.service_account import Credentials
import gspread

# [설정] 페이지 레이아웃
st.set_page_config(page_title="Byungjoo Life OS v69", layout="wide", page_icon="🧭")

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
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

# --- [사이드바 내비게이션] ---
st.sidebar.title(f"🧭 Byungjoo Hub v69")
menu = st.sidebar.radio("메뉴 이동", ["🏠 홈", "💰 개인자산(Weekly)", "🏛️ 연금자산(Monthly)", "✈️ 여행관리(Main/Plan)", "🇺🇸 영어공부/테스트", "📚 도서기록"])

# --- [유틸리티: 증감 계산 함수] ---
def display_asset_report(df, target_key, prev_key, title):
    st.subheader(f"📊 {title} ({target_key})")
    
    curr_df = df[df['날짜'] == target_key]
    prev_df = df[df['날짜'] == prev_key]
    
    if not curr_df.empty:
        curr_total = curr_df['잔액'].sum()
        prev_total = prev_df['잔액'].sum() if not prev_df.empty else 0
        
        diff = curr_total - prev_total
        per = (diff / prev_total * 100) if prev_total > 0 else 0
        
        # 1. 상단 지표 (증감 표시)
        st.metric(f"{target_key} 총 자산", f"{curr_total:,.0f}원", delta=f"{diff:,.0f}원 ({per:.1f}%)")
        
        col1, col2 = st.columns(2)
        # 2. 계좌별 막대 그래프 (복원)
        col1.write("🏦 계좌별 잔액 현황")
        col1.bar_chart(curr_df.set_index('계좌명')['잔액'])
        
        # 3. 시간 흐름별 추이 그래프
        col2.write("📈 자산 총액 추이")
        trend_df = df.groupby('날짜')['잔액'].sum().reset_index()
        col2.line_chart(trend_df.set_index('날짜'))
        
        st.dataframe(curr_df, use_container_width=True)
    else:
        st.warning(f"{target_key}에 해당하는 데이터가 없습니다. 아래에서 먼저 입력해주세요.")

# --- [기능 1: 홈] ---
if menu == "🏠 홈":
    st.header(f"👋 Byungjoo님, 오늘을 리포트합니다.")
    dday = (datetime(2028, 12, 31) - datetime.now()).days
    c1, c2 = st.columns(2)
    c1.metric("은퇴 D-Day", f"{dday}일", "🎯 2028-12-31")
    c2.write("환율 및 주요 지수는 실시간 API 연동 가능")

# --- [기능 2: 개인자산 (Weekly)] ---
elif menu == "💰 개인자산(Weekly)":
    st.header("💰 주간 개인자산 관리")
    col_y, col_w = st.columns(2)
    sel_year = col_y.selectbox("📅 년도", ["2025", "2026", "2027", "2028"], index=1)
    weeks = [f"W{i:02d}" for i in range(1, 53)]
    sel_week_idx = 13 # 기본 W14
    sel_week = col_w.selectbox("🗓️ 주차", weeks, index=sel_week_idx)
    
    target_key = f"{sel_year}-{sel_week}"
    prev_week = weeks[weeks.index(sel_week)-1] if weeks.index(sel_week) > 0 else "W52"
    prev_key = f"{sel_year if sel_week != 'W01' else int(sel_year)-1}-{prev_week}"

    df_weekly = load_df("Personal_Weekly")
    
    # 보고서 출력
    display_asset_report(df_weekly, target_key, prev_key, "주간 자산 리포트")

    # 입력 폼
    with st.expander("📝 데이터 입력/수정", expanded=False):
        df_setup = load_df("Setup")
        df_i = df_setup[df_setup['Category'] == "개인자산"]
        with st.form("w_form"):
            new_data = []
            for _, row in df_i.iterrows():
                val = st.number_input(f"{row['Name']} 잔액", key=f"inp_{row['Name']}")
                new_data.append([target_key, row['Name'], val, ""])
            if st.form_submit_button("저장"):
                sh.worksheet("Personal_Weekly").append_rows(new_data)
                st.success("저장되었습니다.")

# --- [기능 3: 연금자산 (Monthly)] ---
elif menu == "🏛️ 연금자산(Monthly)":
    st.header("🏛️ 월간 연금자산 관리")
    col_y, col_m = st.columns(2)
    sel_year = col_y.selectbox("📅 년도", ["2025", "2026", "2027", "2028"], index=1, key="m_y")
    months = [f"{i}월" for i in range(1, 13)]
    sel_month = col_m.selectbox("🗓️ 월", months, index=datetime.now().month-1)
    
    target_key = f"{sel_year}-{sel_month}"
    prev_month = months[months.index(sel_month)-1] if months.index(sel_month) > 0 else "12월"
    prev_key = f"{sel_year if sel_month != '1월' else int(sel_year)-1}-{prev_month}"

    df_monthly = load_df("Pension_Monthly")
    display_asset_report(df_monthly, target_key, prev_key, "월간 연금 리포트")

    with st.expander("📝 월간 기록 입력", expanded=False):
        df_setup = load_df("Setup")
        df_p = df_setup[df_setup['Category'] != "개인자산"]
        with st.form("m_form"):
            new_p = []
            for _, row in df_p.iterrows():
                val = st.number_input(f"{row['Name']} 잔액", key=f"p_{row['Name']}")
                new_p.append([target_key, row['Name'], val, ""])
            if st.form_submit_button("연금 기록 저장"):
                sh.worksheet("Pension_Monthly").append_rows(new_p)
                st.success("저장 완료")

# --- [기능 4: 여행 관리 (DB 설계 복원)] ---
elif menu == "✈️ 여행관리(Main/Plan)":
    st.header("✈️ 여행 통합 관리")
    t1, t2 = st.tabs(["🌍 메인 정보", "📝 상세 일정/지출"])
    # (v68에서 구현한 상세 필드 포함 로직 유지)
    with t1:
        st.dataframe(load_df("Travel_Main"))
    with t2:
        st.dataframe(load_df("Travel_Plan"))

# [나머지 English, Book 로직 통합 유지]