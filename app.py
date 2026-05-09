import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
from datetime import timedelta, timezone
import plotly.graph_objects as go
import plotly.express as px
import requests
import numpy as np
from io import StringIO

# ==========================================
# 은퇴 준비하기 v6.3.0 버전에 추가된 3개 기능 상세 안내 by Claude (260509)
# ① 목표 달성률 게이지 (은퇴 관제탑 → 통합 자산 리포트 탭 상단)
# 목표 자산을 직접 입력하면 (기본값 15억) 현재 달성률 %를 게이지로 표시
# 색상이 달성률에 따라 빨강(50% 미만) → 주황(80% 미만) → 초록(80% 이상)으로 변경
# 현재 자산, 달성률, 남은 금액 3개 지표 동시 표시

# ② 독서 목표 & 페이스 (도서관리 → 🎯 독서 목표 & 페이스 탭 신규 추가)
# 연간 목표 권수 설정 → 달성률 게이지 + 연말 예상 완독 수 + 남은 월 페이스 자동 계산
# 월별 독서 현황 바 차트 (목표 페이스 점선 표시, 달성 월은 초록색)
# 장르별 독서 분포 파이 차트

# ③ 월간 리포트 (뉴스저장 → 📋 월간 리포트 탭 신규 추가)
# 조회 연/월 선택하면 5개 섹션을 한 페이지로 자동 집계
# 자산 현황 (전월 대비 증감 포함) / 현금흐름 요약 (저축률 + 지출 TOP5) / 이달의 독서 / 이달의 여행 / 이달의 지식 큐레이션

# 1. 앱 기본 설정 및 환경 변수
# ==========================================

st.set_page_config(page_title="은퇴 준비하기 v6.3.0", layout="wide")

KST = timezone(timedelta(hours=9))
now_kst = datetime.datetime.now(KST).date()
ret_date = datetime.date(2028, 12, 31)
d_day = (ret_date - now_kst).days

SHEET_ID = "1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA"

# ==========================================
# 2. 핵심 유틸리티 함수
# ==========================================

def load_data_safe(s_name):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={s_name}"
        response = requests.get(url)
        response.encoding = 'utf-8'
        if response.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(StringIO(response.text))
        if df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str).str.strip().str.upper()
        amount_cols = ['amount', '가격', 'grand_total', 'pension_total', 'personal_total']
        for col in amount_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        if s_name == "Sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생 ({s_name}): {e}")
        return pd.DataFrame()

conn = st.connection("gsheets", type=GSheetsConnection)

def get_rate(unit):
    if unit == "KRW": return 1
    try:
        res = requests.get(f"https://api.exchangerate-api.com/v4/latest/{unit}").json()
        return res['rates']['KRW']
    except:
        return {"TWD": 47, "USD": 1490, "EUR": 1500}.get(unit, 1)

def reset_quiz():
    st.session_state.pop('q_idx', None)
    st.session_state.quiz_input = ""

# ==========================================
# 공통 유틸 - 금액 포맷
# ==========================================

def fmt_eok(val):
    eok = val / 1e8
    return f"{int(eok)}억" if eok == int(eok) else f"{eok:.1f}억"

def fmt_baek(val):
    return f"{int(round(val / 1e6))}백만"

# ==========================================
# 공통 유틸 - 개인자산 주차 변환
# ==========================================

