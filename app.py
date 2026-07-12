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
# 1. 앱 기본 설정 및 환경 변수
# ==========================================
st.set_page_config(page_title="은퇴 준비하기 v6.5.6", layout="wide")

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

def reset_quiz():
    st.session_state.pop('q_idx', None)
    st.session_state.quiz_input = ""

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

def run_withdrawal_sim(bal_isa0, bal_pension0, bal_retire0, monthly_target, annual_div_amt,
                        annual_return, inflation_rate, start_y, end_y,
                        np_start, np_amt, use_np):
    """4계좌 인출 순서 시뮬레이션 - 연금 인출 시뮬/은퇴 점검 리포트 공통 사용"""
    months = (end_y - start_y + 1) * 12
    dates = pd.date_range(start=f"{start_y}-01-01", periods=months, freq='MS')
    monthly_div = annual_div_amt / 12

    acc_isa, acc_pension, acc_retire = bal_isa0, bal_pension0, bal_retire0
    cur_target = monthly_target
    depletion_month = None
    history = []

    for idx, d in enumerate(dates):
        if d.month == 1 and idx > 0:
            cur_target *= (1 + inflation_rate)

        np_active = use_np and d >= pd.Timestamp(np_start)
        net_target = max(0, cur_target - np_amt) if np_active else cur_target
        withdraw_needed = max(0, net_target - monthly_div)

        acc_isa *= (1 + annual_return / 12)
        acc_pension *= (1 + annual_return / 12)
        acc_retire *= (1 + annual_return / 12)

        remain = withdraw_needed
        take = min(acc_isa, remain); acc_isa -= take; remain -= take
        take = min(acc_pension, remain); acc_pension -= take; remain -= take
        take = min(acc_retire, remain); acc_retire -= take; remain -= take

        total_now = acc_isa + acc_pension + acc_retire
        if total_now <= 0 and depletion_month is None:
            depletion_month = d

        history.append({'날짜': d, 'ISA': acc_isa, '연금저축군': acc_pension,
                         '퇴직연금': acc_retire, '합계': total_now, '실인출액': withdraw_needed})

    return pd.DataFrame(history), depletion_month

def get_pension_account_defaults():
    """연금자산(Data) 시트 최신 데이터로 4계좌 기본값 산출"""
    df_p = load_data_safe("Data")
    acc_defaults = {'퇴직연금': 348845206, 'IRP': 75381190, 'ISA': 95091287, '개인연금': 376318489}
    if not df_p.empty and 'date' in df_p.columns and 'account' in df_p.columns:
        df_p['date_dt'] = pd.to_datetime(df_p['date'], format='%Y-%m', errors='coerce')
        latest_dt = df_p['date_dt'].max()
        if pd.notnull(latest_dt):
            latest_rows = df_p[df_p['date_dt'] == latest_dt]
            for _, r in latest_rows.iterrows():
                if r['account'] in acc_defaults:
                    acc_defaults[r['account']] = int(r['amount'])
    return acc_defaults

# ==========================================
# 3. 사이드바 내비게이션 (v6.5.6: 3개 메뉴로 간소화)
# ==========================================

with st.sidebar:
    st.title("은퇴 준비하기 v6.5.6")
    st.caption("자산관리 · 도서관리 · 영어공부에 집중")
    st.divider()

    menu_options = ["💰 자산관리", "📚 도서관리", "🔤 영어공부"]
    menu = st.radio("이동할 메뉴 선택", menu_options, label_visibility="collapsed")

    st.divider()
    st.metric("은퇴 D-Day (KST)", f"D-{d_day}")
    st.caption(f"현재 기준일: {now_kst}")

# ==========================================
# 4. 메뉴별 비즈니스 로직
# ==========================================

