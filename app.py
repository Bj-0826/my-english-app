import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Pro v3.9.3", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().replace(' ', '')
        year = int(w_key[1:5])
        week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 ({w_key})"
    except: return w_key

def load_data_safe(s_name):
    try:
        # TTL=0으로 실시간 데이터 로드
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        
        # [핵심] 헤더 양 끝 공백 제거 및 소문자화 (매우 중요)
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if s_name in ["Data", "PersonalData"]:
            # 'amount' 컬럼이 있는지 확인 후 전처리
            if 'amount' in df.columns:
                # 숫자가 아닌 문자(콤마, 공백 등) 제거 후 강제 숫자 변환
                df['amount'] = df['amount'].astype(str).str.replace(r'[^\d.]', '', regex=True)
                df['amount'] = pd.to_numeric(df['amount'], errors='coerce').fillna(0)
            if 'date' in df.columns:
                df['date'] = df['date'].astype(str).str.upper().str.strip()
                
        elif s_name == "Sheet1":
            # 영어 공부 탭 필수 컬럼 보장
            if 'memorized' not in df.columns:
                df['memorized'] = False
            else:
                df['memorized'] = df['memorized'].astype(str).str.strip().str.capitalize() == "True"
        return df
    except Exception as e:
        # 에러 메시지를 구체적으로 찍어서 원인 파악
        st.error(f"'{s_name}' 시트 처리 중 오류: {str(e)}")
        return pd.DataFrame()

# --- [메인 사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.9.3")
    menu = st.sidebar.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [자산 리포트 출력 함수] ---
def show_asset_dashboard(df, date_label_func=lambda x: x):
    if not df.empty and 'date' in df.columns and 'amount' in df.columns:
        all_dates = sorted(df['date'].unique())
        recent_dates = all_dates[-3:] if len(all_dates) >= 3 else all_dates
        df_recent = df[df['date'].isin(recent_dates)]
        
        # 합계 및 증감 계산
        m_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
        cur = m_total.iloc[-1]['amount']
        prev = m_total.iloc[-2]['amount'] if len(m_total) > 1 else cur
        diff = cur - prev
        
        c1, c2 = st.columns(2)
        c1.metric(f"{date_label_func(recent_dates[-1])} 합계", f"{int(cur):,}원")
        c2.metric("이전 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
        
        # 그래프
        fig = go.Figure()
        for acc in sorted(df_recent['account'].unique()):
            acc_df = df_recent[df_recent['account'] == acc]
            fig.add_trace(go.Bar(x=[date_label_func(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
        fig.update_layout(barmode='stack', xaxis_type='category', height=400)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("표시할 데이터가 없습니다.")

# --- [메인 로직] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (Data)")
    df_p = load_data_safe("Data")
    show_asset_dashboard(df_p)

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리 (PersonalData)")
    df_per = load_data_safe("PersonalData")
    show_asset_dashboard(df_per, date_label_func=get_w_label_python)

else:
    st.header("🔤 영어 공부 (Sheet1)")
    df_en = load_data_safe("Sheet1")
    if not df_en.empty:
        st.dataframe(df_en, use_container_width=True)
    else:
        st.info("데이터가 없습니다.")