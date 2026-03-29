import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go

# 1. 앱 설정 및 제목
st.set_page_config(page_title="Byungjoo Pro v3.8", layout="wide")
st.title("Byungjoo 통합 매니저 Pro")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [도우미 함수: 자산 로직 전수 검토 완료] ---
def get_w_label_python(w_key):
    try:
        w_key = str(w_key).upper().strip()
        year = int(w_key[1:5]); week_num = int(w_key.split('W')[1])
        d = datetime.date(year, 1, 1) + datetime.timedelta(weeks=week_num-1)
        return f"{d.month}월 {((d.day-1)//7)+1}주 (W{week_num})"
    except: return w_key

def load_data_safe(s_name):
    """자산/영어 데이터를 실시간(ttl=0)으로 안전하게 읽어옵니다."""
    try:
        df = conn.read(worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        df = df.dropna(how='all')
        
        if s_name in ["Data", "PersonalData"]:
            df = df.dropna(subset=['date', 'account'])
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['date'] = df['date'].astype(str).str.upper().str.strip()
            df['account'] = df['account'].astype(str).str.strip()
        elif s_name == "Sheet1":
            df = df.dropna(subset=['english'])
            # 데이터 정규화: False, True 문자열로 고정
            df['memorized'] = df['memorized'].astype(str).str.capitalize()
        return df
    except Exception as e:
        return pd.DataFrame()

# --- [통합 저장 로직: 자산 중복 제거 로직 전수 검토] ---
def handle_save_integrated(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0:
        st.warning("금액을 입력해주세요.")
        return

    # 저장 전 데이터 다시 로드 (실시간성 확보)
    df = load_data_safe(s_name)
    date_val = str(date_val).upper().strip()
    acc = str(acc).strip()
    
    # 중복 체크 (js v43 동일 로직)
    mask = (df['date'] == date_val) & (df['account'] == acc)
    if mask.any():
        df.loc[mask, 'amount'] = int(amt_val) # 기존 데이터 수정
    else:
        new_row = pd.DataFrame([{"date": date_val, "account": acc, "amount": int(amt_val), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True) # 신규 추가
    
    conn.update(worksheet=s_name, data=df)
    st.session_state[amt_key] = 0 # 입력창 초기화
    st.toast(f"✅ [{acc}] 저장 및 업데이트 완료!", icon="💰")

def handle_save_english():
    """영어 문장 추가 및 입력창 초기화"""
    en, ko = st.session_state.new_en, st.session_state.new_ko
    if en and ko:
        df_en = load_data_safe("Sheet1")
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": "False"}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(worksheet="Sheet1", data=df_en)
        # 입력창 초기화
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✍️ 영어 문장 추가 완료!")
        st.rerun()

# --- [핵심 수정: 암기완료 버그 해결] ---
def mark_as_memorized(en_text):
    """특정 문장을 '암기완료'로 시트에 실시간 업데이트"""
    df_en = load_data_safe("Sheet1")
    # 영어 문장 텍스트로 행을 찾아 True로 변경
    mask = df_en['english'] == en_text
    if mask.any():
        df_en.loc[mask, 'memorized'] = "True"
        conn.update(worksheet="Sheet1", data=df_en)
        st.toast(f"✅ 암기 완료! {en_text[:10]}...", icon="✨")
        # 즉시 새로고침하여 퀴즈 및 리스트에 반영
        st.rerun()

def next_quiz_question():
    """퀴즈 문제 및 입력창 초기화"""
    if 'q_idx' in st.session_state: del st.session_state.q_idx
    if 'q_in' in st.session_state: st.session_state.q_in = ""

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.markdown("### 📅 D-Day 관리")
    menu = st.radio("메뉴 이동", ["💰 연금자산", "💵 개인자산", "🔤 영어공부"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직] ---

# 1. 연금자산
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리 (최근 3개월)")
    df_p = load_data_safe("Data")
    tab1, tab2 = st.tabs(["📊 대시보드", "📝 데이터 입력/수정"])
    with tab1:
        if not df_p.empty:
            recent_dates = sorted(df_p['date'].unique())[-3:]
            df_recent = df_p[df_p['date'].isin(recent_dates)]
            m_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_val = m_total.iloc[-1]['amount']
            prev_val = m_total.iloc[-2]['amount'] if len(m_total)>1 else m_total.iloc[-1]['amount']
            diff = cur_val - prev_val
            diff_per = (diff / prev_val * 100) if prev_val != 0 else 0
            
            c1, col_delta = st.columns(2)
            c1.metric(f"{recent_dates[-1]} 합계", f"{int(cur_val):,}원")
            col_delta.metric("지난달 대비 증감", f"{diff_per:+.1f}%", f"{int(diff):+,}원")
            
            # 그래프 (툴팁 최적화)
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_recent[df_recent['account'] == acc]
                fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', xaxis_type='category', height=400, margin=dict(t=20, b=20, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    with tab2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2026, 2027, 2028], key="py_v29")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="pm_v29")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="pa_v29")
        st.number_input("금액(원)", step=100000, key="p_amt_v29")
        st.button("연금 저장", on_click=handle_save_integrated, args=("Data", f"{py}-{pm}", p_acc, "p_amt_v29"))

# 2. 개인자산
elif menu == "💵 개인자산 관리":
    st.header("💵 개인자산 관리 (최근 3주)")
    df_per = load_data_safe("PersonalData")
    tab1, tab2 = st.tabs(["📊 주간 대시보드", "📝 데이터 입력/수정"])
    with tab1:
        if not df_per.empty:
            recent_w = sorted(df_per['date'].unique())[-3:]
            df_recent = df_per[df_per['date'].isin(recent_w)]
            w_total = df_recent.groupby('date')['amount'].sum().reset_index().sort_values('date')
            cur_w_val = w_total.iloc[-1]['amount']
            prev_w_val = w_total.iloc[-2]['amount'] if len(w_total)>1 else w_total.iloc[-1]['amount']
            w_diff = cur_w_val - prev_w_val
            w_diff_per = (w_diff / prev_w_val * 100) if prev_w_val != 0 else 0
            
            c1, col_delta = st.columns(2)
            c1.metric(f"{get_w_label_python(recent_w[-1])} 합계", f"{int(cur_w_val):,}원")
            col_delta.metric("지난주 대비 증감", f"{w_diff_per:+.1f}%", f"{int(w_diff):+,}원")
            
            fig = go.Figure()
            for acc in sorted(df_recent['account'].unique()):
                acc_df = df_per[df_per['account'] == acc].sort_values('date').tail(3)
                fig.add_trace(go.Bar(x=[get_w_label_python(d) for d in acc_df['date']], y=acc_df['amount'], name=acc, hovertemplate="<b>%{fullData.name}</b><br>금액: %{y:,.0f}원<extra></extra>"))
            fig.update_layout(barmode='stack', xaxis_type='category', height=450, margin=dict(t=20, b=20, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    with tab2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2026, 2027, 2028], key="pery_v29")
        perw = c2.number_input("주차(Week)", 1, 53, 13, key="perw_v29")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'], key="per_acc_v29")
        st.number_input("금액(원)", step=10000, key="per_amt_v29")
        st.button("개인자산 저장", on_click=handle_save_integrated, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt_v29"))

# 3. 영어 공부 (UI 최적화 및 복구 완료)
else:
    st.header("🔤 Byungjoo의 영어 공부 공간")
    df_en = load_data_safe("Sheet1")
    
    # UI 최적화: 암기 상태 변경 탭을 따로 분리
    tab_list, tab_memorize, tab_input, tab_quiz = st.tabs(["📖 저장된 문장", "✨ 암기 상태 변경", "✍️ 문장 입력", "🧠 퀴즈 테스트"])
    
    with tab_list:
        if not df_en.empty:
            # 여백 없이 깔끔한 데이터프레임으로 복귀 (js v43 스타일)
            st.dataframe(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True)
        else: st.info("문장이 없습니다.")

    with tab_memorize:
        if not df_en.empty:
            st.subheader("외운 문장은 [암기완료 ✅] 버튼을 눌러 졸업시켜 주세요!")
            st.divider()
            # 미암기(False) 문장만 필터링해서 버튼과 함께 표시
            unmemorized = df_en[df_en['memorized'] == "False"]
            
            if not unmemorized.empty:
                for idx, row in unmemorized.iloc[::-1].iterrows():
                    c1, c2 = st.columns([6, 1])
                    c1.write(f"**{row['english']}**<br>{row['korean']}", unsafe_allow_html=True)
                    # 영어 문장을 인자로 전달하여 정확히 매칭
                    if c2.button("암기완료 ✅", key=f"mem_{row['english'][:10]}"):
                        mark_as_memorized(row['english'])
                    st.divider()
            else: st.success("🎉 모든 문장을 다 외우셨습니다! 멋져요!")
        else: st.info("데이터가 없습니다.")
            
    with tab_input:
        st.subheader("새로운 영어 문장 추가")
        st.text_input("영어 문장", key="new_en")
        st.text_input("한글 뜻", key="new_ko")
        st.button("문장 저장", on_click=handle_save_english)

    with tab_quiz:
        if not df_en.empty:
            # 암기 안 된(False) 문장만 퀴즈 출제
            unmemorized_quiz = df_en[df_en['memorized'] == "False"]
            if not unmemorized_quiz.empty:
                if 'q_idx' not in st.session_state or st.session_state.q_idx not in unmemorized_quiz.index:
                    st.session_state.q_idx = unmemorized_quiz.sample(n=1).index[0]
                q = unmemorized_quiz.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력하세요", key="q_in")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("정답 확인"):
                        if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답입니다!"); st.balloons()
                        else: st.error(f"오답입니다. 정답: {q['english']}")
                with c2: st.button("다음 문제", on_click=next_quiz_question)
            else: st.success("모든 문장을 암기 완료했습니다! 🎉")
        else: st.info("문장이 없습니다.")