# =========================================================
# [💰 자산관리] - 7개 탭으로 통합
# =========================================================
if menu == "💰 자산관리":
    st.header("💰 자산관리")

    asset_tabs = st.tabs([
        "📊 통합 현황", "💰 연금자산", "💵 개인자산",
        "📈 연금 인출 시뮬", "🧭 인출순서·세금", "🛡️ 은퇴 점검 리포트",
        "🎯 마일스톤"
    ])
    (tab_overview, tab_pension, tab_personal, tab_sim, tab_order,
     tab_check, tab_milestone) = asset_tabs

    # ⚠️ [v6.5.6 임시 비활성화] 현금흐름·리밸런싱·월간리포트 탭은 메뉴 간소화를 위해
    # UI에서 제외했습니다. 아래 코드 블록 3개(tab_cashflow, tab_rebal, tab_report)는
    # 삭제하지 않고 "# " 접두사를 붙인 주석 형태로 그대로 보존되어 있으니, 복원이 필요하면:
    #   1. 위 asset_tabs 리스트에 "💸 현금흐름", "🔄 리밸런싱", "📋 월간리포트" 추가
    #   2. 아래 unpacking 라인에 tab_cashflow, tab_rebal, tab_report 추가
    #   3. 해당 블록의 각 줄 맨 앞 "# " 접두사를 일괄 제거하면 그대로 동작합니다.

    # =====================================================
    # 탭1: 통합 현황 (구 은퇴관제탑 t_ta) - 목표달성률 + 3개월 추이
    # =====================================================
    with tab_overview:
        df_ta = load_data_safe("TotalAssets")
        if not df_ta.empty:
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

                st.subheader("🎯 은퇴 목표 달성률")
                goal_asset = st.number_input(
                    "은퇴 목표 자산 설정 (원)", value=1_500_000_000, step=100_000_000, format="%d",
                    help="목표 자산을 변경하면 달성률이 즉시 업데이트됩니다.", key="goal_asset_input"
                )
                current_grand = int(latest['grand_total'])
                achievement_pct = min((current_grand / goal_asset) * 100, 100) if goal_asset > 0 else 0
                remaining = max(goal_asset - current_grand, 0)

                ga1, ga2, ga3 = st.columns(3)
                ga1.metric("현재 통합 총자산", f"{current_grand:,}원")
                ga2.metric("목표 달성률", f"{achievement_pct:.1f}%")
                ga3.metric("남은 금액", f"{remaining:,}원")

                fig_gauge = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=achievement_pct,
                    number={'suffix': '%', 'font': {'size': 36}},
                    delta={'reference': 100, 'suffix': '%', 'valueformat': '.1f'},
                    gauge={
                        'axis': {'range': [0, 100], 'ticksuffix': '%'},
                        'bar': {'color': '#2ecc71' if achievement_pct >= 80 else '#f39c12' if achievement_pct >= 50 else '#e74c3c'},
                        'steps': [
                            {'range': [0, 50], 'color': '#fdecea'},
                            {'range': [50, 80], 'color': '#fef9e7'},
                            {'range': [80, 100], 'color': '#eafaf1'},
                        ],
                        'threshold': {'line': {'color': 'gold', 'width': 4}, 'thickness': 0.75, 'value': 100}
                    },
                    title={'text': f"목표 {goal_asset:,}원 대비 달성률", 'font': {'size': 14}}
                ))
                fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=10))
                st.plotly_chart(fig_gauge, width="stretch")

                st.divider()
                st.subheader(f"📊 {latest['date_clean']} 통합 자산 요약")
                c1, c2, c3 = st.columns(3)
                c1.metric("통합 총자산", f"{int(latest['grand_total']):,}원")
                c2.metric("연금자산", f"{int(latest['pension_total']):,}원")
                c3.metric("개인자산", f"{int(latest['personal_total']):,}원")

                st.divider()

                # ── 최근 3개월 데이터 집계 ──
                # to_period()는 Python 3.14+에서 Segfault 위험 → strftime('YYYY-MM') 문자열 키로 대체
                df_ta_valid['ym'] = df_ta_valid['date_dt'].dt.strftime('%Y-%m')
                df_monthly = (
                    df_ta_valid.sort_values('date_dt')
                    .groupby('ym', sort=True)
                    .last()
                    .reset_index()
                )
                df_plot = df_monthly.tail(3).copy()
                df_plot['display_date'] = df_plot['ym'].apply(
                    lambda s: f"{s[2:4]}년 {s[5:7]}월"
                )

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
                    # annotation y값을 grand_total로 통일
                    # (barmode=stack에서 막대 상단 = pension + personal = grand_total이어야 정상)
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
                st.plotly_chart(fig_ct, width="stretch")

                if pd.notnull(latest.get('insight', None)):
                    st.info(f"💡 이번 달 인사이트: {latest['insight']}")

                st.divider()
                with st.expander("📝 통합자산 데이터 입력/수정"):
                    with st.form("in_ta_tower"):
                        ta_d = st.date_input("데이터 기준일", now_kst)
                        ta_p = st.number_input("연금자산 합계(원)", step=1000000)
                        ta_s = st.number_input("개인자산 합계(원)", step=1000000)
                        ta_i = st.text_area("인사이트 및 메모")
                        if st.form_submit_button("통합자산 데이터 저장"):
                            new_ta = pd.DataFrame([{"date": str(ta_d), "pension_total": ta_p, "personal_total": ta_s, "grand_total": ta_p + ta_s, "insight": ta_i}])
                            conn.update(worksheet="TotalAssets", data=pd.concat([df_ta.drop(columns=['date_dt', 'display_date', 'date_clean'], errors='ignore'), new_ta], ignore_index=True))
                            st.rerun()
        else:
            st.info("자산 데이터를 입력해 주세요.")
            with st.expander("📝 통합자산 데이터 입력"):
                df_ta_empty = load_data_safe("TotalAssets")
                with st.form("in_ta_tower_empty"):
                    ta_d = st.date_input("데이터 기준일", now_kst)
                    ta_p = st.number_input("연금자산 합계(원)", step=1000000)
                    ta_s = st.number_input("개인자산 합계(원)", step=1000000)
                    ta_i = st.text_area("인사이트 및 메모")
                    if st.form_submit_button("통합자산 데이터 저장"):
                        new_ta = pd.DataFrame([{"date": str(ta_d), "pension_total": ta_p, "personal_total": ta_s, "grand_total": ta_p + ta_s, "insight": ta_i}])
                        conn.update(worksheet="TotalAssets", data=pd.concat([df_ta_empty, new_ta], ignore_index=True))
                        st.rerun()

    # =====================================================
    # 탭2: 연금자산 (구 메뉴 그대로)
    # =====================================================
    with tab_pension:
        df_p = load_data_safe("Data")
        sub1, sub2 = st.tabs(["📊 대시보드", "📝 입력"])

        with sub1:
            if not df_p.empty and 'date' in df_p.columns:
                df_p['date_dt'] = pd.to_datetime(df_p['date'], format='%Y-%m', errors='coerce')
                df_p_valid = df_p.dropna(subset=['date_dt']).copy()
                dates_sorted_dt = sorted(df_p_valid['date_dt'].unique())

                if dates_sorted_dt:
                    ACCOUNT_COLORS = {'퇴직연금': '#1f77b4', 'IRP': '#ff7f0e', 'ISA': '#2ca02c', '개인연금': '#d62728'}
                    accounts_all = sorted(df_p_valid['account'].unique())

                    # 전체 월별 계좌별 집계 - pivot_table+reindex 대신 안전한 groupby 방식 사용
                    # (pivot_table+reindex 조합이 pandas 3.x + Python 3.14에서 Segfault 위험)
                    df_p_valid['ym_str'] = df_p_valid['date_dt'].dt.strftime('%Y-%m')
                    grp = df_p_valid.groupby(['ym_str', 'account'])['amount'].sum().reset_index()

                    # 전체 월 목록 (정렬)
                    all_ym = sorted(grp['ym_str'].unique())

                    # 월 × 계좌 딕셔너리로 구성 (reindex 없이 직접 구성)
                    pivot_dict = {acc: [] for acc in accounts_all}
                    total_list = []
                    for ym in all_ym:
                        month_data = grp[grp['ym_str'] == ym]
                        row_total = 0
                        for acc in accounts_all:
                            val = month_data.loc[month_data['account'] == acc, 'amount']
                            v = float(val.iloc[0]) if len(val) > 0 else 0.0
                            pivot_dict[acc].append(v)
                            row_total += v
                        total_list.append(row_total)

                    # 날짜 인덱스: ym_str → datetime (그래프 x축용)
                    dt_index = pd.to_datetime([f"{ym}-01" for ym in all_ym])

                    latest_dt = dt_index[-1]
                    cur_total = total_list[-1]
                    prev_total = total_list[-2] if len(total_list) > 1 else cur_total
                    mom_diff = cur_total - prev_total

                    # 연초 대비 YTD 계산
                    cur_year = latest_dt.year
                    ytd_base = cur_total
                    for i, dt in enumerate(dt_index):
                        if dt.year == cur_year:
                            ytd_base = total_list[i]
                            break
                    ytd_diff = cur_total - ytd_base
                    ytd_pct = (ytd_diff / ytd_base * 100) if ytd_base != 0 else 0

                    first_total = total_list[0]
                    total_growth_diff = cur_total - first_total
                    total_growth_pct = (total_growth_diff / first_total * 100) if first_total != 0 else 0

                    # ── ① 핵심 지표 카드 4개 ──
                    st.markdown("##### 📌 핵심 지표")
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric(f"{latest_dt.strftime('%y년 %m월')} 합계", f"{int(cur_total):,}원")
                    k2.metric("전월 대비", f"{(mom_diff/prev_total*100) if prev_total!=0 else 0:+.1f}%", f"{int(mom_diff):+,}원")
                    k3.metric(f"{cur_year}년 누적 증가", f"{ytd_pct:+.1f}%", f"{int(ytd_diff):+,}원")
                    k4.metric("최초 기록 대비 총증가", f"{total_growth_pct:+.1f}%", f"{int(total_growth_diff):+,}원")

                    st.divider()

                    # ── ② 전체 기간 추이 (누적 영역그래프) ──
                    st.markdown("##### 📈 전체 기간 자산 추이")
                    fig_full = go.Figure()
                    for acc in accounts_all:
                        vals = pivot_dict[acc]
                        fig_full.add_trace(go.Scatter(
                            x=dt_index, y=vals, name=acc,
                            stackgroup='one', mode='lines',
                            line=dict(width=0.5, color=ACCOUNT_COLORS.get(acc, '#888888')),
                            hovertemplate=f'{acc}: ' + '%{customdata}백만원<extra></extra>',
                            customdata=[round(v/1e6) for v in vals]
                        ))
                    fig_full.add_trace(go.Scatter(
                        x=dt_index, y=total_list, name='합계',
                        mode='lines', line=dict(color='gold', width=3, dash='dot'),
                        hovertemplate='합계: %{customdata}억원<extra></extra>',
                        customdata=[round(v/1e8, 2) for v in total_list]
                    ))

                    max_full = max(total_list) * 1.2 if total_list else 1e9
                    tick_step_full = 5e8 if max_full > 20e8 else 2e8 if max_full > 10e8 else 1e8
                    tick_vals_full = list(range(0, int(max_full) + int(tick_step_full), int(tick_step_full)))
                    tick_texts_full = [f"{int(v/1e8)}억" for v in tick_vals_full]

                    x_tick_vals = list(dt_index)
                    x_tick_texts = [d.strftime('%y년 %m월') for d in x_tick_vals]
                    if len(x_tick_vals) > 12:
                        step = max(1, len(x_tick_vals) // 12)
                        x_tick_vals = x_tick_vals[::step]
                        x_tick_texts = x_tick_texts[::step]

                    x_min, x_max = dt_index[0], dt_index[-1]
                    x_span = x_max - x_min
                    x_pad = x_span * 0.04 if x_span.days > 0 else pd.Timedelta(days=15)

                    fig_full.update_layout(
                        height=400,
                        xaxis=dict(
                            tickmode='array', tickvals=x_tick_vals, ticktext=x_tick_texts,
                            range=[x_min - x_pad, x_max + x_pad], automargin=True
                        ),
                        yaxis=dict(tickvals=tick_vals_full, ticktext=tick_texts_full),
                        margin=dict(l=20, r=20, t=20, b=20),
                        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                    )
                    st.plotly_chart(fig_full, width="stretch")

                    st.divider()

                    # ── ③ 계좌별 비중 도넛 + 기간선택 막대 ──
                    st.markdown("##### 🥧 계좌별 비중 · 기간별 비교")
                    dc1, dc2 = st.columns([1, 2])

                    with dc1:
                        latest_vals = [pivot_dict[acc][-1] for acc in accounts_all]
                        fig_donut = px.pie(
                            values=latest_vals, names=accounts_all, hole=0.5,
                            color=accounts_all, color_discrete_map=ACCOUNT_COLORS,
                            title=f"{latest_dt.strftime('%y년 %m월')} 비중"
                        )
                        fig_donut.update_traces(textinfo='label+percent')
                        fig_donut.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
                        st.plotly_chart(fig_donut, width="stretch")

                    with dc2:
                        period_choice = st.radio(
                            "조회 기간", ["3개월", "6개월", "12개월", "전체"],
                            horizontal=True, index=1, key="pension_period_choice"
                        )
                        n_map = {"3개월": 3, "6개월": 6, "12개월": 12, "전체": len(all_ym)}
                        n_sel = min(n_map[period_choice], len(all_ym))
                        sel_labels = [d.strftime('%y년 %m월') for d in dt_index[-n_sel:]]
                        sel_totals = total_list[-n_sel:]

                        fig_period = go.Figure()
                        for acc in accounts_all:
                            sel_vals = pivot_dict[acc][-n_sel:]
                            hover_texts = [f"{acc}: {int(round(v/1e6))}백만원" for v in sel_vals]
                            fig_period.add_trace(go.Bar(
                                x=sel_labels, y=sel_vals, name=acc,
                                marker_color=ACCOUNT_COLORS.get(acc, '#888888'),
                                hovertext=hover_texts, hoverinfo='text'
                            ))

                        max_p = max(sel_totals) * 1.3 if sel_totals else 1e9
                        tick_step_p = 1e8
                        tick_vals_p = list(range(0, int(max_p) + int(tick_step_p), int(tick_step_p)))
                        tick_texts_p = [f"{int(v/1e8)}억" for v in tick_vals_p]

                        for label, total_val in zip(sel_labels, sel_totals):
                            fig_period.add_annotation(
                                x=label, y=total_val, text=f"<b>{int(total_val):,}원</b>",
                                showarrow=False, yshift=12, font=dict(size=10, color="#333333"),
                                bgcolor="rgba(255,255,255,0.85)", borderpad=2,
                                xanchor='center', yanchor='bottom'
                            )

                        fig_period.update_layout(
                            barmode='stack', height=380,
                            xaxis=dict(type='category'),
                            yaxis=dict(tickvals=tick_vals_p, ticktext=tick_texts_p, range=[0, max_p]),
                            margin=dict(l=10, r=10, t=20, b=20),
                            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
                        )
                        st.plotly_chart(fig_period, width="stretch")

                    st.divider()

                    # ── ④ 월별 변동 테이블 (펼쳐보기) ──
                    with st.expander("📋 월별 변동 상세 테이블 보기"):
                        table_rows = []
                        for i, ym in enumerate(reversed(all_ym)):
                            idx = len(all_ym) - 1 - i
                            row = {'날짜': f"{ym[:4]}년 {ym[5:7]}월"}
                            for acc in accounts_all:
                                row[acc] = f"{int(pivot_dict[acc][idx]):,}원"
                            row['합계'] = f"{int(total_list[idx]):,}원"
                            if idx > 0:
                                diff = total_list[idx] - total_list[idx-1]
                                row['전월대비'] = f"{int(diff):+,}원"
                            else:
                                row['전월대비'] = "-"
                            table_rows.append(row)
                        st.dataframe(pd.DataFrame(table_rows), width="stretch")
            else:
                st.info("연금자산 데이터를 입력해 주세요.")

        with sub2:
            c1, c2 = st.columns(2)
            py = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
            pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1, key="p_m")
            p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'], key="p_acc_sel")
            p_amt = st.number_input("금액(원)", step=100000, key="p_amt_input")

            if st.button("연금 데이터 저장", key="p_save_btn"):
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

    # =====================================================
    # 탭3: 개인자산 (구 메뉴 그대로)
    # =====================================================
    with tab_personal:
        df_per = load_data_safe("PersonalData")
        sub1, sub2 = st.tabs(["📊 대시보드", "📝 입력"])

        with sub1:
            if not df_per.empty and 'date' in df_per.columns:
                weeks = sorted([str(d) for d in df_per['date'].unique()])
                if weeks:
                    recent = weeks[-3:]
                    df_r = df_per[df_per['date'].isin(recent)]
                    w_total = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                    cur = w_total.iloc[-1]
                    prev = w_total.iloc[-2] if len(w_total) > 1 else cur
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

                    max_y_per = w_total.max() * 1.3 if w_total.max() > 0 else 1e8
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
                    st.plotly_chart(fig, width="stretch")

        with sub2:
            st.subheader("📝 개인자산 입력")
            c1, c2, c3 = st.columns(3)
            pery = c1.selectbox("연도", [2026, 2027, 2028], key="per_y_sel")
            perm = c2.selectbox("월", [f"{i}월" for i in range(1, 13)], index=now_kst.month - 1, key="per_m_sel")
            perm_int = int(perm.replace("월", ""))

            week_options = get_month_weeks(pery, perm_int)
            if not week_options:
                week_options = [(f"{str(pery)[2:]}년 {perm_int}월 1주", f"Y{pery}W{datetime.date(pery, perm_int, 1).isocalendar()[1]}")]

            week_labels = [w[0] for w in week_options]
            week_keys = [w[1] for w in week_options]
            current_week_key = f"Y{now_kst.year}W{now_kst.isocalendar()[1]}"
            default_idx = 0
            for i, wk in enumerate(week_keys):
                if wk == current_week_key:
                    default_idx = i
                    break

            sel_week_label = c3.selectbox("주차 선택", week_labels, index=default_idx, key="per_w_sel")
            sel_week_key = week_keys[week_labels.index(sel_week_label)]

            p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '토스증권'], key="p_acc_per_sel")
            per_amt = st.number_input("현재 잔액(원)", step=10000, key="per_amt_input")
            st.caption(f"📌 선택된 주차 키: `{sel_week_key}` → 대시보드에 **{sel_week_label}** 로 표시됩니다.")

            if st.button("개인자산 정보 저장", key="per_save_btn"):
                df = load_data_safe("PersonalData")
                mask = (df['date'] == sel_week_key) & (df['account'] == p_acc_per)
                if mask.any():
                    df.loc[mask, 'amount'] = int(per_amt)
                else:
                    df = pd.concat([df, pd.DataFrame([{"date": sel_week_key, "account": p_acc_per, "amount": int(per_amt), "memo": ""}])], ignore_index=True)
                conn.update(worksheet="PersonalData", data=df)
                st.toast("저장 완료!")
                st.rerun()

    # =====================================================
    # 탭4: 연금 인출 시뮬 (계좌별 분리 + 연 분배율 입력)
    # =====================================================
    with tab_sim:
        st.caption("4개 계좌(퇴직연금/개인연금/IRP/ISA) 잔액을 기준으로 인출 순서에 따라 자산이 어떻게 줄어드는지 시뮬레이션합니다.")
        acc_defaults = get_pension_account_defaults()

        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("⚙️ 계좌별 잔액 설정")
            st.caption("연금자산 탭의 최신 데이터가 기본값으로 채워집니다. 여기서 수정하면 다른 탭에도 동일하게 반영됩니다.")

            bal_retire = st.number_input("퇴직연금 잔액(원)", value=acc_defaults['퇴직연금'], step=1000000, key="bal_retire")
            bal_personal = st.number_input("개인연금 잔액(원)", value=acc_defaults['개인연금'], step=1000000, key="bal_personal")
            bal_irp = st.number_input("IRP 잔액(원)", value=acc_defaults['IRP'], step=1000000, key="bal_irp")
            bal_isa = st.number_input("ISA 잔액(원)", value=acc_defaults['ISA'], step=1000000, key="bal_isa")

            total_base = bal_retire + bal_personal + bal_irp + bal_isa
            st.metric("기초 자산 합계", f"{total_base:,}원 ({total_base/1e8:.2f}억)")

            st.divider()
            st.subheader("💰 인출/수익 조건")
            monthly_withdraw_manwon = st.slider(
                "월 희망 수령액 (만원, 국민연금 포함 전 총액)", 300, 1000, 500, 10, key="monthly_withdraw_manwon"
            )
            monthly_withdraw_total = monthly_withdraw_manwon * 10000
            dividend_pct_raw = st.slider(
                "연 분배금/배당 수익률 (전체 연금성 자산 대비 %)", 0.0, 5.0, 0.0, 0.5, key="dividend_pct_raw",
                help="연금성 자산 합계의 일정 %를 연간 분배금으로 가정합니다. 예: 2% 선택 시 8.96억의 2% = 약 1,792만원/년"
            )
            dividend_pct = dividend_pct_raw / 100
            annual_return_raw = st.slider("기대 연 수익률 (시세차익, %)", 0.0, 10.0, 3.0, 0.5, key="annual_return_raw")
            annual_return = annual_return_raw / 100
            inflation_rate_raw = st.slider("예상 물가 상승률 (%)", 0.0, 5.0, 2.0, 0.5, key="inflation_rate_raw")
            inflation_rate = inflation_rate_raw / 100

            st.session_state['_final_monthly_withdraw_total'] = monthly_withdraw_total
            st.session_state['_final_dividend_pct'] = dividend_pct
            st.session_state['_final_annual_return'] = annual_return
            st.session_state['_final_inflation_rate'] = inflation_rate

            annual_dividend_amt = total_base * dividend_pct
            st.caption(f"📌 연 분배금 예상액: **{annual_dividend_amt:,.0f}원** (월 평균 {annual_dividend_amt/12:,.0f}원)")

            st.divider()
            st.subheader("📅 기간 & 국민연금")
            start_y = st.selectbox("시뮬레이션 시작 연도", range(2029, 2040), index=0, key="start_y")
            end_y = st.selectbox("시뮬레이션 종료 연도", range(start_y + 1, 2075), index=25, key="end_y")
            national_pension_start = st.date_input("국민연금 수령 시작일", datetime.date(2038, 8, 1), key="national_pension_start")
            national_pension_amt = st.number_input("국민연금 월 수령액(원)", value=1500000, step=100000, key="national_pension_amt")
            use_national = st.checkbox("국민연금 수령 시점부터 인출액에서 자동 차감", value=True, key="use_national")

        with c2:
            sim_df, depletion_month = run_withdrawal_sim(
                bal_isa, bal_personal + bal_irp, bal_retire,
                monthly_withdraw_total, annual_dividend_amt,
                annual_return, inflation_rate, start_y, end_y,
                national_pension_start, national_pension_amt, use_national
            )

            max_asset = sim_df['합계'].max() if not sim_df.empty else 1e9
            tick_step_eok = 5e8 if max_asset > 20e8 else 2e8 if max_asset > 10e8 else 1e8
            tick_vals_sim = list(range(0, int(max_asset * 1.15) + int(tick_step_eok), int(tick_step_eok)))
            tick_texts_sim = [f"{int(v / 1e8)}억" for v in tick_vals_sim]

            fig_sim = go.Figure()
            fig_sim.add_trace(go.Scatter(
                x=sim_df['날짜'], y=sim_df['퇴직연금'], name='퇴직연금', mode='lines',
                stackgroup='one', line=dict(width=0.5, color='#1f77b4'),
                hovertemplate='퇴직연금: %{customdata}억원<extra></extra>',
                customdata=[round(v / 1e8, 2) for v in sim_df['퇴직연금']]
            ))
            fig_sim.add_trace(go.Scatter(
                x=sim_df['날짜'], y=sim_df['연금저축군'], name='개인연금+IRP', mode='lines',
                stackgroup='one', line=dict(width=0.5, color='#ff7f0e'),
                hovertemplate='개인연금+IRP: %{customdata}억원<extra></extra>',
                customdata=[round(v / 1e8, 2) for v in sim_df['연금저축군']]
            ))
            fig_sim.add_trace(go.Scatter(
                x=sim_df['날짜'], y=sim_df['ISA'], name='ISA', mode='lines',
                stackgroup='one', line=dict(width=0.5, color='#2ca02c'),
                hovertemplate='ISA: %{customdata}억원<extra></extra>',
                customdata=[round(v / 1e8, 2) for v in sim_df['ISA']]
            ))

            if use_national:
                fig_sim.add_vline(
                    x=pd.Timestamp(national_pension_start).timestamp() * 1000,
                    line_dash="dash", line_color="gray",
                    annotation_text="국민연금 시작", annotation_position="top"
                )

            fig_sim.update_layout(
                title=f"월 {int(monthly_withdraw_total/10000)}만원 인출 시 계좌별 자산 추이",
                xaxis=dict(tickformat="%y년"),
                yaxis=dict(tickvals=tick_vals_sim, ticktext=tick_texts_sim, title="자산 잔액"),
                height=480, margin=dict(l=20, r=20, t=50, b=20),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
            )
            st.plotly_chart(fig_sim, width="stretch")

            m1, m2, m3 = st.columns(3)
            if depletion_month is not None:
                years_lasted = (depletion_month.year - start_y) + (depletion_month.month - 1) / 12
                m1.metric("자산 소진 예상", depletion_month.strftime('%Y년 %m월'), f"약 {years_lasted:.1f}년 지속")
            else:
                m1.metric("자산 소진 예상", "소진 안 됨 ✅", f"{end_y}년까지 자산 유지")

            gap_years = (national_pension_start.year - start_y) + max(0, (national_pension_start.month - 1)) / 12
            m2.metric("국민연금 공백기", f"{gap_years:.1f}년", f"{start_y}년 ~ {national_pension_start.year}.{national_pension_start.month:02d}")

            final_balance = sim_df['합계'].iloc[-1] if not sim_df.empty else 0
            m3.metric(f"{end_y}년 말 잔액", f"{final_balance/1e8:.2f}억원")

    # =====================================================
    # 탭5: 인출순서·세금 가이드 (탭4 session_state 값 그대로 사용)
    # =====================================================
    with tab_order:
        st.subheader("🧭 내 자산 기준 인출 순서 시뮬레이션")
        st.caption("[연금 인출 시뮬] 탭에서 입력한 계좌별 잔액을 실시간으로 반영합니다.")

        acc_defaults_o = get_pension_account_defaults()
        isa_bal = st.session_state.get('bal_isa', acc_defaults_o['ISA'])
        pension_bal = st.session_state.get('bal_personal', acc_defaults_o['개인연금']) + st.session_state.get('bal_irp', acc_defaults_o['IRP'])
        retire_bal = st.session_state.get('bal_retire', acc_defaults_o['퇴직연금'])

        st.divider()
        order_steps = [
            ("1단계", "ISA 자금", isa_bal, "비과세", "만기 시 수익 200만원까지 비과세, 초과분 9.9% 분리과세. 가장 먼저 사용해 세부담 최소화"),
            ("2단계", "개인연금/IRP 원금", pension_bal, "비과세", "본인이 납입한 원금(세액공제 받지 않은 추가납입분)은 인출 시 비과세"),
            ("3단계", "퇴직연금(퇴직금)", retire_bal, "퇴직소득세 30%↓", "연금으로 10년 이상 수령 시 퇴직소득세 30~40% 감면 혜택"),
            ("4단계", "개인연금/IRP 수익+세액공제분", 0, "연금소득세 3.3~5.5%", "마지막에 수령. 연 1,500만원 한도 초과 시 종합과세 전환 주의"),
        ]

        for step, name, amt, tax, desc in order_steps:
            with st.expander(f"{step} · {name} — {amt/1e8:.2f}억원 ({tax})", expanded=(step == "1단계")):
                st.write(desc)

        st.divider()
        st.subheader("💰 연 1,500만원 한도 체크")
        annual_limit = 15000000
        default_test = int(st.session_state.get('_final_monthly_withdraw_total', 5000000) / 10000)
        test_monthly = st.slider("월 사적연금 인출액 테스트(만원)", 100, 800, min(max(default_test, 100), 800), 10, key="test_monthly_order") * 10000
        annual_withdraw = test_monthly * 12
        ratio = annual_withdraw / annual_limit * 100

        lc1, lc2 = st.columns(2)
        lc1.metric("연간 인출 예상액", f"{annual_withdraw:,}원")
        lc2.metric("한도 대비 비율", f"{ratio:.0f}%", "초과 시 종합과세 ⚠️" if ratio > 100 else "한도 내 ✅")

        if ratio > 100:
            st.warning(f"⚠️ 연 1,500만원 한도를 {ratio-100:.0f}% 초과합니다. 종합과세 대상이 되어 세부담이 커질 수 있으니 인출 시점을 분산하거나 ISA·퇴직연금 비중을 늘리는 것을 검토하세요.")
        else:
            st.success(f"✅ 한도의 {ratio:.0f}% 수준으로, 저율의 연금소득세(3.3~5.5%) 범위 내에서 수령 가능합니다.")

        st.divider()
        st.subheader("🏛️ 건강보험료 참고사항")
        st.info("현재(2026년 기준) 사적연금 수령액은 건강보험 피부양자 자격 산정 소득에서 제외됩니다. 다만 제도 개편 가능성이 있어 매년 보건복지부 발표를 확인하는 것이 안전합니다.")

    # =====================================================
    # 탭6: 은퇴 점검 리포트 (탭4 session_state 값 그대로 사용)
    # =====================================================
    with tab_check:
        st.subheader("🛡️ 내 데이터 기반 자동 진단")
        st.caption("[연금 인출 시뮬] 탭에서 입력한 계좌 잔액·인출 조건을 실시간으로 반영합니다.")

        acc_defaults_c = get_pension_account_defaults()
        r_isa = st.session_state.get('bal_isa', acc_defaults_c['ISA'])
        r_personal = st.session_state.get('bal_personal', acc_defaults_c['개인연금'])
        r_irp = st.session_state.get('bal_irp', acc_defaults_c['IRP'])
        r_retire = st.session_state.get('bal_retire', acc_defaults_c['퇴직연금'])
        total3 = r_isa + r_personal + r_irp + r_retire

        r_monthly_target = st.session_state.get('_final_monthly_withdraw_total', 5000000)
        r_div_pct = st.session_state.get('_final_dividend_pct', 0.0)
        r_annual_return = st.session_state.get('_final_annual_return', 0.03)
        r_inflation = st.session_state.get('_final_inflation_rate', 0.02)
        r_start_y = st.session_state.get('start_y', 2029)
        r_end_y = st.session_state.get('end_y', 2054)
        r_np_start = st.session_state.get('national_pension_start', datetime.date(2038, 8, 1))
        r_np_amt = st.session_state.get('national_pension_amt', 1500000)
        r_use_np = st.session_state.get('use_national', True)

        st.caption(f"현재 반영된 총자산: **{total3:,}원 ({total3/1e8:.2f}억원)** · 목표 인출액: 월 {r_monthly_target/10000:,.0f}만원")

        st.markdown("### 📐 4% 안전 인출률 진단")
        annual_withdraw_target = r_monthly_target * 12
        safe_withdraw_amt = total3 * 0.04
        withdraw_ratio = (annual_withdraw_target / total3 * 100) if total3 > 0 else 0

        r1, r2, r3 = st.columns(3)
        r1.metric("현재 총자산", f"{total3/1e8:.2f}억원")
        r2.metric("4% 룰 권장 연 인출액", f"{safe_withdraw_amt/1e4:,.0f}만원")
        r3.metric(f"희망 인출률(연 {annual_withdraw_target/1e8:.2f}억)", f"{withdraw_ratio:.1f}%",
                  "4% 이내 ✅" if withdraw_ratio <= 4.0 else "4% 초과 ⚠️")

        if withdraw_ratio <= 4.0:
            st.success(f"✅ 월 {r_monthly_target/10000:,.0f}만원(연 {annual_withdraw_target/1e4:,.0f}만원) 인출은 현재 자산 기준 {withdraw_ratio:.1f}%로, 4% 룰 안전 범위 내에 있습니다.")
        else:
            st.warning(f"⚠️ 월 {r_monthly_target/10000:,.0f}만원 인출 시 {withdraw_ratio:.1f}%로 4% 룰을 초과합니다. 국민연금 수령 전까지는 자산 소진 속도가 빠를 수 있어 분배금 확보나 인출액 조정을 고려하세요.")

        st.divider()
        st.markdown("### ⏳ 국민연금 공백기 대응 진단")
        gap_start = datetime.date(r_start_y, 1, 1)
        gap_end = r_np_start - timedelta(days=1)
        gap_months = max(0, (gap_end.year - gap_start.year) * 12 + (gap_end.month - gap_start.month) + 1)
        gap_total_needed = r_monthly_target * gap_months

        g1, g2 = st.columns(2)
        g1.metric("공백기 기간", f"{gap_months}개월 (약 {gap_months/12:.1f}년)",
                  f"{gap_start.strftime('%Y.%m')} ~ {gap_end.strftime('%Y.%m')}")
        g2.metric("공백기 총 필요액(수익 미반영)", f"{gap_total_needed/1e8:.2f}억원")

        coverage_ratio = (total3 / gap_total_needed * 100) if gap_total_needed > 0 else 100
        if coverage_ratio >= 100:
            st.success(f"✅ 현재 자산({total3/1e8:.2f}억)만으로도 공백기 전체를 수익률 반영 없이 커버할 수 있는 수준({coverage_ratio:.0f}%)입니다. 실제로는 운용수익이 더해지므로 여유가 있습니다.")
        else:
            st.info(f"💡 현재 자산은 공백기 필요액의 {coverage_ratio:.0f}% 수준입니다. 운용수익과 분배금을 더하면 충당 가능하니 [연금 인출 시뮬] 탭에서 정확한 소진 시점을 확인하세요.")

        r_annual_div_amt = total3 * r_div_pct
        _, r_depletion = run_withdrawal_sim(
            r_isa, r_personal + r_irp, r_retire, r_monthly_target, r_annual_div_amt,
            r_annual_return, r_inflation, r_start_y, r_end_y, r_np_start, r_np_amt, r_use_np
        )
        if r_depletion is not None:
            st.caption(f"📊 [연금 인출 시뮬] 탭 조건(수익률 {r_annual_return*100:.1f}%, 물가 {r_inflation*100:.1f}%, 분배율 {r_div_pct*100:.1f}%) 적용 시 실제 소진 예상: **{r_depletion.strftime('%Y년 %m월')}**")
        else:
            st.caption(f"📊 [연금 인출 시뮬] 탭 조건 적용 시 {r_end_y}년까지 자산이 소진되지 않습니다.")

        st.divider()
        st.markdown("### 🧯 현금성 자산 버퍼 점검")
        st.caption("시장 급락기에 위험자산을 팔지 않고도 버틸 수 있는 현금성 자산(예금·MMF·금리액티브 ETF 등) 규모를 점검합니다.")

        buf_mode = st.radio(
            "현금 버퍼 산정 방식",
            ["개월수로 계산 (예: 24개월)", "직접 금액 입력", "전체 자산 대비 비중(%) 추천"],
            horizontal=True, key="buf_mode"
        )

        if buf_mode == "개월수로 계산 (예: 24개월)":
            buf_months = st.slider("권장 버퍼 기간(개월)", 6, 36, 24, 6, key="buf_months_input")
            buffer_needed = r_monthly_target * buf_months
            buffer_desc = f"{buf_months}개월치 생활비"
        elif buf_mode == "직접 금액 입력":
            buffer_needed = st.number_input(
                "권장 현금 버퍼 직접 입력(원)", value=120000000, step=10000000, key="buf_amount_input"
            )
            buffer_desc = "직접 입력한 금액"
        else:
            buf_pct = st.slider("전체 자산 대비 현금성 자산 추천 비중(%)", 5, 30, 10, 1, key="buf_pct_input")
            buffer_needed = total3 * (buf_pct / 100)
            buffer_desc = f"전체 자산의 {buf_pct}%"

        bc1, bc2, bc3 = st.columns(3)
        bc1.metric("권장 현금 버퍼", f"{buffer_needed/1e8:.2f}억원", buffer_desc)

        months_covered_isa = (r_isa / r_monthly_target) if r_monthly_target > 0 else 0
        bc2.metric("ISA 잔액으로 충당 가능 기간", f"{months_covered_isa:.1f}개월")

        buffer_gap = buffer_needed - r_isa
        if buffer_gap > 0:
            bc3.metric("ISA 대비 부족분", f"{buffer_gap/1e8:.2f}억원", "추가 확보 필요", delta_color="inverse")
        else:
            bc3.metric("ISA 대비 부족분", "충분 ✅", f"{abs(buffer_gap)/1e8:.2f}억원 여유")

        if r_isa >= buffer_needed:
            st.success(f"✅ ISA 잔액({r_isa/1e8:.2f}억)이 권장 현금 버퍼({buffer_needed/1e8:.2f}억) 이상이라 시장 급락기에도 위험자산을 매도하지 않고 버틸 수 있습니다.")
        else:
            st.info(f"💡 ISA만으로는 권장 버퍼({buffer_needed/1e8:.2f}억) 대비 {buffer_gap/1e8:.2f}억원이 부족합니다. 금리액티브 ETF, MMF, 예금 등 현금성 자산을 추가로 일부 배분하는 것을 검토해보세요. 시장이 일시적으로 폭락할 때 위험자산을 매도해 인출하면 자산 회복이 불가능해질 수 있습니다.")

    # =====================================================
    # 탭7: 현금흐름 (구 메뉴 그대로)
    # ⚠️ v6.5.6: UI 간소화를 위해 임시 비활성화 (코드는 보존, 삭제 아님)
    # 복원 방법: 아래 "# " 로 시작하는 줄들의 "# " 접두사만 일괄 제거하면 즉시 동작
    # =====================================================
    # with tab_cashflow:
        # df_cf = load_data_safe("CashFlow")
        # df_bg = load_data_safe("Budgets")

        # CF_CATEGORIES = ["급여", "기타수익", "자기계발", "문화생활", "저축/투자", "쇼핑", "외식", "생활비", "마트",
                         # "통신비, 구독료", "교통비", "보험", "여행", "명절, 이벤트", "용돈", "기타"]

        # c_f1, c_f2 = st.columns(2)
        # sel_y = c_f1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1, key="cf_sel_y")
        # sel_m = c_f2.selectbox("조회 월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1, key="cf_sel_m")
        # sel_period = f"{sel_y}-{sel_m}"

        # cf1_t, cf2_t, cf3_t, cf4_t, cf5_t = st.tabs(["🚦 소비 신호등", "📝 내역 기록", "📊 지출 패턴 분석", "✏️ 내역 수정/삭제", "⚙️ 예산 설정"])

        # with cf1_t:
            # total_spent = 0
            # if not df_cf.empty:
                # df_cf['date_dt'] = pd.to_datetime(df_cf['date'], errors='coerce')
                # m_exp = df_cf[(df_cf['type'] == 'EXPENSE') & (df_cf['date_dt'].dt.strftime("%Y-%m") == sel_period)]
                # total_spent = m_exp['amount'].sum()

            # current_budget = df_bg[df_bg['period'] == sel_period]['budget_amount'].iloc[0] if not df_bg.empty and not df_bg[df_bg['period'] == sel_period].empty else 0

            # if current_budget == 0:
                # st.info(f"📢 {sel_period}의 예산이 설정되지 않았습니다.")
            # else:
                # percent = (total_spent / current_budget) * 100
                # c1, c2, c3 = st.columns(3)
                # c1.metric("소비 상태", f"{percent:.1f}%", f"{int(current_budget - total_spent):,}원 남음")

        # with cf2_t:
            # with st.form("cf_form_v3", clear_on_submit=True):
                # c1, c2 = st.columns(2)
                # f_date = c1.date_input("날짜", now_kst)
                # f_type = c1.selectbox("구분", ["EXPENSE", "INCOME"])
                # f_cat = c2.selectbox("카테고리", CF_CATEGORIES)
                # f_amt = c2.number_input("금액", min_value=0, step=1000)
                # f_memo = st.text_input("메모")
                # f_rec = st.checkbox("정기 지출/수입 여부")
                # if st.form_submit_button("현금흐름 기록 저장"):
                    # new_data = pd.DataFrame([{"date": str(f_date), "type": f_type, "category": f_cat, "amount": f_amt, "memo": f_memo, "is_recurring": str(f_rec).upper()}])
                    # conn.update(worksheet="CashFlow", data=pd.concat([df_cf.drop(columns=['date_dt'], errors='ignore'), new_data], ignore_index=True))
                    # st.success("내역이 저장되었습니다!")
                    # st.rerun()

        # with cf3_t:
            # if not df_cf.empty:
                # m_exp_only = df_cf[(df_cf['type'] == 'EXPENSE') & (pd.to_datetime(df_cf['date']).dt.strftime("%Y-%m") == sel_period)]
                # if not m_exp_only.empty:
                    # fig = px.pie(m_exp_only, values='amount', names='category', hole=0.4)
                    # st.plotly_chart(fig, width="stretch")
                    # st.dataframe(m_exp_only[['date', 'category', 'amount', 'memo']].sort_values('date', ascending=False), width="stretch")

        # with cf4_t:
            # if not df_cf.empty:
                # m_data = df_cf[pd.to_datetime(df_cf['date'], errors='coerce').dt.strftime("%Y-%m") == sel_period].copy()
                # if not m_data.empty:
                    # m_data = m_data.sort_values('date', ascending=False)
                    # edit_list = m_data.apply(
                        # lambda x: f"[{x['date']}] {x['category']} - {x['memo']} ({int(x['amount']):,}원)", axis=1
                    # ).tolist()
                    # sel_item = st.selectbox("수정/삭제할 항목 선택 (최신순)", options=edit_list)
                    # sel_idx = m_data.index[edit_list.index(sel_item)]

                    # with st.form("edit_cf_full"):
                        # ec1, ec2 = st.columns(2)
                        # e_date = ec1.date_input("날짜 수정", value=pd.to_datetime(df_cf.loc[sel_idx, 'date']).date())
                        # e_type = ec1.selectbox("구분 수정", ["EXPENSE", "INCOME"], index=0 if df_cf.loc[sel_idx, 'type'] == "EXPENSE" else 1)
                        # e_cat = ec2.selectbox("카테고리 수정", CF_CATEGORIES, index=CF_CATEGORIES.index(df_cf.loc[sel_idx, 'category']) if df_cf.loc[sel_idx, 'category'] in CF_CATEGORIES else 0)
                        # e_amt = ec2.number_input("금액 수정", value=int(df_cf.loc[sel_idx, 'amount']))
                        # e_memo = st.text_input("메모 수정", value=str(df_cf.loc[sel_idx, 'memo']))
                        # b1, b2 = st.columns(2)
                        # if b1.form_submit_button("💾 수정 완료"):
                            # df_cf.at[sel_idx, 'date'] = str(e_date)
                            # df_cf.at[sel_idx, 'type'] = e_type
                            # df_cf.at[sel_idx, 'category'] = e_cat
                            # df_cf.at[sel_idx, 'amount'] = e_amt
                            # df_cf.at[sel_idx, 'memo'] = e_memo
                            # conn.update(worksheet="CashFlow", data=df_cf.drop(columns=['date_dt'], errors='ignore'))
                            # st.rerun()
                        # if b2.form_submit_button("🗑️ 삭제 완료"):
                            # conn.update(worksheet="CashFlow", data=df_cf.drop(sel_idx).drop(columns=['date_dt'], errors='ignore'))
                            # st.rerun()

        # with cf5_t:
            # with st.form("budget_setting"):
                # new_bg = st.number_input("해당 월 목표 예산", value=int(current_budget), step=100000)
                # if st.form_submit_button("예산 저장"):
                    # if not df_bg.empty and (df_bg['period'] == sel_period).any():
                        # df_bg.loc[df_bg['period'] == sel_period, 'budget_amount'] = new_bg
                    # else:
                        # df_bg = pd.concat([df_bg, pd.DataFrame([{"category": "전체", "budget_amount": new_bg, "period": sel_period}])], ignore_index=True)
                    # conn.update(worksheet="Budgets", data=df_bg)
                    # st.rerun()

    # # =====================================================
    # # 탭8: 리밸런싱 (구 전략모드 → 탭으로 흡수)
    # # =====================================================
    # with tab_rebal:
        # df_reb = load_data_safe("Rebalancing")
        # st.info("💡26년(70:30) → 27년(60:40) → 28년(50:50), 29년 이후 배당 ETF, 마켓금리액티브 매수")

        # with st.form("reb_in_form_v2"):
            # c1, c2 = st.columns(2)
            # r_date = c1.date_input("리밸런싱 실행 날짜", now_kst)
            # r_strat = c1.text_input("현재 전략 비중 (예: 70:30)")
            # r_action = c2.text_area("실행 내역 (매수/매도 상세)")
            # r_reason = st.text_area("리밸런싱 판단 근거")
            # r_target = c2.text_input("조정 후 목표 비중")
            # if st.form_submit_button("리밸런싱 내역 저장"):
                # new_reb = pd.DataFrame([{"date": str(r_date), "strategy": r_strat, "action": r_action, "reason": r_reason, "target_ratio": r_target}])
                # conn.update(worksheet="Rebalancing", data=pd.concat([df_reb, new_reb], ignore_index=True))
                # st.rerun()

        # if not df_reb.empty:
            # st.divider()
            # for i, row in df_reb.iloc[::-1].iterrows():
                # with st.expander(f"📅 {row['date']} 리밸런싱 실행 기록"):
                    # st.write(f"**전략 비중:** {row['strategy']} → **목표 비중:** {row['target_ratio']}")
                    # st.write(f"**상세 액션:** {row['action']}")
                    # st.caption(f"**판단 근거:** {row['reason']}")
                    # if st.button("내역 삭제", key=f"reb_del_btn_{i}"):
                        # conn.update(worksheet="Rebalancing", data=df_reb.drop(i))
                        # st.rerun()

    # # =====================================================
    # # 탭9: 월간리포트 (여행/뉴스 섹션 제거 - 자산/현금흐름/독서만)
    # # =====================================================
    # with tab_report:
        # st.caption("자산·현금흐름·독서를 한 페이지로 자동 집계합니다.")

        # rp_c1, rp_c2 = st.columns(2)
        # rp_year = rp_c1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1, key="rp_year")
        # rp_month = rp_c2.selectbox("조회 월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month - 1, key="rp_month")
        # rp_period = f"{rp_year}-{rp_month}"

        # st.divider()

        # st.markdown("### 💰 자산 현황")
        # df_ta_rp = load_data_safe("TotalAssets")
        # if not df_ta_rp.empty:
            # df_ta_rp['date_clean'] = df_ta_rp['date'].astype(str).str.strip().str.lower()
            # df_ta_rp['date_dt'] = pd.to_datetime(df_ta_rp['date_clean'], errors='coerce')
            # df_ta_rp_valid = df_ta_rp.dropna(subset=['date_dt']).sort_values('date_dt')
            # rp_month_data = df_ta_rp_valid[df_ta_rp_valid['date_dt'].dt.strftime('%Y-%m') == rp_period]
            # prev_month_dt = (datetime.date(rp_year, int(rp_month), 1) - timedelta(days=1))
            # prev_period = prev_month_dt.strftime('%Y-%m')
            # rp_prev_data = df_ta_rp_valid[df_ta_rp_valid['date_dt'].dt.strftime('%Y-%m') == prev_period]

            # if not rp_month_data.empty:
                # cur_row = rp_month_data.iloc[-1]
                # prev_row = rp_prev_data.iloc[-1] if not rp_prev_data.empty else None
                # a1, a2, a3 = st.columns(3)
                # a1.metric("통합 총자산", f"{int(cur_row['grand_total']):,}원",
                          # f"{int(cur_row['grand_total'] - prev_row['grand_total']):+,}원" if prev_row is not None else None)
                # a2.metric("연금자산", f"{int(cur_row['pension_total']):,}원",
                          # f"{int(cur_row['pension_total'] - prev_row['pension_total']):+,}원" if prev_row is not None else None)
                # a3.metric("개인자산", f"{int(cur_row['personal_total']):,}원",
                          # f"{int(cur_row['personal_total'] - prev_row['personal_total']):+,}원" if prev_row is not None else None)
                # if pd.notnull(cur_row.get('insight', None)):
                    # st.info(f"💡 {rp_period} 인사이트: {cur_row['insight']}")
            # else:
                # st.info(f"{rp_period} 자산 데이터가 없습니다.")
        # else:
            # st.info("자산 데이터가 없습니다.")

        # st.divider()

        # st.markdown("### 💸 현금흐름 요약")
        # df_cf_rp = load_data_safe("CashFlow")
        # if not df_cf_rp.empty:
            # df_cf_rp['date_dt'] = pd.to_datetime(df_cf_rp['date'], errors='coerce')
            # rp_cf = df_cf_rp[df_cf_rp['date_dt'].dt.strftime('%Y-%m') == rp_period]
            # rp_income = rp_cf[rp_cf['type'] == 'INCOME']['amount'].sum()
            # rp_expense = rp_cf[rp_cf['type'] == 'EXPENSE']['amount'].sum()
            # rp_net = rp_income - rp_expense
            # rp_save_rate = (rp_net / rp_income * 100) if rp_income > 0 else 0
            # cf1, cf2, cf3, cf4 = st.columns(4)
            # cf1.metric("총 수입", f"{int(rp_income):,}원")
            # cf2.metric("총 지출", f"{int(rp_expense):,}원")
            # cf3.metric("순 수지", f"{int(rp_net):,}원")
            # cf4.metric("저축률", f"{rp_save_rate:.1f}%")
            # if not rp_cf[rp_cf['type'] == 'EXPENSE'].empty:
                # top5 = rp_cf[rp_cf['type'] == 'EXPENSE'].groupby('category')['amount'].sum().sort_values(ascending=False).head(5).reset_index()
                # top5.columns = ['카테고리', '금액']
                # top5['금액'] = top5['금액'].apply(lambda x: f"{int(x):,}원")
                # st.caption("📊 지출 TOP 5 카테고리")
                # st.table(top5)
        # else:
            # st.info(f"{rp_period} 현금흐름 데이터가 없습니다.")

        # st.divider()

        # st.markdown("### 📚 이달의 독서")
        # df_bk_rp = load_data_safe("Books")
        # if not df_bk_rp.empty:
            # df_bk_rp['날짜_dt'] = pd.to_datetime(df_bk_rp['날짜'], errors='coerce')
            # rp_books = df_bk_rp[df_bk_rp['날짜_dt'].dt.strftime('%Y-%m') == rp_period]
            # if not rp_books.empty:
                # bk1, bk2 = st.columns(2)
                # bk1.metric("이달 완독", f"{len(rp_books)}권")
                # bk2.metric("도서 지출", f"₩{int(rp_books['가격'].sum()):,}")
                # st.table(rp_books[['날짜', '제목', '저자', '분류', '별점']].reset_index(drop=True))
            # else:
                # st.info(f"{rp_period}에 기록된 도서가 없습니다.")
        # else:
            # st.info("도서 데이터가 없습니다.")

    # =====================================================
    # 탭10(원래 번호 유지): 마일스톤 (구 은퇴관제탑 t_ms, t_in 일부 흡수)
    # =====================================================
    with tab_milestone:
        df_ms = load_data_safe("Milestones")
        st.caption("은퇴까지 해야 할 일들을 카테고리별로 관리합니다.")

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
            st.info("아래에서 마일스톤을 추가해 주세요.")

        st.divider()
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