def week_key_to_label(k):
    try:
        k = str(k)
        y = int(k[1:5])
        w = int(k.split('W')[1])
        d = datetime.date(y, 1, 1) + datetime.timedelta(weeks=w - 1)
        week_of_month = ((d.day - 1) // 7) + 1
        return f"{str(y)[2:]}년 {d.month}월 {week_of_month}주"
    except:
        return str(k)

def label_to_week_key(year, month, week_of_month):
    first_day_of_month = datetime.date(year, month, 1)
    target_day = first_day_of_month + datetime.timedelta(weeks=week_of_month - 1)
    iso_week = target_day.isocalendar()[1]
    return f"Y{year}W{iso_week}", target_day

def get_month_weeks(year, month):
    first_day = datetime.date(year, month, 1)
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    seen_weeks = []
    d = first_day
    while d <= last_day:
        week_of_month = ((d.day - 1) // 7) + 1
        iso_week = d.isocalendar()[1]
        week_key = f"Y{year}W{iso_week}"
        label = f"{str(year)[2:]}년 {month}월 {week_of_month}주"
        if week_key not in [x[1] for x in seen_weeks]:
            seen_weeks.append((label, week_key))
        d += datetime.timedelta(days=7)
        if d.day > last_day.day and d.month != month:
            break
        if week_of_month >= 5:
            break
    return seen_weeks

# ==========================================
# 3. 사이드바 내비게이션
# ==========================================

with st.sidebar:
    st.title("은퇴 준비하기 v6.3.0")
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
    st.metric("은퇴 D-Day (KST)", f"D-{d_day}")
    st.caption(f"현재 기준일: {now_kst}")

# ==========================================
# 4. 각 메뉴별 비즈니스 로직
# ==========================================

# =========================================================
# [전략 로직: 은퇴 관제탑]
# =========================================================
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
                        conn.update(worksheet="Milestones", data=df_ms)
                        st.rerun()
                    if c2.button("마일스톤 삭제", key=f"ms_dl_{i}"):
                        conn.update(worksheet="Milestones", data=df_ms.drop(i))
                        st.rerun()
        else:
            st.info("입력 탭에서 마일스톤을 추가해 주세요.")

    with t_ta:
        if not df_ta.empty:
            # date 파싱 강화 (pandas 2.x 호환)
            df_ta['date_clean'] = df_ta['date'].astype(str).str.strip().str.lower()
            df_ta['date_dt'] = pd.to_datetime(df_ta['date_clean'], errors='coerce')
            df_ta_valid = df_ta.dropna(subset=['date_dt']).sort_values('date_dt').copy()

            failed_rows = df_ta[df_ta['date_dt'].isna()]
            if not failed_rows.empty:
                st.caption(f"⚠️ 날짜 파싱 실패 {len(failed_rows)}행 → 원본값: {failed_rows['date'].tolist()}")

            if df_ta_valid.empty:
                st.warning("날짜 파싱에 실패했습니다. TotalAssets 시트의 date 컬럼 형식(예: 2026-05-08)을 확인해주세요.")
            else:
                latest = df_ta_valid.iloc[-1]

                # ── [신규 기능 1] 목표 달성률 게이지 ──
                st.subheader("🎯 은퇴 목표 달성률")
                goal_asset = st.number_input(
                    "은퇴 목표 자산 설정 (원)",
                    value=1_500_000_000,
                    step=100_000_000,
                    format="%d",
                    help="목표 자산을 변경하면 달성률이 즉시 업데이트됩니다.",
                    key="goal_asset_input"
                )
                current_grand = int(latest['grand_total'])
                achievement_pct = min((current_grand / goal_asset) * 100, 100) if goal_asset > 0 else 0
                remaining = max(goal_asset - current_grand, 0)

                ga1, ga2, ga3 = st.columns(3)
                ga1.metric("현재 통합 총자산", f"{current_grand:,}원")
                ga2.metric("목표 달성률", f"{achievement_pct:.1f}%")
                ga3.metric("남은 금액", f"{remaining:,}원")

                # 게이지 바 시각화
                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=achievement_pct,
                    number={'suffix': '%', 'font': {'size': 36}},
                    delta={'reference': 100, 'suffix': '%', 'valueformat': '.1f'},
                    gauge={
                        'axis': {'range': [0, 100], 'ticksuffix': '%'},
                        'bar': {'color': '#2ecc71' if achievement_pct >= 80 else '#f39c12' if achievement_pct >= 50 else '#e74c3c'},
                        'steps': [
                            {'range': [0, 50],  'color': '#fdecea'},
                            {'range': [50, 80], 'color': '#fef9e7'},
                            {'range': [80, 100],'color': '#eafaf1'},
                        ],
                        'threshold': {'line': {'color': 'gold', 'width': 4}, 'thickness': 0.75, 'value': 100}
                    },
                    title={'text': f"목표 {goal_asset:,}원 대비 달성률", 'font': {'size': 14}}
                ))
                fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=10))
                st.plotly_chart(fig_gauge, use_container_width=True)

                st.divider()

                # ── 최근 3개월 자산 추이 그래프 ──
                st.subheader(f"📊 {latest['date_clean']} 통합 자산 요약")
                c1, c2, c3 = st.columns(3)
                c1.metric("통합 총자산", f"{int(latest['grand_total']):,}원")
                c2.metric("연금자산",   f"{int(latest['pension_total']):,}원")
                c3.metric("개인자산",   f"{int(latest['personal_total']):,}원")

                st.divider()

                df_plot = df_ta_valid.tail(3).copy()
                df_plot['display_date'] = df_plot['date_dt'].dt.strftime('%y년 %m월')

                fig_ct = go.Figure()
                fig_ct.add_trace(go.Bar(
                    x=df_plot['display_date'], y=df_plot['pension_total'],
                    name='연금자산', marker_color='#1f77b4',
                    hovertemplate='연금자산: %{customdata}억원<extra></extra>',
                    customdata=[round(v / 1e8, 1) for v in df_plot['pension_total']]
                ))
                fig_ct.add_trace(go.Bar(
                    x=df_plot['display_date'], y=df_plot['personal_total'],
                    name='개인자산', marker_color='#ff7f0e',
                    hovertemplate='개인자산: %{customdata}억원<extra></extra>',
                    customdata=[round(v / 1e8, 1) for v in df_plot['personal_total']]
                ))
                fig_ct.add_trace(go.Scatter(
                    x=df_plot['display_date'], y=df_plot['grand_total'],
                    name='통합총자산', mode='lines+markers',
                    line=dict(color='gold', width=4), marker=dict(size=8),
                    hovertemplate='총자산: %{customdata}억원<extra></extra>',
                    customdata=[round(v / 1e8, 1) for v in df_plot['grand_total']]
                ))

                max_ct = df_plot['grand_total'].max() * 1.3 if not df_plot.empty else 1e9
                for _, row in df_plot.iterrows():
                    fig_ct.add_annotation(
                        x=row['display_date'], y=row['grand_total'],
                        text=f"<b>{int(row['grand_total']):,}원</b>",
                        showarrow=False, yshift=14,
                        font=dict(size=11, color="#333333"),
                        bgcolor="rgba(255,255,255,0.85)", borderpad=3,
                        xanchor='center', yanchor='bottom'
                    )

                tick_step_ct = 5e8 if max_ct > 20e8 else 2e8 if max_ct > 10e8 else 1e8
                tick_vals_ct = list(range(0, int(max_ct) + int(tick_step_ct), int(tick_step_ct)))
                tick_texts_ct = [f"{int(v / 1e8)}억" for v in tick_vals_ct]

                fig_ct.update_layout(
                    barmode='stack', height=500,
                    title="최근 3개월 데이터 자산 추이",
                    xaxis=dict(type='category'),
                    yaxis=dict(tickvals=tick_vals_ct, ticktext=tick_texts_ct, range=[0, max_ct]),
                    margin=dict(l=20, r=20, t=50, b=20),
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                )
                st.plotly_chart(fig_ct, use_container_width=True)

                if pd.notnull(latest.get('insight', None)):
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
                    conn.update(worksheet="Milestones", data=pd.concat([df_ms, new_ms], ignore_index=True))
                    st.rerun()
        with c2:
            st.subheader("💰 통합자산 기록 업데이트")
            with st.form("in_ta_tower"):
                ta_d = st.date_input("데이터 기준일", now_kst)
                ta_p = st.number_input("연금자산 합계(원)", step=1000000)
                ta_s = st.number_input("개인자산 합계(원)", step=1000000)
                ta_i = st.text_area("인사이트 및 메모")
                if st.form_submit_button("통합자산 데이터 저장"):
                    new_ta = pd.DataFrame([{"date": str(ta_d), "pension_total": ta_p, "personal_total": ta_s, "grand_total": ta_p + ta_s, "insight": ta_i}])
                    conn.update(worksheet="TotalAssets", data=pd.concat([df_ta.drop(columns=['date_dt', 'display_date', 'date_clean'], errors='ignore'), new_ta], ignore_index=True))
                    st.rerun()

# =========================================================
# [전략 로직: 리밸런싱 관리]
# =========================================================
elif strat_mode == "🔄 리밸런싱":
    st.header("🔄 자산 리밸런싱 아카이브")
    df_reb = load_data_safe("Rebalancing")
    st.info("💡26년(70:30) → 27년(60:40) → 28년(50:50), 29년 이후 배당 ETF, 마켓금리액티브 매수")

    with st.form("reb_in_form_v2"):
        c1, c2 = st.columns(2)
        r_date  = c1.date_input("리밸런싱 실행 날짜", now_kst)
        r_strat = c1.text_input("현재 전략 비중 (예: 70:30)")
        r_action = c2.text_area("실행 내역 (매수/매도 상세)")
        r_reason = st.text_area("리밸런싱 판단 근거")
        r_target = c2.text_input("조정 후 목표 비중")
        if st.form_submit_button("리밸런싱 내역 저장"):
            new_reb = pd.DataFrame([{"date": str(r_date), "strategy": r_strat, "action": r_action, "reason": r_reason, "target_ratio": r_target}])
            conn.update(worksheet="Rebalancing", data=pd.concat([df_reb, new_reb], ignore_index=True))
            st.rerun()

    if not df_reb.empty:
        st.divider()
        for i, row in df_reb.iloc[::-1].iterrows():
            with st.expander(f"📅 {row['date']} 리밸런싱 실행 기록"):
                st.write(f"**전략 비중:** {row['strategy']} → **목표 비중:** {row['target_ratio']}")
                st.write(f"**상세 액션:** {row['action']}")
                st.caption(f"**판단 근거:** {row['reason']}")
                if st.button("내역 삭제", key=f"reb_del_btn_{i}"):
                    conn.update(worksheet="Rebalancing", data=df_reb.drop(i))
                    st.rerun()

