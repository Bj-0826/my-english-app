import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
from datetime import timedelta, timezone
import plotly.graph_objects as go
import os
import plotly.express as px
import requests
import numpy as np
from io import StringIO

# ==========================================
# 1. 앱 기본 설정 및 환경 변수
# ==========================================
st.set_page_config(page_title="은퇴 준비하기 v6.2.0", layout="wide")

# 한국 표준시(KST) 보정 및 D-Day 계산
KST = timezone(timedelta(hours=9))
now_kst = datetime.datetime.now(KST).date()
ret_date = datetime.date(2028, 12, 31)
d_day = (ret_date - now_kst).days

# 구글 시트 고유 ID
SHEET_ID = "1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA"

# ==========================================
# 2. 핵심 유틸리티 함수
# ==========================================

def load_data_safe(s_name):
    """구글 시트로부터 데이터를 안전하게 로드하는 함수"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={s_name}"
        response = requests.get(url)
        response.encoding = 'utf-8'
        if response.status_code != 200: 
            return pd.DataFrame()
        
        df = pd.read_csv(StringIO(response.text))
        if df.empty: 
            return pd.DataFrame()
        
        # 컬럼명 전처리 및 빈 행 제거
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if 'date' in df.columns: 
            df['date'] = df['date'].astype(str).str.strip().str.upper()
        
        # 숫자형 데이터 변환 (기존 + v6.2.0 신규 자산 컬럼 포함)
        amount_cols = ['amount', '가격', 'grand_total', 'pension_total', 'personal_total']
        for col in amount_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        # 영어공부 암기 상태 처리
        if s_name == "Sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
            
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생 ({s_name}): {e}")
        return pd.DataFrame()

# 구글 시트 연결 인스턴스
conn = st.connection("gsheets", type=GSheetsConnection)

def get_rate(unit):
    """실시간 환율 정보 획득"""
    if unit == "KRW": return 1
    try:
        res = requests.get(f"https://api.exchangerate-api.com/v4/latest/{unit}").json()
        return res['rates']['KRW']
    except:
        return {"TWD": 47, "USD": 1490, "EUR": 1500}.get(unit, 1)

def reset_quiz():
    """영어 퀴즈 초기화"""
    st.session_state.pop('q_idx', None)
    st.session_state.quiz_input = ""

# ==========================================
# 3. 사이드바 내비게이션
# ==========================================

with st.sidebar:
    st.title("은퇴 준비하기 v6.2.0")
    
    # [v6.2.0 추가] 상단 전략 모드 선택
    st.subheader("🚀 핵심 전략")
    strat_mode = st.selectbox("전략 모드 선택", ["일반 모드", "🏦 은퇴 관제탑", "🔄 리밸런싱"], index=0)
    
    st.divider()
    st.subheader("📋 전체 메뉴")
    
    menu_options = [
        "💰 연금자산", "📈 연금시뮬", "💸 현금흐름", "💵 개인자산",
        "🔤 영어공부", "📚 도서관리", "✈️ 여행관리", "📓 다이어리", "📰 뉴스저장"
    ]
    
    menu = st.radio("이동할 메뉴 선택", menu_options, label_visibility="collapsed")
    
    st.divider()
    
    # 은퇴 D-Day 지표 (KST 기준)
    st.metric("은퇴 D-Day (KST)", f"D-{d_day}")
    st.caption(f"현재 기준일: {now_kst}")
# ==========================================
# 4. 각 메뉴별 비즈니스 로직
# ==========================================

# --- [v6.2.1 신규 전략 로직: 은퇴 관제탑 - 입력/수정/삭제 포함] ---
if strat_mode == "🏦 은퇴 관제탑":
    st.header("🏦 은퇴 관제탑 (Control Tower)")
    df_ms = load_data_safe("Milestones")
    df_ta = load_data_safe("TotalAssets")
    
    t_ms, t_ta, t_in = st.tabs(["🎯 마일스톤 관리", "📊 통합 자산 리포트", "📝 데이터 입력/수정"])
    
    with t_ms:
        st.subheader("🎯 마일스톤 현황 및 관리")
        if not df_ms.empty:
            for i, row in df_ms.iterrows():
                icon = "✅" if str(row['status']).strip() == "완료" else "⏳"
                with st.expander(f"{icon} {row['d_day_target']} | {row['task']}"):
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**카테고리:** {row['category']}")
                    c1.write(f"**상세메모:** {row['memo'] if pd.notnull(row['memo']) else '-'}")
                    if c2.button("상태변경", key=f"ms_sw_{i}"):
                        df_ms.at[i, 'status'] = "진행중" if str(row['status']).strip() == "완료" else "완료"
                        conn.update(worksheet="Milestones", data=df_ms); st.rerun()
                    if c2.button("마일스톤 삭제", key=f"ms_dl_{i}"):
                        conn.update(worksheet="Milestones", data=df_ms.drop(i)); st.rerun()
        else:
            st.info("입력 탭에서 마일스톤을 추가해 주세요.")
            
    with t_ta:
        if not df_ta.empty:
            # 상단 합계 표시
            latest = df_ta.iloc[-1]
            st.subheader(f"📊 {latest['date']} 통합 자산 요약")
            c1, c2, c3 = st.columns(3)
            c1.metric("통합 총자산", f"{int(latest['grand_total']):,}원")
            c2.metric("연금자산", f"{int(latest['pension_total']):,}원")
            c3.metric("개인자산", f"{int(latest['personal_total']):,}원")
            
            st.divider()
            
            # 최신 3개 데이터 그래프 (X축 포맷: 26-04-25)
            df_ta['date_dt'] = pd.to_datetime(df_ta['date'], errors='coerce')
            df_plot = df_ta.sort_values('date_dt').tail(3).copy()
            df_plot['display_date'] = df_plot['date_dt'].dt.strftime('%y-%m-%d')
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df_plot['display_date'], y=df_plot['pension_total'], name='연금자산', marker_color='#1f77b4'))
            fig.add_trace(go.Bar(x=df_plot['display_date'], y=df_plot['personal_total'], name='개인자산', marker_color='#ff7f0e'))
            fig.add_trace(go.Scatter(x=df_plot['display_date'], y=df_plot['grand_total'], name='총자산', line=dict(color='gold', width=4)))
            
            fig.update_layout(barmode='stack', height=450, xaxis=dict(type='category'), title="최근 3개 데이터 자산 추이")
            st.plotly_chart(fig, use_container_width=True)
            if pd.notnull(latest['insight']):
                st.info(f"💡 이번 달 인사이트: {latest['insight']}")
        else:
            st.info("자산 데이터를 입력해 주세요.")

    with t_in:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🎯 신규 마일스톤 등록")
            with st.form("in_ms_tower"):
                ms_d = st.text_input("D-Day (예: D-900)")
                ms_t = st.text_input("할 일 제목")
                ms_c = st.selectbox("분류", ["금융", "행정", "라이프", "자기계발"])
                ms_m = st.text_area("상세 내용")
                if st.form_submit_button("마일스톤 저장"):
                    new_ms = pd.DataFrame([{"d_day_target": ms_d, "task": ms_t, "category": ms_c, "status": "진행중", "memo": ms_m}])
                    conn.update(worksheet="Milestones", data=pd.concat([df_ms, new_ms], ignore_index=True)); st.rerun()
        with c2:
            st.subheader("💰 통합자산 기록 업데이트")
            with st.form("in_ta_tower"):
                ta_d = st.date_input("데이터 기준일", now_kst)
                ta_p = st.number_input("연금자산 합계(원)", step=1000000)
                ta_s = st.number_input("개인자산 합계(원)", step=1000000)
                ta_i = st.text_area("인사이트 및 메모")
                if st.form_submit_button("통합자산 데이터 저장"):
                    new_ta = pd.DataFrame([{"date": str(ta_d), "pension_total": ta_p, "personal_total": ta_s, "grand_total": ta_p+ta_s, "insight": ta_i}])
                    conn.update(worksheet="TotalAssets", data=pd.concat([df_ta.drop(columns=['date_dt','display_date'], errors='ignore'), new_ta], ignore_index=True)); st.rerun()

# --- [v6.2.1 신규 전략 로직: 리밸런싱 관리] ---
elif strat_mode == "🔄 리밸런싱":
    st.header("🔄 자산 리밸런싱 아카이브")
    df_reb = load_data_safe("Rebalancing")
    st.info("💡26년(70:30) → 27년(60:40) → 28년(50:50), 29년 이후 배당 ETF, 마켓금리액티브 매수")
    
    with st.form("reb_in_form_v2"):
        c1, c2 = st.columns(2)
        r_date = c1.date_input("리밸런싱 실행 날짜", now_kst)
        r_strat = c1.text_input("현재 전략 비중 (예: 70:30)")
        r_action = c2.text_area("실행 내역 (매수/매도 상세)")
        r_reason = st.text_area("리밸런싱 판단 근거")
        r_target = c2.text_input("조정 후 목표 비중")
        if st.form_submit_button("리밸런싱 내역 저장"):
            new_reb = pd.DataFrame([{"date": str(r_date), "strategy": r_strat, "action": r_action, "reason": r_reason, "target_ratio": r_target}])
            conn.update(worksheet="Rebalancing", data=pd.concat([df_reb, new_reb], ignore_index=True)); st.rerun()
            
    if not df_reb.empty:
        st.divider()
        for i, row in df_reb.iloc[::-1].iterrows():
            with st.expander(f"📅 {row['date']} 리밸런싱 실행 기록"):
                st.write(f"**전략 비중:** {row['strategy']} → **목표 비중:** {row['target_ratio']}")
                st.write(f"**상세 액션:** {row['action']}")
                st.caption(f"**판단 근거:** {row['reason']}")
                if st.button("내역 삭제", key=f"reb_del_btn_{i}"):
                    conn.update(worksheet="Rebalancing", data=df_reb.drop(i)); st.rerun()

# --- [기존 모드: v6.1.2 코드 100% 유지] ---
elif strat_mode == "일반 모드":

    # --- [1. 연금자산] ---
    if menu == "💰 연금자산":
        st.header("💰 연금자산 관리")
        df_p = load_data_safe("Data")
        t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
        
        with t1:
            if not df_p.empty and 'date' in df_p.columns:
                # 날짜 정렬을 위한 전처리
                df_p['date_dt'] = pd.to_datetime(df_p['date'], format='%Y-%m', errors='coerce')
                dates_sorted_dt = sorted(df_p['date_dt'].dropna().unique())
                
                if dates_sorted_dt:
                    recent_dt = dates_sorted_dt[-3:]
                    # 캡처 요청 반영: 표시용 날짜 포맷팅 (26년 03월 형태)
                    recent_labels = [d.strftime('%y년 %m월') for d in recent_dt]
                    
                    # 원본 문자열 기반 필터링
                    recent_str = [d.strftime('%Y-%m') for d in recent_dt]
                    df_r = df_p[df_p['date'].isin(recent_str)].copy()
                    
                    # 날짜를 다시 정렬된 dt 기반으로 매핑하여 그룹화
                    m_total = df_r.groupby('date_dt')['amount'].sum().reindex(recent_dt).fillna(0)
                    
                    cur = m_total.iloc[-1]
                    prev = m_total.iloc[-2] if len(m_total) > 1 else cur
                    diff = cur - prev
                    
                    c1, c2 = st.columns(2)
                    c1.metric(f"{recent_labels[-1]} 합계", f"{int(cur):,}원")
                    c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
                    
                    fig = go.Figure()
                    for acc in sorted(df_r['account'].unique()):
                        acc_df = df_r[df_r['account'] == acc].set_index('date_dt').reindex(recent_dt).fillna(0).reset_index()
                        # X축에 포맷팅된 라벨 적용
                        fig.add_trace(go.Bar(
                            x=[d.strftime('%y년 %m월') for d in acc_df['date_dt']], 
                            y=acc_df['amount'], 
                            name=acc
                        ))
                    
                    fig.update_layout(
                        barmode='stack', 
                        height=450,
                        xaxis=dict(type='category'), # X축을 카테고리로 지정하여 자동 변동 방지
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
        with t2:
            c1, c2 = st.columns(2)
            py = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
            pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month-1, key="p_m")
            p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
            p_amt = st.number_input("금액(원)", step=100000)
            
            if st.button("연금 데이터 저장"):
                df = load_data_safe("Data")
                t_date = f"{py}-{pm}"
                mask = (df['date'] == t_date) & (df['account'] == p_acc)
                
                if mask.any():
                    df.loc[mask, 'amount'] = int(p_amt)
                else:
                    new_row = pd.DataFrame([{"date": t_date, "account": p_acc, "amount": int(p_amt), "memo": ""}])
                    df = pd.concat([df, new_row], ignore_index=True)
                    
                conn.update(worksheet="Data", data=df)
                st.toast("연금 정보가 저장되었습니다!")
                st.rerun()

    # --- [2. 연금시뮬] ---
    elif menu == "📈 연금시뮬":
        st.header("📈 은퇴 후 연금 마스터 시뮬레이터")
        df_p = load_data_safe("Data")
        current_total = 0
        
        if not df_p.empty:
            df_p['date_dt'] = pd.to_datetime(df_p['date'], format='%Y-%m', errors='coerce')
            latest_dt = df_p['date_dt'].max()
            if pd.notnull(latest_dt):
                current_total = df_p[df_p['date_dt'] == latest_dt]['amount'].sum()
            
        tab1, tab2, tab3 = st.tabs(["📉 자산 예측 시뮬레이션", "🏛️ 국민연금 & 세금 가이드", "💡 기획자 제언"])
        
        with tab1:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.subheader("⚙️ 조건 설정")
                # Byungjoo님 목표 반영: 퇴직금 4.9억 베이스로 수정
                base_asset = st.number_input("기초 자산 (현재연금+퇴직금)", value=int(current_total + 490000000), step=10000000)
                monthly_withdraw = st.slider("월 희망 수령액 (만 원)", 300, 1000, 450) * 10000 # 450만원 고정 목표
                annual_return = st.slider("기대 연 수익률 (%)", 0.0, 10.0, 4.0, 0.5) / 100
                inflation_rate = st.slider("예상 물가 상승률 (%)", 0.0, 5.0, 2.0, 0.5) / 100
                start_y = st.selectbox("시뮬레이션 시작 연도", range(2029, 2040), index=0)
                end_y = st.selectbox("시뮬레이션 종료 연도", range(start_y+1, 2075), index=25)
                use_national = st.checkbox("2038년 8월부터 월 150만원 합산", value=True)
                
            with c2:
                months = (end_y - start_y + 1) * 12
                dates = pd.date_range(start=f"{start_y}-01-01", periods=months, freq='MS')
                asset_history, cur_asset, cur_withdraw = [], base_asset, monthly_withdraw
                
                for d in dates:
                    cur_asset *= (1 + annual_return / 12)
                    if d.month == 1: cur_withdraw *= (1 + inflation_rate)
                    net_withdraw = max(0, cur_withdraw - 1500000) if use_national and d >= pd.Timestamp(2038, 8, 1) else cur_withdraw
                    cur_asset -= net_withdraw
                    if cur_asset < 0: cur_asset = 0
                    asset_history.append(cur_asset)
                    
                sim_df = pd.DataFrame({"날짜": dates, "잔액": asset_history})
                fig_sim = px.area(sim_df, x="날짜", y="잔액", title=f"월 {int(monthly_withdraw/10000)}만원 인출 시 자산 추이")
                fig_sim.update_xaxes(tickformat="%y년")
                st.plotly_chart(fig_sim, use_container_width=True)
                
        with tab2:
            st.subheader("📚 연금 수령 전략 사전")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("""
                #### 1. 인출 순서 (Tax-Smart)
                * **ISA 자금**: 가장 먼저 사용 (비과세 혜택 활용)
                * **연금저축/IRP (추가납입분)**: 원금은 비과세 인출 가능하므로 유동성 확보에 유리
                * **퇴직연금 (퇴직금)**: 연금 수령 시 퇴직소득세 30% 감면 혜택
                * **연금저축/IRP (공제분+수익)**: 마지막에 수령 (연금소득세 3.3~5.5%)
                """)
            with col_b:
                st.markdown("""
                #### 2. 세금 주의사항
                * **연 1,500만원 한도**: 사적연금 수령액이 넘으면 종합과세 대상이 되므로 인출 금액 조절 필수
                * **건보료**: 현재 사적연금은 건보료 산정 제외이나, 향후 개편 가능성을 지속 모니터링해야 함
                """)
                
        with tab3:
            st.subheader("💡 Byungjoo님을 위한 기획자 제언")
            st.info("""
            **1. 4% 법칙 (Safe Withdrawal Rate)**: 전체 자산의 4% 이내로 매년 인출하면 자산이 마르지 않을 확률이 매우 높습니다.
            
            **2. 현금성 자산 2년치 보유**: 시장이 일시적으로 폭락할 때 연금을 인출하면 자산 회복이 불가능해집니다. 하락장을 버틸 2년치 생활비는 항상 예금/채권으로 별도 관리하세요.
            """)

    # --- [3. 현금흐름] ---
    elif menu == "💸 현금흐름":
        st.header("💸 현금흐름 관리 (은퇴 준비)")
        df_cf = load_data_safe("CashFlow")
        df_bg = load_data_safe("Budgets")
        
        CF_CATEGORIES = ["급여", "기타수익", "자기계발", "문화생활", "저축/투자", "쇼핑", "외식", "생활비", "마트", 
                         "통신비, 구독료", "교통비", "보험", "여행", "명절, 이벤트", "용돈", "기타"]
        
        c_f1, c_f2 = st.columns(2)
        sel_y = c_f1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1)
        sel_m = c_f2.selectbox("조회 월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month-1)
        sel_period = f"{sel_y}-{sel_m}"
        
        t1, t2, t3, t4, t5 = st.tabs(["🚦 소비 신호등", "📝 내역 기록", "📊 지출 패턴 분석", "✏️ 내역 수정/삭제", "⚙️ 예산 설정"])
        
        with t1:
            total_spent = 0
            if not df_cf.empty:
                df_cf['date_dt'] = pd.to_datetime(df_cf['date'], errors='coerce')
                m_exp = df_cf[(df_cf['type'] == 'EXPENSE') & (df_cf['date_dt'].dt.strftime("%Y-%m") == sel_period)]
                total_spent = m_exp['amount'].sum()
                
            current_budget = df_bg[df_bg['period'] == sel_period]['budget_amount'].iloc[0] if not df_bg.empty and not df_bg[df_bg['period'] == sel_period].empty else 0
            
            if current_budget == 0:
                st.info(f"📢 {sel_period}의 예산이 설정되지 않았습니다.")
            else:
                percent = (total_spent / current_budget) * 100
                c1, c2, c3 = st.columns(3)
                c1.metric("소비 상태", f"{percent:.1f}%", f"{int(current_budget-total_spent):,}원 남음")
                
        with t2:
            with st.form("cf_form_v3", clear_on_submit=True):
                c1, c2 = st.columns(2)
                f_date = c1.date_input("날짜", now_kst)
                f_type = c1.selectbox("구분", ["EXPENSE", "INCOME"])
                f_cat = c2.selectbox("카테고리", CF_CATEGORIES)
                f_amt = c2.number_input("금액", min_value=0, step=1000)
                f_memo = st.text_input("메모")
                f_rec = st.checkbox("정기 지출/수입 여부")
                
                if st.form_submit_button("현금흐름 기록 저장"):
                    new_data = pd.DataFrame([{"date": str(f_date), "type": f_type, "category": f_cat, "amount": f_amt, "memo": f_memo, "is_recurring": str(f_rec).upper()}])
                    conn.update(worksheet="CashFlow", data=pd.concat([df_cf.drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf, new_data], ignore_index=True))
                    st.success("내역이 저장되었습니다!")
                    st.rerun()
                    
        with t3:
            if not df_cf.empty:
                m_exp_only = df_cf[(df_cf['type'] == 'EXPENSE') & (pd.to_datetime(df_cf['date']).dt.strftime("%Y-%m") == sel_period)]
                if not m_exp_only.empty:
                    fig = px.pie(m_exp_only, values='amount', names='category', hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)
                    st.dataframe(m_exp_only[['date', 'category', 'amount', 'memo']].sort_values('date', ascending=False), use_container_width=True)
                    
        with t4:
            if not df_cf.empty:
                m_data = df_cf[pd.to_datetime(df_cf['date'], errors='coerce').dt.strftime("%Y-%m") == sel_period]
                if not m_data.empty:
                    edit_list = m_data.apply(lambda x: f"[{x['date']}] {x['category']} - {x['memo']} ({int(x['amount']):,}원)", axis=1).tolist()
                    sel_item = st.selectbox("수정/삭제할 항목 선택", options=edit_list)
                    sel_idx = m_data.index[edit_list.index(sel_item)]
                    
                    with st.form("edit_cf_full"):
                        ec1, ec2 = st.columns(2)
                        e_date = ec1.date_input("날짜 수정", value=pd.to_datetime(df_cf.loc[sel_idx, 'date']).date())
                        e_type = ec1.selectbox("구분 수정", ["EXPENSE", "INCOME"], index=0 if df_cf.loc[sel_idx, 'type'] == "EXPENSE" else 1)
                        e_cat = ec2.selectbox("카테고리 수정", CF_CATEGORIES, index=CF_CATEGORIES.index(df_cf.loc[sel_idx, 'category']) if df_cf.loc[sel_idx, 'category'] in CF_CATEGORIES else 0)
                        e_amt = ec2.number_input("금액 수정", value=int(df_cf.loc[sel_idx, 'amount']))
                        e_memo = st.text_input("메모 수정", value=str(df_cf.loc[sel_idx, 'memo']))
                        
                        b1, b2 = st.columns(2)
                        if b1.form_submit_button("💾 수정 완료"):
                            df_cf.at[sel_idx, 'date'] = str(e_date)
                            df_cf.at[sel_idx, 'type'] = e_type
                            df_cf.at[sel_idx, 'category'] = e_cat
                            df_cf.at[sel_idx, 'amount'] = e_amt
                            df_cf.at[sel_idx, 'memo'] = e_memo
                            conn.update(worksheet="CashFlow", data=df_cf.drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf)
                            st.rerun()
                        if b2.form_submit_button("🗑️ 삭제 완료"):
                            conn.update(worksheet="CashFlow", data=df_cf.drop(sel_idx).drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf)
                            st.rerun()

        with t5:
            with st.form("budget_setting"):
                new_bg = st.number_input("해당 월 목표 예산", value=int(current_budget), step=100000)
                if st.form_submit_button("예산 저장"):
                    if not df_bg.empty and (df_bg['period'] == sel_period).any():
                        df_bg.loc[df_bg['period'] == sel_period, 'budget_amount'] = new_bg
                    else:
                        df_bg = pd.concat([df_bg, pd.DataFrame([{"category": "전체", "budget_amount": new_bg, "period": sel_period}])], ignore_index=True)
                    conn.update(worksheet="Budgets", data=df_bg)
                    st.rerun()

    # --- [4. 개인자산] ---
    elif menu == "💵 개인자산":
        st.header("💵 개인자산 관리")
        df_per = load_data_safe("PersonalData")
        t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
        
        with t1:
            if not df_per.empty and 'date' in df_per.columns:
                def get_w_label(k):
                    try:
                        y = int(str(k)[1:5])
                        w = int(str(k).split('W')[1])
                        d = datetime.date(y, 1, 1) + datetime.timedelta(weeks=w-1)
                        return f"{d.strftime('%y년')} {d.month}월 {((d.day-1)//7)+1}주"
                    except: return str(k)
                    
                weeks = sorted([str(d) for d in df_per['date'].unique()])
                if weeks:
                    recent = weeks[-3:]
                    df_r = df_per[df_per['date'].isin(recent)]
                    w_total = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                    cur = w_total.iloc[-1]
                    prev = w_total.iloc[-2] if len(w_total) > 1 else cur
                    
                    c1, c2 = st.columns(2)
                    c1.metric(f"{get_w_label(recent[-1])} 합계", f"{int(cur):,}원")
                    c2.metric("전주 대비", f"{((cur-prev)/prev*100) if prev!=0 else 0:+.1f}%", f"{int(cur-prev):+,}원")
                    
                    fig = go.Figure()
                    for acc in sorted(df_r['account'].unique()):
                        acc_df = df_r[df_r['account'] == acc].set_index('date').reindex(recent).fillna(0).reset_index()
                        fig.add_trace(go.Bar(x=[get_w_label(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
                    fig.update_layout(barmode='stack', height=400, xaxis=dict(type='category'))
                    st.plotly_chart(fig, use_container_width=True)
                    
        with t2:
            c1, c2 = st.columns(2)
            pery = c1.selectbox("연도", [2026, 2027, 2028])
            perw = c2.number_input("주차 (Week)", 1, 53, now_kst.isocalendar()[1])
            p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
            per_amt = st.number_input("현재 잔액(원)", step=10000)
            
            if st.button("개인자산 정보 저장"):
                df = load_data_safe("PersonalData")
                t_date = f"Y{pery}W{perw}"
                mask = (df['date'] == t_date) & (df['account'] == p_acc_per)
                
                if mask.any():
                    df.loc[mask, 'amount'] = int(per_amt)
                else:
                    df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc_per, "amount": int(per_amt), "memo": ""}])], ignore_index=True)
                    
                conn.update(worksheet="PersonalData", data=df)
                st.toast("저장 완료!")
                st.rerun()

    # --- [5. 영어공부] ---
    elif menu == "🔤 영어공부":
        st.header("🔤 영어 공부")
        df_en = load_data_safe("Sheet1")
        t1, t2, t3, t4 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "✏️ 문장 수정/삭제", "🧠 퀴즈"])
        
        with t1:
            if not df_en.empty:
                ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True, key="en_ed")
                if st.button("암기 상태 한꺼번에 저장"):
                    save_df = df_en.copy()
                    save_df.update(ed)
                    conn.update(worksheet="Sheet1", data=save_df)
                    st.toast("상태 업데이트 완료!")
                    st.rerun()
                    
        with t2:
            with st.form("en_in_form", clear_on_submit=True):
                new_en = st.text_input("영어 문장")
                new_ko = st.text_input("한글 뜻")
                if st.form_submit_button("새 문장 추가"):
                    new_row = pd.DataFrame([{"date": str(now_kst), "english": new_en, "korean": new_ko, "memorized": False}])
                    conn.update(worksheet="Sheet1", data=pd.concat([df_en, new_row], ignore_index=True))
                    st.rerun()
                    
        with t3:
            if not df_en.empty:
                edit_list = df_en.apply(lambda x: f"[{x['date']}] {x['english']}", axis=1).tolist()
                sel_en = st.selectbox("수정할 문장 선택", options=edit_list)
                en_idx = df_en.index[edit_list.index(sel_en)]
                with st.form("edit_en"):
                    e_en = st.text_input("영어 수정", value=str(df_en.loc[en_idx, 'english']))
                    e_ko = st.text_input("한글 수정", value=str(df_en.loc[en_idx, 'korean']))
                    if st.form_submit_button("💾 문장 수정 저장"):
                        df_en.at[en_idx, 'english'] = e_en
                        df_en.at[en_idx, 'korean'] = e_ko
                        conn.update(worksheet="Sheet1", data=df_en)
                        st.rerun()
                    if st.form_submit_button("🗑️ 문장 삭제"):
                        conn.update(worksheet="Sheet1", data=df_en.drop(en_idx))
                        st.rerun()
                        
        with t4:
            unmem = df_en[df_en['memorized'] == False] if not df_en.empty else pd.DataFrame()
            if not unmem.empty:
                if 'q_idx' not in st.session_state: 
                    st.session_state.q_idx = unmem.sample(n=1).index[0]
                q = unmem.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력해 보세요", key="quiz_input")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): 
                        st.success("Perfect!")
                        st.balloons()
                    else: 
                        st.error(f"Try again! 정답: {q['english']}")
                st.button("다음 문제로", on_click=reset_quiz)

    # --- [6. 도서관리] ---
    elif menu == "📚 도서관리":
        st.header("📚 도서 관리 시스템")
        df_books = load_data_safe("Books")
        
        if not df_books.empty:
            c1, c2, c3 = st.columns([1, 1, 2])
            sel_y_book = c1.selectbox("통계 조회 연도", options=["2026년", "2027년", "2028년"])
            y_int = int(sel_y_book.replace("년", ""))
            y_df = df_books[pd.to_datetime(df_books['날짜'], errors='coerce').dt.year == y_int]
            c2.metric(f"{y_int}년 완독수", f"{len(y_df)} 권")
            c3.metric(f"{y_int}년 누적 도서비", f"₩{int(y_df['가격'].sum()):,}")
            
        st.divider()
        tab1, tab2, tab3 = st.tabs(["📖 나의 서재", "➕ 신규 도서 등록", "✏️ 도서 정보 수정/삭제"])
        
        with tab1:
            if not df_books.empty:
                st.table(df_books.iloc[::-1][['날짜', '제목', '저자', '가격', '구입처', '분류']].head(15))
                
        with tab2:
            with st.form("book_reg_cloud", clear_on_submit=True):
                tc1, tc2 = st.columns(2)
                t = tc1.text_input("도서 제목 (필수)")
                a = tc1.text_input("저자")
                p = tc1.number_input("구입 가격", step=1000)
                s = tc1.text_input("구입처")
                d = tc2.date_input("구입/읽은 날짜", now_kst)
                cat = tc2.selectbox("도서 분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"])
                r = tc2.slider("나의 별점", 1, 5, 5)
                cmt = st.text_area("한줄평 및 메모")
                
                if st.form_submit_button("도서 정보 저장"):
                    if t:
                        new_book = pd.DataFrame([{'날짜': str(d), '제목': t, '저자': a, '가격': int(p), '구입처': s, '분류': cat, '별점': int(r), '코멘트': cmt, '연도': d.year}])
                        conn.update(worksheet="Books", data=pd.concat([df_books, new_book], ignore_index=True))
                        st.success("서재에 추가되었습니다!")
                        st.rerun()
                    else: st.warning("제목을 입력해주세요.")
                    
        with tab3:
            if not df_books.empty:
                edit_list = df_books.apply(lambda x: f"{x['제목']} ({x['저자']})", axis=1).tolist()
                sel_b = st.selectbox("수정할 책 선택", options=edit_list)
                b_idx = df_books.index[edit_list.index(sel_b)]
                with st.form("edit_book_full"):
                    ec1, ec2 = st.columns(2)
                    e_t = ec1.text_input("제목 수정", value=df_books.loc[b_idx, '제목'])
                    e_a = ec1.text_input("저자 수정", value=df_books.loc[b_idx, '저자'])
                    e_p = ec1.number_input("가격 수정", value=int(df_books.loc[b_idx, '가격']))
                    e_s = ec1.text_input("구입처 수정", value=str(df_books.loc[b_idx, '구입처']))
                    e_cat = ec2.selectbox("분류 수정", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"], index=0)
                    e_r = ec2.slider("별점 수정", 1, 5, int(df_books.loc[b_idx, '별점']))
                    e_cmt = st.text_area("코멘트 수정", value=str(df_books.loc[b_idx, '코멘트']))
                    
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 수정사항 저장"):
                        df_books.loc[b_idx, ['제목', '저자', '가격', '구입처', '분류', '별점', '코멘트']] = [e_t, e_a, e_p, e_s, e_cat, e_r, e_cmt]
                        conn.update(worksheet="Books", data=df_books)
                        st.rerun()
                    if c2.form_submit_button("🗑️ 도서 삭제"):
                        conn.update(worksheet="Books", data=df_books.drop(b_idx))
                        st.rerun()

    # --- [7. 여행관리] ---
    elif menu == "✈️ 여행관리":
        st.header("✈️ Byungjoo 여행기록")
        df_dest = load_data_safe("TravelDest")
        df_exp = load_data_safe("TravelExp")
        METHODS = ["하나카드", "트래블월렛", "삼성카드", "현금"]
        
        t_home, t_ledger, t_timeline, t_stats, t_edit = st.tabs(["🗺️ 여행지 관리", "💰 비용 기록", "🗓️ 타임라인", "📊 지출 요약", "⚙️ 내역 수정/삭제"])
        
        with t_home:
            st.subheader("📍 새 여행 계획/완료 등록")
            with st.form("new_dest_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                new_name = c1.text_input("여행지명")
                new_start = c2.date_input("출발일", now_kst)
                new_end = c2.date_input("도착일", now_kst + timedelta(days=3))
                new_status = c3.selectbox("여행 상태", ["준비", "여행중", "완료"])
                if st.form_submit_button("여행지 추가"):
                    if new_name:
                        new_id = int(df_dest['id'].max() + 1) if not df_dest.empty else 1
                        new_row = pd.DataFrame([{'id': new_id, 'name': new_name, 'start_date': str(new_start), 'end_date': str(new_end), 'status': new_status}])
                        conn.update(worksheet="TravelDest", data=pd.concat([df_dest, new_row], ignore_index=True))
                        st.rerun()
            
            if not df_dest.empty:
                st.divider()
                st.write("📂 **기존 여행지 정보 관리**")
                for i, row in df_dest.iterrows():
                    with st.expander(f"{row['name']} ({row['start_date']} ~ {row['end_date']})"):
                        with st.form(f"edit_dest_{i}"):
                            e1, e2, e3 = st.columns(3)
                            en = e1.text_input("여행지명 수정", value=row['name'])
                            es = e2.date_input("출발일 수정", value=pd.to_datetime(row['start_date']).date())
                            ee = e2.date_input("도착일 수정", value=pd.to_datetime(row['end_date']).date())
                            est = e3.selectbox("상태 수정", ["준비", "여행중", "완료"], index=["준비", "여행중", "완료"].index(row['status']))
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 여행지 정보 저장"):
                                df_dest.at[i, 'name'], df_dest.at[i, 'start_date'], df_dest.at[i, 'end_date'], df_dest.at[i, 'status'] = en, str(es), str(ee), est
                                conn.update(worksheet="TravelDest", data=df_dest); st.rerun()
                            if b2.form_submit_button("🗑️ 여행지 전체 삭제"):
                                conn.update(worksheet="TravelDest", data=df_dest.drop(i)); st.rerun()

        if not df_dest.empty:
            sel_city = st.sidebar.selectbox("📍 여행지 선택", options=df_dest['name'].tolist())
            curr_row = df_dest[df_dest['name'] == sel_city]
            if not curr_row.empty:
                curr = curr_row.iloc[0]
                d_exp = df_exp[df_exp['dest_id'] == curr['id']].copy() if not df_exp.empty else pd.DataFrame()
                
                with t_ledger:
                    st.metric(f"'{sel_city}' 누적 비용", f"₩{int(d_exp['amount'].sum()):,}" if not d_exp.empty else "₩0")
                    with st.expander("➕ 실시간 지출 기록", expanded=True):
                        with st.form("t_add_v5", clear_on_submit=True):
                            c1, c2 = st.columns(2)
                            d_input = c1.date_input("날짜", now_kst)
                            it = c2.text_input("소비 항목")
                            pl = c1.text_input("사용 장소")
                            amt = c2.number_input("지출 금액", min_value=0)
                            cat = c1.selectbox("카테고리", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"])
                            met = c2.selectbox("결제 수단", METHODS)
                            if st.form_submit_button("💰 비용 저장 및 초기화"):
                                new_e = pd.DataFrame([{'dest_id': curr['id'], 'date': str(d_input), 'time': '12:00', 'item': it, 'place': pl, 'category': cat, 'method': met, 'amount': int(amt), 'unit': 'KRW', 'memo': ''}])
                                conn.update(worksheet="TravelExp", data=pd.concat([df_exp, new_e], ignore_index=True))
                                st.success("기록되었습니다."); st.rerun()
                
                with t_timeline:
                    if not d_exp.empty:
                        for _, row in d_exp.sort_values('date').iterrows():
                            st.write(f"**[{row['date']}]** {row['item']} | {row['place']} ({row['method']}) - ₩{int(row['amount']):,}")
                
                with t_stats:
                    if not d_exp.empty:
                        st.subheader("📅 일자별 지출 리포트")
                        daily_sum = d_exp.groupby('date')['amount'].sum().reset_index()
                        st.table(daily_sum.assign(amount=lambda x: x['amount'].map('{:,}원'.format)))
                        
                        st.subheader("💳 결제수단별 합계")
                        method_sum = d_exp.groupby('method')['amount'].sum().reset_index()
                        st.table(method_sum.assign(amount=lambda x: x['amount'].map('{:,}원'.format)))

                        st.subheader("📁 카테고리별 요약")
                        cat_sum = d_exp.groupby('category')['amount'].sum().reset_index()
                        st.table(cat_sum.assign(amount=lambda x: x['amount'].map('{:,}원'.format)))
                
                with t_edit:
                    if not d_exp.empty:
                        edit_list = d_exp.apply(lambda x: f"[{x['date']}] {x['item']} (₩{int(x['amount']):,}원)", axis=1).tolist()
                        sel_l = st.selectbox("수정할 지출 내역 선택", options=edit_list)
                        t_idx = d_exp.index[edit_list.index(sel_l)]
                        with st.form("edit_t_exp_full"):
                            ec1, ec2 = st.columns(2)
                            e_date = ec1.date_input("날짜 수정", value=pd.to_datetime(d_exp.loc[t_idx, 'date']).date())
                            e_it = ec1.text_input("항목명 수정", value=d_exp.loc[t_idx, 'item'])
                            e_pl = ec1.text_input("장소 수정", value=d_exp.loc[t_idx, 'place'])
                            e_amt = ec2.number_input("금액 수정", value=int(d_exp.loc[t_idx, 'amount']))
                            e_cat = ec2.selectbox("카테고리 수정", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"], index=0)
                            e_met = ec2.selectbox("수단 수정", METHODS, index=METHODS.index(d_exp.loc[t_idx, 'method']) if d_exp.loc[t_idx, 'method'] in METHODS else 0)
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 지출 정보 수정 저장"):
                                df_exp.loc[t_idx, ['date', 'item', 'place', 'amount', 'category', 'method']] = [str(e_date), e_it, e_pl, e_amt, e_cat, e_met]
                                conn.update(worksheet="TravelExp", data=df_exp); st.rerun()
                            if b2.form_submit_button("🗑️ 지출 항목 삭제"):
                                conn.update(worksheet="TravelExp", data=df_exp.drop(t_idx)); st.rerun()

    # --- [8. 다이어리] ---
    elif menu == "📓 다이어리":
        st.header("📓 Byungjoo's 다이어리 & 아이디어")
        df_diary = load_data_safe("Diary")
        dt1, dt2 = st.tabs(["📝 신규 기록 남기기", "📖 전체 기록 확인 및 수정"])
        
        with dt1:
            with st.form("diary_in", clear_on_submit=True):
                d_title = st.text_input("기록 제목")
                d_tags = st.multiselect("태그 선택", ["아이디어", "회고", "계획", "학습", "일상"])
                d_content = st.text_area("내용을 자유롭게 적어주세요", height=200)
                if st.form_submit_button("생각 저장하기"):
                    new_diary = pd.DataFrame([{'date': str(now_kst), 'title': d_title, 'content': d_content, 'tags': ", ".join(d_tags), 'level': 'Normal'}])
                    conn.update(worksheet="Diary", data=pd.concat([df_diary, new_diary], ignore_index=True))
                    st.rerun()
                    
        with dt2:
            if not df_diary.empty:
                search_q = st.text_input("🔍 제목 키워드 검색")
                filt_df = df_diary[df_diary['title'].str.contains(search_q, na=False)] if search_q else df_diary
                for i, row in filt_df.iloc[::-1].iterrows():
                    with st.expander(f"{row['date']} | {row['title']}"):
                        with st.form(f"edit_diary_{i}"):
                            e_title = st.text_input("제목 수정", value=row['title'])
                            e_content = st.text_area("내용 수정", value=row['content'], height=150)
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("💾 메모 수정 저장"):
                                df_diary.at[i, 'title'], df_diary.at[i, 'content'] = e_title, e_content
                                conn.update(worksheet="Diary", data=df_diary); st.rerun()
                            if c2.form_submit_button("🗑️ 메모 삭제"):
                                conn.update(worksheet="Diary", data=df_diary.drop(i)); st.rerun()

    # --- [9. 뉴스저장] ---
    elif menu == "📰 뉴스저장":
        st.header("📰 지식 큐레이션 (뉴스 & 아티클)")
        df_media = load_data_safe("Media")
        with st.form("media_form", clear_on_submit=True):
            m_title = st.text_input("아티클 제목")
            m_url = st.text_input("URL 링크")
            m_insight = st.text_area("나의 인사이트")
            if st.form_submit_button("지식 창고에 저장"):
                new_media = pd.DataFrame([{'date': str(now_kst), 'category': '기타', 'title': m_title, 'url': m_url, 'insight': m_insight}])
                conn.update(worksheet="Media", data=pd.concat([df_media, new_media], ignore_index=True))
                st.rerun()
        
        if not df_media.empty:
            st.divider()
            st.subheader("📝 저장된 지식 리스트")
            for i, row in df_media.iloc[::-1].iterrows():
                with st.expander(f"{row['title']}"):
                    with st.form(f"edit_media_{i}"):
                        e_m_title = st.text_input("제목 수정", value=row['title'])
                        e_m_url = st.text_input("URL 수정", value=row['url'])
                        e_m_insight = st.text_area("인사이트 수정", value=row['insight'])
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 정보 업데이트"):
                            df_media.at[i, 'title'], df_media.at[i, 'url'], df_media.at[i, 'insight'] = e_m_title, e_m_url, e_m_insight
                            conn.update(worksheet="Media", data=df_media); st.rerun()
                        if c2.form_submit_button("🗑️ 지식 삭제"):
                            conn.update(worksheet="Media", data=df_media.drop(i)); st.rerun()
                    st.markdown(f"🔗 [기사 원문 읽기]({row['url']})")