# =========================================================
# [📚 도서관리] - 기존 메뉴 그대로 유지
# =========================================================
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

    tab1, tab2, tab3, tab4 = st.tabs(["📖 나의 서재", "🎯 독서 목표 & 페이스", "➕ 신규 도서 등록", "✏️ 도서 정보 수정/삭제"])

    with tab1:
        if not df_books.empty:
            st.table(df_books.iloc[::-1][['날짜', '제목', '저자', '가격', '구입처', '분류']].head(15))

    with tab2:
        st.subheader("🎯 독서 목표 달성 현황")

        if not df_books.empty:
            goal_year = st.selectbox("연도 선택", [2026, 2027, 2028], key="goal_year_sel")
            goal_books = st.number_input("연간 목표 권수", min_value=1, max_value=100, value=24, step=1, key="goal_books_input")

            df_books['날짜_dt'] = pd.to_datetime(df_books['날짜'], errors='coerce')
            year_df = df_books[df_books['날짜_dt'].dt.year == goal_year].copy()
            read_count = len(year_df)

            achieve_pct = min((read_count / goal_books) * 100, 100) if goal_books > 0 else 0
            remaining_books = max(goal_books - read_count, 0)

            year_start = datetime.date(goal_year, 1, 1)
            year_end = datetime.date(goal_year, 12, 31)
            today = now_kst
            days_passed = max((min(today, year_end) - year_start).days + 1, 1)
            days_total = (year_end - year_start).days + 1
            days_remaining = max((year_end - today).days, 0)

            expected_total = int(read_count / days_passed * days_total) if days_passed > 0 else 0
            pace_needed = f"{remaining_books / (days_remaining / 30):.1f}권/월" if days_remaining > 0 else "목표 달성!"

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("올해 완독", f"{read_count}권", f"목표 {goal_books}권")
            m2.metric("달성률", f"{achieve_pct:.0f}%")
            m3.metric("연말 예상", f"{expected_total}권", f"{'초과 👍' if expected_total >= goal_books else '부족 📚'}")
            m4.metric("남은 목표 페이스", pace_needed)

            fig_book_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=achieve_pct,
                number={'suffix': '%', 'font': {'size': 32}},
                gauge={
                    'axis': {'range': [0, 100], 'ticksuffix': '%'},
                    'bar': {'color': '#2ecc71' if achieve_pct >= 80 else '#f39c12' if achieve_pct >= 50 else '#3498db'},
                    'steps': [
                        {'range': [0, 50], 'color': '#eaf4fb'},
                        {'range': [50, 80], 'color': '#fef9e7'},
                        {'range': [80, 100], 'color': '#eafaf1'},
                    ],
                    'threshold': {'line': {'color': 'gold', 'width': 4}, 'thickness': 0.75, 'value': 100}
                },
                title={'text': f"{goal_year}년 독서 목표 달성률 ({read_count}/{goal_books}권)", 'font': {'size': 14}}
            ))
            fig_book_gauge.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
            st.plotly_chart(fig_book_gauge, width="stretch")

            if not year_df.empty:
                st.divider()
                st.subheader("📅 월별 독서 현황")
                year_df['월'] = year_df['날짜_dt'].dt.month
                monthly_counts = year_df.groupby('월').size().reset_index(name='권수')
                all_months = pd.DataFrame({'월': range(1, 13)})
                monthly_counts = all_months.merge(monthly_counts, on='월', how='left').fillna(0)
                monthly_counts['권수'] = monthly_counts['권수'].astype(int)
                monthly_counts['월명'] = monthly_counts['월'].apply(lambda m: f"{m}월")

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
                st.plotly_chart(fig_monthly, width="stretch")

                st.divider()
                st.subheader("📊 장르별 독서 분포")
                genre_counts = year_df['분류'].value_counts().reset_index()
                genre_counts.columns = ['분류', '권수']
                fig_genre = px.pie(genre_counts, values='권수', names='분류', hole=0.4,
                                   title=f"{goal_year}년 장르 분포")
                fig_genre.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_genre, width="stretch")
        else:
            st.info("도서를 먼저 등록해주세요.")

    with tab3:
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
                else:
                    st.warning("제목을 입력해주세요.")

    with tab4:
        if not df_books.empty:
            df_books_sorted = df_books.copy()
            df_books_sorted['날짜_dt'] = pd.to_datetime(df_books_sorted['날짜'], errors='coerce')
            df_books_sorted = df_books_sorted.sort_values('날짜_dt', ascending=False)
            edit_list = df_books_sorted.apply(lambda x: f"{x['날짜']} | {x['제목']} ({x['저자']})", axis=1).tolist()
            sel_b = st.selectbox("수정할 책 선택 (최신순)", options=edit_list)
            b_idx = df_books_sorted.index[edit_list.index(sel_b)]
            with st.form("edit_book_full"):
                ec1, ec2 = st.columns(2)
                e_t = ec1.text_input("제목 수정", value=df_books.loc[b_idx, '제목'])
                e_a = ec1.text_input("저자 수정", value=df_books.loc[b_idx, '저자'])
                e_p = ec1.number_input("가격 수정", value=int(df_books.loc[b_idx, '가격']))
                e_s = ec1.text_input("구입처 수정", value=str(df_books.loc[b_idx, '구입처']))
                cat_list = ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"]
                cur_cat = df_books.loc[b_idx, '분류']
                cat_idx = cat_list.index(cur_cat) if cur_cat in cat_list else 0
                e_cat = ec2.selectbox("분류 수정", cat_list, index=cat_idx)
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