# =========================================================
# [일반 모드]
# =========================================================
elif strat_mode == "일반 모드":

    # =========================================================
    # [1. 연금자산]
    # =========================================================
    if menu == "💰 연금자산":
        st.header("💰 연금자산 관리")
        df_p = load_data_safe("Data")
        t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])

        with t1:
            if not df_p.empty and 'date' in df_p.columns:
                df_p['date_dt'] = pd.to_datetime(df_p['date'], format='%Y-%m', errors='coerce')
                dates_sorted_dt = sorted(df_p['date_dt'].dropna().unique())

                if dates_sorted_dt:
                    recent_dt     = dates_sorted_dt[-3:]
                    recent_labels = [d.strftime('%y년 %m월') for d in recent_dt]
                    recent_str    = [d.strftime('%Y-%m') for d in recent_dt]
                    df_r = df_p[df_p['date'].isin(recent_str)].copy()

                    m_total = df_r.groupby('date_dt')['amount'].sum().reindex(recent_dt).fillna(0)
                    cur  = m_total.iloc[-1]
                    prev = m_total.iloc[-2] if len(m_total) > 1 else cur
                    diff = cur - prev

                    c1, c2 = st.columns(2)
                    c1.metric(f"{recent_labels[-1]} 합계", f"{int(cur):,}원")
                    c2.metric("전월 대비", f"{(diff / prev * 100) if prev != 0 else 0:+.1f}%", f"{int(diff):+,}원")

                    fig = go.Figure()
                    for acc in sorted(df_r['account'].unique()):
                        acc_df = df_r[df_r['account'] == acc].set_index('date_dt').reindex(recent_dt).fillna(0).reset_index()
                        hover_texts = [f"{acc}: {int(round(v / 1e6))}백만원" for v in acc_df['amount']]
                        fig.add_trace(go.Bar(
                            x=recent_labels, y=acc_df['amount'], name=acc,
                            hovertext=hover_texts, hoverinfo='text'
                        ))

                    max_y = m_total.max() * 1.3 if m_total.max() > 0 else 1e9
                    tick_step = 1e8
                    tick_vals  = list(range(0, int(max_y) + int(tick_step), int(tick_step)))
                    tick_texts = [f"{int(v / 1e8)}억" for v in tick_vals]

                    for i, (label, dt) in enumerate(zip(recent_labels, recent_dt)):
                        total_val = m_total.iloc[i] if i < len(m_total) else 0
                        fig.add_annotation(
                            x=label, y=total_val,
                            text=f"<b>{int(total_val):,}원</b>",
                            showarrow=False, yshift=14,
                            font=dict(size=12, color="#333333"),
                            bgcolor="rgba(255,255,255,0.85)", borderpad=3,
                            xanchor='center', yanchor='bottom'
                        )

                    fig.update_layout(
                        barmode='stack', height=500,
                        xaxis=dict(type='category'),
                        yaxis=dict(tickvals=tick_vals, ticktext=tick_texts, range=[0, max_y]),
                        margin=dict(l=20, r=20, t=50, b=20),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True)

        with t2:
            c1, c2 = st.columns(2)
            py    = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
            pm    = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1, key="p_m")
            p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
            p_amt = st.number_input("금액(원)", step=100000)

            if st.button("연금 데이터 저장"):
                df = load_data_safe("Data")
                t_date = f"{py}-{pm}"
                mask = (df['date'] == t_date) & (df['account'] == p_acc)
                if mask.any():
                    df.loc[mask, 'amount'] = int(p_amt)
                else:
                    df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc, "amount": int(p_amt), "memo": ""}])], ignore_index=True)
                conn.update(worksheet="Data", data=df)
                st.toast("연금 정보가 저장되었습니다!")
                st.rerun()

    # =========================================================
    # [2. 연금시뮬]
    # =========================================================
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
                base_asset      = st.number_input("기초 자산 (현재연금+퇴직금)", value=int(current_total + 490000000), step=10000000)
                monthly_withdraw = st.slider("월 희망 수령액 (만 원)", 300, 1000, 450) * 10000
                annual_return   = st.slider("기대 연 수익률 (%)", 0.0, 10.0, 4.0, 0.5) / 100
                inflation_rate  = st.slider("예상 물가 상승률 (%)", 0.0, 5.0, 2.0, 0.5) / 100
                start_y = st.selectbox("시뮬레이션 시작 연도", range(2029, 2040), index=0)
                end_y   = st.selectbox("시뮬레이션 종료 연도", range(start_y + 1, 2075), index=25)
                use_national = st.checkbox("2038년 8월부터 월 150만원 합산", value=True)

            with c2:
                months = (end_y - start_y + 1) * 12
                dates  = pd.date_range(start=f"{start_y}-01-01", periods=months, freq='MS')
                asset_history, cur_asset, cur_withdraw = [], base_asset, monthly_withdraw

                for d in dates:
                    cur_asset *= (1 + annual_return / 12)
                    if d.month == 1:
                        cur_withdraw *= (1 + inflation_rate)
                    net_withdraw = max(0, cur_withdraw - 1500000) if use_national and d >= pd.Timestamp(2038, 8, 1) else cur_withdraw
                    cur_asset -= net_withdraw
                    if cur_asset < 0:
                        cur_asset = 0
                    asset_history.append(cur_asset)

                sim_df = pd.DataFrame({"날짜": dates, "잔액": asset_history})

                max_asset = max(asset_history) if asset_history else 1e9
                tick_step_eok = 5e8 if max_asset > 20e8 else 2e8 if max_asset > 10e8 else 1e8
                tick_vals_sim  = list(range(0, int(max_asset * 1.15) + int(tick_step_eok), int(tick_step_eok)))
                tick_texts_sim = [f"{int(v / 1e8)}억" for v in tick_vals_sim]

                sim_df['hover'] = sim_df['잔액'].apply(lambda v: f"{v / 1e8:.1f}억원")

                fig_sim = go.Figure()
                fig_sim.add_trace(go.Scatter(
                    x=sim_df['날짜'], y=sim_df['잔액'],
                    fill='tozeroy', mode='lines', name='잔액',
                    hovertext=sim_df['hover'], hoverinfo='x+text',
                    line=dict(color='#1f77b4')
                ))
                fig_sim.update_layout(
                    title=f"월 {int(monthly_withdraw / 10000)}만원 인출 시 자산 추이",
                    xaxis=dict(tickformat="%y년"),
                    yaxis=dict(tickvals=tick_vals_sim, ticktext=tick_texts_sim),
                    height=450, margin=dict(l=20, r=20, t=40, b=20)
                )
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

    # =========================================================
    # [3. 현금흐름]
    # =========================================================
    elif menu == "💸 현금흐름":
        st.header("💸 현금흐름 관리 (은퇴 준비)")
        df_cf = load_data_safe("CashFlow")
        df_bg = load_data_safe("Budgets")

        CF_CATEGORIES = ["급여", "기타수익", "자기계발", "문화생활", "저축/투자", "쇼핑", "외식", "생활비", "마트",
                         "통신비, 구독료", "교통비", "보험", "여행", "명절, 이벤트", "용돈", "기타"]

        c_f1, c_f2 = st.columns(2)
        sel_y = c_f1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1)
        sel_m = c_f2.selectbox("조회 월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1)
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
                c1.metric("소비 상태", f"{percent:.1f}%", f"{int(current_budget - total_spent):,}원 남음")

        with t2:
            with st.form("cf_form_v3", clear_on_submit=True):
                c1, c2 = st.columns(2)
                f_date = c1.date_input("날짜", now_kst)
                f_type = c1.selectbox("구분", ["EXPENSE", "INCOME"])
                f_cat  = c2.selectbox("카테고리", CF_CATEGORIES)
                f_amt  = c2.number_input("금액", min_value=0, step=1000)
                f_memo = st.text_input("메모")
                f_rec  = st.checkbox("정기 지출/수입 여부")
                if st.form_submit_button("현금흐름 기록 저장"):
                    new_data = pd.DataFrame([{"date": str(f_date), "type": f_type, "category": f_cat, "amount": f_amt, "memo": f_memo, "is_recurring": str(f_rec).upper()}])
                    conn.update(worksheet="CashFlow", data=pd.concat([df_cf.drop(columns=['date_dt'], errors='ignore'), new_data], ignore_index=True))
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
                m_data = df_cf[pd.to_datetime(df_cf['date'], errors='coerce').dt.strftime("%Y-%m") == sel_period].copy()
                if not m_data.empty:
                    m_data = m_data.sort_values('date', ascending=False)
                    edit_list = m_data.apply(
                        lambda x: f"[{x['date']}] {x['category']} - {x['memo']} ({int(x['amount']):,}원)", axis=1
                    ).tolist()
                    sel_item = st.selectbox("수정/삭제할 항목 선택 (최신순)", options=edit_list)
                    sel_idx  = m_data.index[edit_list.index(sel_item)]

                    with st.form("edit_cf_full"):
                        ec1, ec2 = st.columns(2)
                        e_date = ec1.date_input("날짜 수정", value=pd.to_datetime(df_cf.loc[sel_idx, 'date']).date())
                        e_type = ec1.selectbox("구분 수정", ["EXPENSE", "INCOME"], index=0 if df_cf.loc[sel_idx, 'type'] == "EXPENSE" else 1)
                        e_cat  = ec2.selectbox("카테고리 수정", CF_CATEGORIES, index=CF_CATEGORIES.index(df_cf.loc[sel_idx, 'category']) if df_cf.loc[sel_idx, 'category'] in CF_CATEGORIES else 0)
                        e_amt  = ec2.number_input("금액 수정", value=int(df_cf.loc[sel_idx, 'amount']))
                        e_memo = st.text_input("메모 수정", value=str(df_cf.loc[sel_idx, 'memo']))
                        b1, b2 = st.columns(2)
                        if b1.form_submit_button("💾 수정 완료"):
                            df_cf.at[sel_idx, 'date']     = str(e_date)
                            df_cf.at[sel_idx, 'type']     = e_type
                            df_cf.at[sel_idx, 'category'] = e_cat
                            df_cf.at[sel_idx, 'amount']   = e_amt
                            df_cf.at[sel_idx, 'memo']     = e_memo
                            conn.update(worksheet="CashFlow", data=df_cf.drop(columns=['date_dt'], errors='ignore'))
                            st.rerun()
                        if b2.form_submit_button("🗑️ 삭제 완료"):
                            conn.update(worksheet="CashFlow", data=df_cf.drop(sel_idx).drop(columns=['date_dt'], errors='ignore'))
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

    # =========================================================
    # [4. 개인자산]
    # =========================================================
    elif menu == "💵 개인자산":
        st.header("💵 개인자산 관리")
        df_per = load_data_safe("PersonalData")
        t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])

        with t1:
            if not df_per.empty and 'date' in df_per.columns:
                weeks  = sorted([str(d) for d in df_per['date'].unique()])
                if weeks:
                    recent        = weeks[-3:]
                    df_r          = df_per[df_per['date'].isin(recent)]
                    w_total       = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                    cur           = w_total.iloc[-1]
                    prev          = w_total.iloc[-2] if len(w_total) > 1 else cur
                    recent_labels = [week_key_to_label(k) for k in recent]

                    c1, c2 = st.columns(2)
                    c1.metric(f"{recent_labels[-1]} 합계", f"{int(cur):,}원")
                    c2.metric("전주 대비", f"{((cur - prev) / prev * 100) if prev != 0 else 0:+.1f}%", f"{int(cur - prev):+,}원")

                    fig = go.Figure()
                    for acc in sorted(df_r['account'].unique()):
                        acc_df = df_r[df_r['account'] == acc].set_index('date').reindex(recent).fillna(0).reset_index()
                        hover_texts = [f"{acc}: {int(round(v / 1e6))}백만원" for v in acc_df['amount']]
                        fig.add_trace(go.Bar(
                            x=recent_labels, y=acc_df['amount'], name=acc,
                            hovertext=hover_texts, hoverinfo='text'
                        ))

                    max_y_per    = w_total.max() * 1.3 if w_total.max() > 0 else 1e8
                    tick_step_per = 1e8 if max_y_per > 5e8 else 5e7
                    tick_vals_per, tick_texts_per = [], []
                    for v in range(0, int(max_y_per) + int(tick_step_per), int(tick_step_per)):
                        tick_vals_per.append(v)
                        eok_v = v / 1e8
                        if eok_v >= 1:
                            tick_texts_per.append(f"{int(eok_v)}억" if eok_v == int(eok_v) else f"{eok_v:.1f}억")
                        else:
                            tick_texts_per.append(f"{v / 1e7:.0f}천만")

                    for i, (label, wk) in enumerate(zip(recent_labels, recent)):
                        total_val = w_total.iloc[i] if i < len(w_total) else 0
                        fig.add_annotation(
                            x=label, y=total_val,
                            text=f"<b>{int(total_val):,}원</b>",
                            showarrow=False, yshift=14,
                            font=dict(size=12, color="#333333"),
                            bgcolor="rgba(255,255,255,0.85)", borderpad=3,
                            xanchor='center', yanchor='bottom'
                        )

                    fig.update_layout(
                        barmode='stack', height=500,
                        xaxis=dict(type='category'),
                        yaxis=dict(tickvals=tick_vals_per, ticktext=tick_texts_per, range=[0, max_y_per]),
                        margin=dict(l=20, r=20, t=50, b=20),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                    )
                    st.plotly_chart(fig, use_container_width=True)

        with t2:
            st.subheader("📝 개인자산 입력")
            c1, c2, c3 = st.columns(3)
            pery     = c1.selectbox("연도", [2026, 2027, 2028], key="per_y_sel")
            perm     = c2.selectbox("월", [f"{i}월" for i in range(1, 13)], index=now_kst.month - 1, key="per_m_sel")
            perm_int = int(perm.replace("월", ""))

            week_options = get_month_weeks(pery, perm_int)
            if not week_options:
                week_options = [(f"{str(pery)[2:]}년 {perm_int}월 1주", f"Y{pery}W{datetime.date(pery, perm_int, 1).isocalendar()[1]}")]

            week_labels = [w[0] for w in week_options]
            week_keys   = [w[1] for w in week_options]
            current_week_key = f"Y{now_kst.year}W{now_kst.isocalendar()[1]}"
            default_idx = 0
            for i, wk in enumerate(week_keys):
                if wk == current_week_key:
                    default_idx = i
                    break

            sel_week_label = c3.selectbox("주차 선택", week_labels, index=default_idx, key="per_w_sel")
            sel_week_key   = week_keys[week_labels.index(sel_week_label)]

            p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
            per_amt   = st.number_input("현재 잔액(원)", step=10000)
            st.caption(f"📌 선택된 주차 키: `{sel_week_key}` → 대시보드에 **{sel_week_label}** 로 표시됩니다.")

            if st.button("개인자산 정보 저장"):
                df   = load_data_safe("PersonalData")
                mask = (df['date'] == sel_week_key) & (df['account'] == p_acc_per)
                if mask.any():
                    df.loc[mask, 'amount'] = int(per_amt)
                else:
                    df = pd.concat([df, pd.DataFrame([{"date": sel_week_key, "account": p_acc_per, "amount": int(per_amt), "memo": ""}])], ignore_index=True)
                conn.update(worksheet="PersonalData", data=df)
                st.toast("저장 완료!")
                st.rerun()

    # =========================================================
    # [5. 영어공부]
    # =========================================================
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
                sel_en    = st.selectbox("수정할 문장 선택", options=edit_list)
                en_idx    = df_en.index[edit_list.index(sel_en)]
                with st.form("edit_en"):
                    e_en = st.text_input("영어 수정", value=str(df_en.loc[en_idx, 'english']))
                    e_ko = st.text_input("한글 수정", value=str(df_en.loc[en_idx, 'korean']))
                    if st.form_submit_button("💾 문장 수정 저장"):
                        df_en.at[en_idx, 'english'] = e_en
                        df_en.at[en_idx, 'korean']  = e_ko
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
                q   = unmem.loc[st.session_state.q_idx]
                st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력해 보세요", key="quiz_input")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower():
                        st.success("Perfect!")
                        st.balloons()
                    else:
                        st.error(f"Try again! 정답: {q['english']}")
                st.button("다음 문제로", on_click=reset_quiz)

    # =========================================================
    # [6. 도서관리] ── [신규 기능 2] 독서 목표 & 페이스 추가
    # =========================================================
    elif menu == "📚 도서관리":
        st.header("📚 도서 관리 시스템")
        df_books = load_data_safe("Books")

        # ── 연간 통계 헤더 ──
        if not df_books.empty:
            c1, c2, c3 = st.columns([1, 1, 2])
            sel_y_book = c1.selectbox("통계 조회 연도", options=["2026년", "2027년", "2028년"])
            y_int = int(sel_y_book.replace("년", ""))
            y_df  = df_books[pd.to_datetime(df_books['날짜'], errors='coerce').dt.year == y_int]
            c2.metric(f"{y_int}년 완독수",      f"{len(y_df)} 권")
            c3.metric(f"{y_int}년 누적 도서비", f"₩{int(y_df['가격'].sum()):,}")

        st.divider()

        tab1, tab2, tab3, tab4 = st.tabs(["📖 나의 서재", "🎯 독서 목표 & 페이스", "➕ 신규 도서 등록", "✏️ 도서 정보 수정/삭제"])

        with tab1:
            if not df_books.empty:
                st.table(df_books.iloc[::-1][['날짜', '제목', '저자', '가격', '구입처', '분류']].head(15))

        # ── [신규 기능 2] 독서 목표 & 페이스 탭 ──
        with tab2:
            st.subheader("🎯 독서 목표 달성 현황")

            if not df_books.empty:
                goal_year = st.selectbox("연도 선택", [2026, 2027, 2028], key="goal_year_sel")
                goal_books = st.number_input("연간 목표 권수", min_value=1, max_value=100, value=24, step=1, key="goal_books_input")

                # 해당 연도 도서 필터
                df_books['날짜_dt'] = pd.to_datetime(df_books['날짜'], errors='coerce')
                year_df = df_books[df_books['날짜_dt'].dt.year == goal_year].copy()
                read_count = len(year_df)

                # 달성률 계산
                achieve_pct = min((read_count / goal_books) * 100, 100) if goal_books > 0 else 0
                remaining_books = max(goal_books - read_count, 0)

                # 현재 날짜 기준 연간 페이스 계산
                year_start = datetime.date(goal_year, 1, 1)
                year_end   = datetime.date(goal_year, 12, 31)
                today      = now_kst
                days_passed  = max((min(today, year_end) - year_start).days + 1, 1)
                days_total   = (year_end - year_start).days + 1
                days_remaining = max((year_end - today).days, 0)

                # 이 페이스라면 연말 예상 완독 수
                expected_total = int(read_count / days_passed * days_total) if days_passed > 0 else 0
                # 목표 달성을 위해 남은 기간 동안 읽어야 할 권수
                pace_needed = f"{remaining_books / (days_remaining / 30):.1f}권/월" if days_remaining > 0 else "목표 달성!"

                # 지표 표시
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("올해 완독", f"{read_count}권", f"목표 {goal_books}권")
                m2.metric("달성률",    f"{achieve_pct:.0f}%")
                m3.metric("연말 예상", f"{expected_total}권", f"{'초과 👍' if expected_total >= goal_books else '부족 📚'}")
                m4.metric("남은 목표 페이스", pace_needed)

                # 진행 게이지
                fig_book_gauge = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=achieve_pct,
                    number={'suffix': '%', 'font': {'size': 32}},
                    gauge={
                        'axis': {'range': [0, 100], 'ticksuffix': '%'},
                        'bar': {'color': '#2ecc71' if achieve_pct >= 80 else '#f39c12' if achieve_pct >= 50 else '#3498db'},
                        'steps': [
                            {'range': [0, 50],   'color': '#eaf4fb'},
                            {'range': [50, 80],  'color': '#fef9e7'},
                            {'range': [80, 100], 'color': '#eafaf1'},
                        ],
                        'threshold': {'line': {'color': 'gold', 'width': 4}, 'thickness': 0.75, 'value': 100}
                    },
                    title={'text': f"{goal_year}년 독서 목표 달성률 ({read_count}/{goal_books}권)", 'font': {'size': 14}}
                ))
                fig_book_gauge.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
                st.plotly_chart(fig_book_gauge, use_container_width=True)

                # 월별 독서 현황 바 차트
                if not year_df.empty:
                    st.divider()
                    st.subheader("📅 월별 독서 현황")
                    year_df['월'] = year_df['날짜_dt'].dt.month
                    monthly_counts = year_df.groupby('월').size().reset_index(name='권수')
                    # 1~12월 전체 채우기
                    all_months = pd.DataFrame({'월': range(1, 13)})
                    monthly_counts = all_months.merge(monthly_counts, on='월', how='left').fillna(0)
                    monthly_counts['권수'] = monthly_counts['권수'].astype(int)
                    monthly_counts['월명'] = monthly_counts['월'].apply(lambda m: f"{m}월")

                    # 목표 페이스 선 (월 목표)
                    monthly_goal = goal_books / 12

                    fig_monthly = go.Figure()
                    fig_monthly.add_trace(go.Bar(
                        x=monthly_counts['월명'],
                        y=monthly_counts['권수'],
                        name='완독 권수',
                        marker_color=['#2ecc71' if v >= monthly_goal else '#3498db' for v in monthly_counts['권수']],
                        text=monthly_counts['권수'],
                        textposition='outside'
                    ))
                    fig_monthly.add_trace(go.Scatter(
                        x=monthly_counts['월명'],
                        y=[monthly_goal] * 12,
                        name=f'월 목표 ({monthly_goal:.1f}권)',
                        mode='lines',
                        line=dict(color='gold', width=2, dash='dash')
                    ))
                    fig_monthly.update_layout(
                        height=320,
                        xaxis=dict(type='category'),
                        yaxis=dict(title='권수', dtick=1),
                        margin=dict(l=20, r=20, t=30, b=20),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                    )
                    st.plotly_chart(fig_monthly, use_container_width=True)

                    # 장르별 분포
                    st.divider()
                    st.subheader("📊 장르별 독서 분포")
                    genre_counts = year_df['분류'].value_counts().reset_index()
                    genre_counts.columns = ['분류', '권수']
                    fig_genre = px.pie(genre_counts, values='권수', names='분류', hole=0.4,
                                       title=f"{goal_year}년 장르 분포")
                    fig_genre.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_genre, use_container_width=True)
            else:
                st.info("도서를 먼저 등록해주세요.")

        with tab3:
            with st.form("book_reg_cloud", clear_on_submit=True):
                tc1, tc2 = st.columns(2)
                t  = tc1.text_input("도서 제목 (필수)")
                a  = tc1.text_input("저자")
                p  = tc1.number_input("구입 가격", step=1000)
                s  = tc1.text_input("구입처")
                d  = tc2.date_input("구입/읽은 날짜", now_kst)
                cat = tc2.selectbox("도서 분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"])
                r  = tc2.slider("나의 별점", 1, 5, 5)
                cmt = st.text_area("한줄평 및 메모")
                if st.form_submit_button("도서 정보 저장"):
                    if t:
                        new_book = pd.DataFrame([{'날짜': str(d), '제목': t, '저자': a, '가격': int(p), '구입처': s, '분류': cat, '별점': int(r), '코멘트': cmt, '연도': d.year}])
                        conn.update(worksheet="Books", data=pd.concat([df_books, new_book], ignore_index=True))
                        st.success("서재에 추가되었습니다!")
                        st.rerun()
                    else:
                        st.warning("제목을 입력해주세요.")

        with tab4:
            if not df_books.empty:
                df_books_sorted = df_books.copy()
                df_books_sorted['날짜_dt'] = pd.to_datetime(df_books_sorted['날짜'], errors='coerce')
                df_books_sorted = df_books_sorted.sort_values('날짜_dt', ascending=False)
                edit_list = df_books_sorted.apply(lambda x: f"{x['날짜']} | {x['제목']} ({x['저자']})", axis=1).tolist()
                sel_b  = st.selectbox("수정할 책 선택 (최신순)", options=edit_list)
                b_idx  = df_books_sorted.index[edit_list.index(sel_b)]
                with st.form("edit_book_full"):
                    ec1, ec2 = st.columns(2)
                    e_t   = ec1.text_input("제목 수정",  value=df_books.loc[b_idx, '제목'])
                    e_a   = ec1.text_input("저자 수정",  value=df_books.loc[b_idx, '저자'])
                    e_p   = ec1.number_input("가격 수정", value=int(df_books.loc[b_idx, '가격']))
                    e_s   = ec1.text_input("구입처 수정", value=str(df_books.loc[b_idx, '구입처']))
                    cat_list = ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"]
                    cur_cat  = df_books.loc[b_idx, '분류']
                    cat_idx  = cat_list.index(cur_cat) if cur_cat in cat_list else 0
                    e_cat = ec2.selectbox("분류 수정", cat_list, index=cat_idx)
                    e_r   = ec2.slider("별점 수정", 1, 5, int(df_books.loc[b_idx, '별점']))
                    e_cmt = st.text_area("코멘트 수정", value=str(df_books.loc[b_idx, '코멘트']))
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 수정사항 저장"):
                        df_books.loc[b_idx, ['제목', '저자', '가격', '구입처', '분류', '별점', '코멘트']] = [e_t, e_a, e_p, e_s, e_cat, e_r, e_cmt]
                        conn.update(worksheet="Books", data=df_books)
                        st.rerun()
                    if c2.form_submit_button("🗑️ 도서 삭제"):
                        conn.update(worksheet="Books", data=df_books.drop(b_idx))
                        st.rerun()

    # =========================================================
    # [7. 여행관리]
    # =========================================================
    elif menu == "✈️ 여행관리":
        st.header("✈️ Byungjoo 여행기록")
        df_dest = load_data_safe("TravelDest")
        df_exp  = load_data_safe("TravelExp")
        METHODS = ["하나카드", "트래블월렛", "삼성카드", "현금"]

        t_home, t_ledger, t_timeline, t_stats, t_edit = st.tabs(["🗺️ 여행지 관리", "💰 비용 기록", "🗓️ 타임라인", "📊 지출 요약", "⚙️ 내역 수정/삭제"])

        with t_home:
            st.subheader("📍 새 여행 계획/완료 등록")
            with st.form("new_dest_form", clear_on_submit=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                new_name   = c1.text_input("여행지명")
                new_start  = c2.date_input("출발일", now_kst)
                new_end    = c2.date_input("도착일", now_kst + timedelta(days=3))
                new_status = c3.selectbox("여행 상태", ["준비", "여행중", "완료"])
                if st.form_submit_button("여행지 추가"):
                    if new_name:
                        new_id  = int(df_dest['id'].max() + 1) if not df_dest.empty else 1
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
                            en  = e1.text_input("여행지명 수정", value=row['name'])
                            es  = e2.date_input("출발일 수정",   value=pd.to_datetime(row['start_date']).date())
                            ee  = e2.date_input("도착일 수정",   value=pd.to_datetime(row['end_date']).date())
                            est = e3.selectbox("상태 수정", ["준비", "여행중", "완료"], index=["준비", "여행중", "완료"].index(row['status']))
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 여행지 정보 저장"):
                                df_dest.at[i, 'name'], df_dest.at[i, 'start_date'], df_dest.at[i, 'end_date'], df_dest.at[i, 'status'] = en, str(es), str(ee), est
                                conn.update(worksheet="TravelDest", data=df_dest)
                                st.rerun()
                            if b2.form_submit_button("🗑️ 여행지 전체 삭제"):
                                conn.update(worksheet="TravelDest", data=df_dest.drop(i))
                                st.rerun()

        if not df_dest.empty:
            sel_city = st.sidebar.selectbox("📍 여행지 선택", options=df_dest['name'].tolist())
            curr_row = df_dest[df_dest['name'] == sel_city]
            if not curr_row.empty:
                curr  = curr_row.iloc[0]
                d_exp = df_exp[df_exp['dest_id'] == curr['id']].copy() if not df_exp.empty else pd.DataFrame()

                with t_ledger:
                    st.metric(f"'{sel_city}' 누적 비용", f"₩{int(d_exp['amount'].sum()):,}" if not d_exp.empty else "₩0")
                    with st.expander("➕ 실시간 지출 기록", expanded=True):
                        with st.form("t_add_v5", clear_on_submit=True):
                            c1, c2 = st.columns(2)
                            d_input = c1.date_input("날짜", now_kst)
                            it  = c2.text_input("소비 항목")
                            pl  = c1.text_input("사용 장소")
                            amt = c2.number_input("지출 금액", min_value=0)
                            cat = c1.selectbox("카테고리", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"])
                            met = c2.selectbox("결제 수단", METHODS)
                            if st.form_submit_button("💰 비용 저장 및 초기화"):
                                new_e = pd.DataFrame([{'dest_id': curr['id'], 'date': str(d_input), 'time': '12:00', 'item': it, 'place': pl, 'category': cat, 'method': met, 'amount': int(amt), 'unit': 'KRW', 'memo': ''}])
                                conn.update(worksheet="TravelExp", data=pd.concat([df_exp, new_e], ignore_index=True))
                                st.success("기록되었습니다.")
                                st.rerun()

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
                            e_it   = ec1.text_input("항목명 수정", value=d_exp.loc[t_idx, 'item'])
                            e_pl   = ec1.text_input("장소 수정",   value=d_exp.loc[t_idx, 'place'])
                            e_amt  = ec2.number_input("금액 수정", value=int(d_exp.loc[t_idx, 'amount']))
                            e_cat  = ec2.selectbox("카테고리 수정", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"], index=0)
                            e_met  = ec2.selectbox("수단 수정", METHODS, index=METHODS.index(d_exp.loc[t_idx, 'method']) if d_exp.loc[t_idx, 'method'] in METHODS else 0)
                            b1, b2 = st.columns(2)
                            if b1.form_submit_button("💾 지출 정보 수정 저장"):
                                df_exp.loc[t_idx, ['date', 'item', 'place', 'amount', 'category', 'method']] = [str(e_date), e_it, e_pl, e_amt, e_cat, e_met]
                                conn.update(worksheet="TravelExp", data=df_exp)
                                st.rerun()
                            if b2.form_submit_button("🗑️ 지출 항목 삭제"):
                                conn.update(worksheet="TravelExp", data=df_exp.drop(t_idx))
                                st.rerun()

    # =========================================================
    # [8. 다이어리]
    # =========================================================
    elif menu == "📓 다이어리":
        st.header("📓 Byungjoo's 다이어리 & 아이디어")
        df_diary = load_data_safe("Diary")
        dt1, dt2 = st.tabs(["📝 신규 기록 남기기", "📖 전체 기록 확인 및 수정"])

        with dt1:
            with st.form("diary_in", clear_on_submit=True):
                d_title   = st.text_input("기록 제목")
                d_tags    = st.multiselect("태그 선택", ["아이디어", "회고", "계획", "학습", "일상"])
                d_content = st.text_area("내용을 자유롭게 적어주세요", height=200)
                if st.form_submit_button("생각 저장하기"):
                    new_diary = pd.DataFrame([{'date': str(now_kst), 'title': d_title, 'content': d_content, 'tags': ", ".join(d_tags), 'level': 'Normal'}])
                    conn.update(worksheet="Diary", data=pd.concat([df_diary, new_diary], ignore_index=True))
                    st.rerun()

        with dt2:
            if not df_diary.empty:
                search_q = st.text_input("🔍 제목 키워드 검색")
                filt_df  = df_diary[df_diary['title'].str.contains(search_q, na=False)] if search_q else df_diary
                for i, row in filt_df.iloc[::-1].iterrows():
                    with st.expander(f"{row['date']} | {row['title']}"):
                        with st.form(f"edit_diary_{i}"):
                            e_title   = st.text_input("제목 수정",  value=row['title'])
                            e_content = st.text_area("내용 수정",   value=row['content'], height=150)
                            c1, c2    = st.columns(2)
                            if c1.form_submit_button("💾 메모 수정 저장"):
                                df_diary.at[i, 'title'], df_diary.at[i, 'content'] = e_title, e_content
                                conn.update(worksheet="Diary", data=df_diary)
                                st.rerun()
                            if c2.form_submit_button("🗑️ 메모 삭제"):
                                conn.update(worksheet="Diary", data=df_diary.drop(i))
                                st.rerun()

    # =========================================================
    # [9. 뉴스저장] ── [신규 기능 3] 월간 리포트 탭 추가
    # =========================================================
    elif menu == "📰 뉴스저장":
        st.header("📰 지식 큐레이션 (뉴스 & 아티클)")
        df_media = load_data_safe("Media")

        media_t1, media_t2 = st.tabs(["📰 뉴스 저장/관리", "📋 월간 리포트"])

        with media_t1:
            with st.form("media_form", clear_on_submit=True):
                m_title   = st.text_input("아티클 제목")
                m_url     = st.text_input("URL 링크")
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
                            e_m_title   = st.text_input("제목 수정",     value=row['title'])
                            e_m_url     = st.text_input("URL 수정",      value=row['url'])
                            e_m_insight = st.text_area("인사이트 수정",  value=row['insight'])
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("💾 정보 업데이트"):
                                df_media.at[i, 'title'], df_media.at[i, 'url'], df_media.at[i, 'insight'] = e_m_title, e_m_url, e_m_insight
                                conn.update(worksheet="Media", data=df_media)
                                st.rerun()
                            if c2.form_submit_button("🗑️ 지식 삭제"):
                                conn.update(worksheet="Media", data=df_media.drop(i))
                                st.rerun()
                        st.markdown(f"🔗 [기사 원문 읽기]({row['url']})")

        # ── [신규 기능 3] 월간 리포트 탭 ──
        with media_t2:
            st.subheader("📋 월간 통합 리포트")
            st.caption("각 메뉴의 데이터를 한 페이지로 자동 집계합니다.")

            # 조회 월 선택
            rp_c1, rp_c2 = st.columns(2)
            rp_year  = rp_c1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1, key="rp_year")
            rp_month = rp_c2.selectbox("조회 월",   [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1, key="rp_month")
            rp_period = f"{rp_year}-{rp_month}"

            st.divider()

            # ── 섹션 1: 자산 현황 ──
            st.markdown("### 💰 자산 현황")
            df_ta_rp = load_data_safe("TotalAssets")
            if not df_ta_rp.empty:
                df_ta_rp['date_clean'] = df_ta_rp['date'].astype(str).str.strip().str.lower()
                df_ta_rp['date_dt']    = pd.to_datetime(df_ta_rp['date_clean'], errors='coerce')
                df_ta_rp_valid = df_ta_rp.dropna(subset=['date_dt']).sort_values('date_dt')

                # 해당 월 데이터 찾기
                rp_month_data = df_ta_rp_valid[df_ta_rp_valid['date_dt'].dt.strftime('%Y-%m') == rp_period]
                prev_month_dt = (datetime.date(rp_year, int(rp_month), 1) - timedelta(days=1))
                prev_period   = prev_month_dt.strftime('%Y-%m')
                rp_prev_data  = df_ta_rp_valid[df_ta_rp_valid['date_dt'].dt.strftime('%Y-%m') == prev_period]

                if not rp_month_data.empty:
                    cur_row  = rp_month_data.iloc[-1]
                    prev_row = rp_prev_data.iloc[-1] if not rp_prev_data.empty else None

                    a1, a2, a3 = st.columns(3)
                    a1.metric("통합 총자산", f"{int(cur_row['grand_total']):,}원",
                              f"{int(cur_row['grand_total'] - prev_row['grand_total']):+,}원" if prev_row is not None else None)
                    a2.metric("연금자산",   f"{int(cur_row['pension_total']):,}원",
                              f"{int(cur_row['pension_total'] - prev_row['pension_total']):+,}원" if prev_row is not None else None)
                    a3.metric("개인자산",   f"{int(cur_row['personal_total']):,}원",
                              f"{int(cur_row['personal_total'] - prev_row['personal_total']):+,}원" if prev_row is not None else None)
                    if pd.notnull(cur_row.get('insight', None)):
                        st.info(f"💡 {rp_period} 인사이트: {cur_row['insight']}")
                else:
                    st.info(f"{rp_period} 자산 데이터가 없습니다.")

            st.divider()

            # ── 섹션 2: 현금흐름 요약 ──
            st.markdown("### 💸 현금흐름 요약")
            df_cf_rp = load_data_safe("CashFlow")
            if not df_cf_rp.empty:
                df_cf_rp['date_dt'] = pd.to_datetime(df_cf_rp['date'], errors='coerce')
                rp_cf = df_cf_rp[df_cf_rp['date_dt'].dt.strftime('%Y-%m') == rp_period]

                rp_income  = rp_cf[rp_cf['type'] == 'INCOME']['amount'].sum()
                rp_expense = rp_cf[rp_cf['type'] == 'EXPENSE']['amount'].sum()
                rp_net     = rp_income - rp_expense
                rp_save_rate = (rp_net / rp_income * 100) if rp_income > 0 else 0

                cf1, cf2, cf3, cf4 = st.columns(4)
                cf1.metric("총 수입",  f"{int(rp_income):,}원")
                cf2.metric("총 지출",  f"{int(rp_expense):,}원")
                cf3.metric("순 수지",  f"{int(rp_net):,}원", delta_color="normal")
                cf4.metric("저축률",   f"{rp_save_rate:.1f}%")

                # 카테고리별 지출 TOP 5
                if not rp_cf[rp_cf['type'] == 'EXPENSE'].empty:
                    top5 = rp_cf[rp_cf['type'] == 'EXPENSE'].groupby('category')['amount'].sum().sort_values(ascending=False).head(5).reset_index()
                    top5.columns = ['카테고리', '금액']
                    top5['금액'] = top5['금액'].apply(lambda x: f"{int(x):,}원")
                    st.caption("📊 지출 TOP 5 카테고리")
                    st.table(top5)
            else:
                st.info(f"{rp_period} 현금흐름 데이터가 없습니다.")

            st.divider()

            # ── 섹션 3: 이달의 독서 ──
            st.markdown("### 📚 이달의 독서")
            df_bk_rp = load_data_safe("Books")
            if not df_bk_rp.empty:
                df_bk_rp['날짜_dt'] = pd.to_datetime(df_bk_rp['날짜'], errors='coerce')
                rp_books = df_bk_rp[df_bk_rp['날짜_dt'].dt.strftime('%Y-%m') == rp_period]
                if not rp_books.empty:
                    bk1, bk2 = st.columns(2)
                    bk1.metric("이달 완독", f"{len(rp_books)}권")
                    bk2.metric("도서 지출", f"₩{int(rp_books['가격'].sum()):,}")
                    st.table(rp_books[['날짜', '제목', '저자', '분류', '별점']].reset_index(drop=True))
                else:
                    st.info(f"{rp_period}에 기록된 도서가 없습니다.")
            else:
                st.info("도서 데이터가 없습니다.")

            st.divider()

            # ── 섹션 4: 이달의 여행 ──
            st.markdown("### ✈️ 이달의 여행")
            df_exp_rp  = load_data_safe("TravelExp")
            df_dest_rp = load_data_safe("TravelDest")
            if not df_exp_rp.empty:
                df_exp_rp['date_dt'] = pd.to_datetime(df_exp_rp['date'], errors='coerce')
                rp_travel = df_exp_rp[df_exp_rp['date_dt'].dt.strftime('%Y-%m') == rp_period]
                if not rp_travel.empty:
                    tr1, tr2 = st.columns(2)
                    tr1.metric("여행 지출 합계", f"₩{int(rp_travel['amount'].sum()):,}")
                    tr2.metric("지출 건수",       f"{len(rp_travel)}건")
                    # 여행지명 매핑
                    if not df_dest_rp.empty:
                        dest_map = dict(zip(df_dest_rp['id'], df_dest_rp['name']))
                        rp_travel = rp_travel.copy()
                        rp_travel['여행지'] = rp_travel['dest_id'].map(dest_map).fillna('기타')
                        st.table(rp_travel[['date', '여행지', 'item', 'category', 'amount']].rename(columns={'date': '날짜', 'item': '항목', 'category': '분류', 'amount': '금액'}).assign(금액=lambda x: x['금액'].apply(lambda v: f"₩{int(v):,}")).reset_index(drop=True))
                else:
                    st.info(f"{rp_period}에 기록된 여행 지출이 없습니다.")
            else:
                st.info("여행 지출 데이터가 없습니다.")

            st.divider()

            # ── 섹션 5: 이달의 뉴스/아티클 ──
            st.markdown("### 📰 이달의 지식 큐레이션")
            if not df_media.empty:
                df_media['date_dt'] = pd.to_datetime(df_media['date'], errors='coerce')
                rp_media = df_media[df_media['date_dt'].dt.strftime('%Y-%m') == rp_period]
                if not rp_media.empty:
                    st.metric("저장 아티클", f"{len(rp_media)}개")
                    for _, mrow in rp_media.iloc[::-1].iterrows():
                        st.markdown(f"**{mrow['title']}** — {mrow['insight'][:80]}{'...' if len(str(mrow['insight'])) > 80 else ''} 🔗 [읽기]({mrow['url']})")
                else:
                    st.info(f"{rp_period}에 저장된 아티클이 없습니다.")
            else:
                st.info("뉴스/아티클 데이터가 없습니다.")