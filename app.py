import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.title("🔍 시스템 연결 진단 모드")

# 1. Secrets 구조 확인
if "connections" not in st.secrets:
    st.error("❌ 에러: Secrets에 [connections.gsheets] 섹션이 없습니다.")
else:
    st.success("✅ 1단계: Secrets 섹션 로드 성공")

# 2. 구글 시트 연결 시도
try:
    creds_info = st.secrets["connections"]["gsheets"]
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    gc = gspread.authorize(creds)
    
    # 시트 열기 시도
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1puWzFplStYrixwCHTyvC0NDWw1N-YacA1XkZOCaM6Jk/edit"
    sh = gc.open_by_url(spreadsheet_url)
    st.success(f"✅ 2단계: 구글 시트 연결 성공! ({sh.title})")
    
    # Setup 탭 확인
    ws = sh.worksheet("Setup")
    st.success("✅ 3단계: 'Setup' 탭 확인 완료!")
    
except Exception as e:
    st.error(f"❌ 에러 발생 상세: {e}")
    st.info("💡 팁: 구글 시트 우측 상단 [공유] 버튼을 눌러 서비스 계정 이메일을 '편집자'로 추가했는지 확인하세요.")