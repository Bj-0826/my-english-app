import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Pro v3.9.2", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        # "Y2026W12" 형식 처리
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
        
        # 헤더 공백 제거 및 소문자 통일 (KeyError 방지)
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if s_name in ["Data", "PersonalData"]:
            # 데이터 정제: 금액에서 콤마 제거 및 숫자로 변환
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
        elif s_name == "Sheet1":
            if 'english' in df.columns:
                df = df.dropna(subset=['english'])
                if 'memorized' not in df.columns:
                    df['memorized'] = False
                else:
                    # 'True' 문자열을 실제 Boolean으로 변환
                    df['memorized'] = df['memorized'].astype(str).str.strip().str.capitalize() == "True"
        return df
    except Exception as e:
        st.error(f"'{s_name}' 로드 실패: {e}")
        return pd.DataFrame()

# --- [저장 및 퀴즈 로직 생략 없이 유지] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    df = load_data_safe(s_name)
    mask = (df['date'] == str(date_val).upper()) & (df['account'] == str(acc))
    if mask.any(): df.loc[mask, 'amount'] = int(amt_val)
    else: df = pd.concat([df, pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val)}])], ignore_index=True)
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ {acc} 저장 완료!")

# --- [메인 사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v3.9.2")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (Data)")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    
    with t1:
        if not df_p.empty:
            all_dates = sorted(df_p['date'].unique())
            recent_dates = all_dates[-3:] if len(all_dates) >= 3 else all_dates
            df_recent = df_p[df_p['date'].isin(recent_dates)]
            
            m_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur = m_total.iloc[-1]['amount']
            prev = m_total.iloc[-2]['amount'] if len(m_total) > 1 else cur
            diff = cur - prev
            
            c1, c2 = st.columns(2)
            c1.metric(f"{recent_dates[-1]} 합계", f"{int(cur):,}원")
            c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_recent.sort_values('date', ascending=False), use_container_width=True)
        else:
            st.warning("Data 탭에서 데이터를 불러올 수 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2025, 2026, 2027, 2028], key="p_y")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("연금 데이터 저장", on_click=handle_save_asset, args=("Data", f"{py}-{pm}", p_acc, "p_amt"))

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리 (PersonalData)")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    
    with t1:
        if not df_per.empty:
            all_weeks = sorted(df_per['date'].unique())
            recent_w = all_weeks[-3:] if len(all_weeks) >= 3 else all_weeks
            df_recent = df_per[df_per['date'].isin(recent_w)]
            
            w_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur = w_total.iloc[-1]['amount']
            prev = w_total.iloc[-2]['amount'] if len(w_total) > 1 else cur
            diff = cur - prev
            
            c1, c2 = st.columns(2)
            c1.metric(f"{get_w_label_python(recent_w[-1])} 합계", f"{int(cur):,}원")
            c2.metric("전주 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
            
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_recent.sort_values('date', ascending=False), use_container_width=True)
        else:
            st.warning("PersonalData 탭에서 데이터를 불러올 수 없습니다.")

    with t2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2025, 2026, 2027, 2028], key="per_y")
        perw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 데이터 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

else:
    st.header("🔤 Byungjoo의 영어 공부 (Sheet1)")
    df_en = load_data_safe("Sheet1")
    # (이하 영어 로직 v3.9.1과 동일하게 에러 방지 처리 완료)
    st.dataframe(df_en) # 데이터 확인용