# =========================================================
# [🔤 영어공부] - 기존 메뉴 그대로 유지
# =========================================================
elif menu == "🔤 영어공부":
    st.header("🔤 영어 공부")
    df_en = load_data_safe("Sheet1")
    t1, t2, t3, t4 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "✏️ 문장 수정/삭제", "🧠 퀴즈"])

    with t1:
        if not df_en.empty:
            ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], width="stretch", key="en_ed")
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
            sf1, sf2 = st.columns(2)
            search_kw = sf1.text_input("🔍 영어/한글 키워드 검색", placeholder="예: give up, 포기하다")
            search_date = sf2.text_input("📅 날짜 검색", placeholder="예: 2026-05-07")

            df_en_sorted = df_en.copy()
            df_en_sorted['date_dt'] = pd.to_datetime(df_en_sorted['date'], errors='coerce')
            df_en_sorted = df_en_sorted.sort_values('date_dt', ascending=False)

            if search_kw.strip():
                kw = search_kw.strip().lower()
                df_en_sorted = df_en_sorted[
                    df_en_sorted['english'].astype(str).str.lower().str.contains(kw, na=False) |
                    df_en_sorted['korean'].astype(str).str.lower().str.contains(kw, na=False)
                ]
            if search_date.strip():
                df_en_sorted = df_en_sorted[
                    df_en_sorted['date'].astype(str).str.contains(search_date.strip(), na=False)
                ]

            st.caption(f"검색 결과: {len(df_en_sorted)}개 문장")

            if not df_en_sorted.empty:
                edit_list = df_en_sorted.apply(
                    lambda x: f"[{x['date']}] {x['english']}", axis=1
                ).tolist()
                sel_en = st.selectbox("수정/삭제할 문장 선택 (최신순)", options=edit_list)
                en_idx = df_en_sorted.index[edit_list.index(sel_en)]

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
            else:
                st.info("검색 조건에 맞는 문장이 없습니다.")

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



