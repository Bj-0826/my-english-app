import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
from datetime import timedelta, timezone  # KST 보정을 위해 추가
import plotly.graph_objects as go
import os
import plotly.express as px
import requests
import numpy as np
from io import StringIO

# 1. 앱 설정
st.set_page_config(page_title="은퇴 준비하기 v6.0.8", layout="wide")

# 2. 한국 표준시(KST) 설정 및 은퇴 D-Day 계산
# 서버 시간에 관계없이 항상 한국 표준시로 오늘 날짜를 가져옵니다.
KST = timezone(timedelta(hours=9))
now_kst = datetime.datetime.now(KST).date()
ret_date = datetime.date(2028, 12, 31)
d_day = (ret_date - now_kst).days

# 3. 구글 시트 고유 ID (인증된 서비스 계정 사용)
SHEET_ID = "1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA"

# --- [데이터 로드 함수: 400/404 에러 방지용 직접 호출 로직] ---
def load_data_safe(s_name):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={s_name}"
        response = requests.get(url)
        response.encoding = 'utf-8'
        if response.status_code != 200: return pd.DataFrame()
        
        df = pd.read_csv(StringIO(response.text))
        if df.empty: return pd.DataFrame()
        
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        
        if 'date' in df.columns: 
            df['date'] = df['date'].astype(str).str.strip().str.upper()
        
        # 금액 데이터 처리 (연금, 개인자산, 현금흐름, 도서, 여행 공통)
        amount_cols = ['amount', '가격']
        for col in amount_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        if s_name == "Sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
        return df
    except:
        return pd.DataFrame()

# 저장용 커넥션 선언 (Secrets의 서비스 계정 키 참조)
conn = st.connection("gsheets", type=GSheetsConnection)

# 환율 정보 함수
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

# --- [사이드바 메뉴: 통합 및 전환 이슈 해결] ---
with st.sidebar:
    st.title("은퇴 준비하기 v6.0.8")
    
    # 1) 메뉴 전환 이슈 해결을 위해 모든 옵션을 하나의 라디오 버튼으로 통합합니다.
    st.subheader("📋 전체 메뉴")
    menu_options = [
        "💰 연금자산", "📈 연금시뮬", "💸 현금흐름", "💵 개인자산",
        "🔤 영어공부", "📚 도서관리", "✈️ 여행관리", "📓 다이어리", "📰 뉴스저장"
    ]
    menu = st.radio("이동할 메뉴 선택", menu_options, label_visibility="collapsed")
    
    st.divider()
    # 2) 은퇴 D-Day (KST 적용)
    st.metric("은퇴 D-Day (KST)", f"D-{d_day}")
    st.caption(f"현재 기준일: {now_kst}")

# --- [1. 연금자산] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_p.empty and 'date' in df_p.columns:
            dates_sorted = sorted(df_p['date'].unique(), key=lambda x: pd.to_datetime(x, format='%Y-%m', errors='coerce'))
            if dates_sorted:
                recent = dates_sorted[-3:]; df_r = df_p[df_p['date'].isin(recent)]
                m_total = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                cur = m_total.iloc[-1]; prev = m_total.iloc[-2] if len(m_total)>1 else cur
                diff = cur - prev
                c1, c2 = st.columns(2)
                c1.metric(f"{recent[-1]} 합계", f"{int(cur):,}원")
                c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
                fig = go.Figure()
                for acc in sorted(df_r['account'].unique()):
                    acc_df = df_r[df_r['account'] == acc].set_index('date').reindex(recent).fillna(0).reset_index()
                    fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc))
                fig.update_layout(barmode='stack', height=400); st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=now_kst.month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        p_amt = st.number_input("금액(원)", step=100000)
        if st.button("저장"):
            df = load_data_safe("Data")
            t_date = f"{py}-{pm}"; mask = (df['date'] == t_date) & (df['account'] == p_acc)
            if mask.any(): df.loc[mask, 'amount'] = int(p_amt)
            else: df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc, "amount": int(p_amt), "memo": ""}])], ignore_index=True)
            conn.update(worksheet="Data", data=df); st.toast("저장 완료!"); st.rerun()

# --- [2. 연금시뮬] ---
elif menu == "📈 연금시뮬":
    st.header("📈 은퇴 후 연금 마스터 시뮬레이터")
    df_p = load_data_safe("Data")
    current_total = 0
    if not df_p.empty:
        latest_date = sorted(df_p['date'].unique(), key=lambda x: pd.to_datetime(x, format='%Y-%m', errors='coerce'))[-1]
        current_total = df_p[df_p['date'] == latest_date]['amount'].sum()
    tab1, tab2, tab3 = st.tabs(["📉 자산 예측 시뮬레이션", "🏛️ 국민연금 & 세금 가이드", "💡 기획자 제언"])
    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("⚙️ 조건 설정")
            base_asset = st.number_input("기초 자산 (현재연금+퇴직금)", value=int(current_total + 350000000), step=10000000)
            monthly_withdraw = st.slider("월 희망 수령액 (만 원)", 300, 1000, 600) * 10000
            annual_return = st.slider("기대 연 수익률 (%)", 0.0, 10.0, 4.0, 0.5) / 100
            inflation_rate = st.slider("예상 물가 상승률 (%)", 0.0, 5.0, 2.0, 0.5) / 100
            start_y = st.selectbox("시뮬레이션 시작 연도", range(2029, 2040), index=0)
            end_y = st.selectbox("시뮬레이션 종료 연도", range(start_y+1, 2070), index=21)
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
            st.plotly_chart(px.area(sim_df, x="날짜", y="잔액", title="자산 추이 예측"), use_container_width=True)
    with tab2:
        st.subheader("📚 연금 수령 전략 사전")
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("""
            #### 1. 인출 순서 (Tax-Smart)
            * **ISA 자금**: 가장 먼저 사용 (비과세)
            * **연금저축/IRP (추가납입분)**: 원금은 비과세 인출 가능
            * **퇴직연금 (퇴직금)**: 퇴직소득세 30% 감면 혜택
            * **연금저축/IRP (공제분+수익)**: 마지막에 수령 (연금소득세 3.3~5.5%)
            """)
        with col_b:
            st.markdown("""
            #### 2. 세금 주의사항
            * **연 1,500만원 한도**: 사적연금 수령액이 넘으면 종합과세 대상. (퇴직금 원금은 이 한도에 포함 안 됨!)
            * **건보료**: 현재 사적연금은 건보료 산정 제외이나, 향후 개편 가능성 모니터링 필요.
            """)
    with tab3:
        st.subheader("💡 Byungjoo님을 위한 기획자 제언")
        st.info("""
        **1. 4% 법칙 (Safe Withdrawal Rate)**: 전체 자산의 4% 이내로 매년 인출하면 자산이 마르지 않을 확률이 매우 높습니다. 현재 Byungjoo님의 자산 규모에서는 월 600~700만원 수준이 골디락스 존(Goldilocks Zone)입니다.
        
        **2. 현금성 자산 2년치 보유**: 시장이 폭락할 때 연금을 인출하면 자산 회복이 불가능해집니다. 하락장을 버틸 2년치 생활비는 항상 예금/채권으로 별도 관리하세요.
        """)

# --- [3. 현금흐름] ---
elif menu == "💸 현금흐름":
    st.header("💸 현금흐름 관리 (은퇴 준비)")
    df_cf = load_data_safe("CashFlow"); df_bg = load_data_safe("Budgets")
    CF_CATEGORIES = ["급여", "배당금", "고정지출", "변동지출", "자기계발", "저축/투자", "쇼핑", "외식", "생활비", 
                     "통신비, 구독료", "교통비", "보험료", "여행", "명절, 이벤트", "용돈", "기타"]
    
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
            f_date = c1.date_input("날짜", now_kst); f_type = c1.selectbox("구분", ["EXPENSE", "INCOME"])
            f_cat = c2.selectbox("카테고리", CF_CATEGORIES); f_amt = c2.number_input("금액", min_value=0, step=1000)
            f_memo = st.text_input("메모"); f_rec = st.checkbox("정기 지출/수입 여부")
            if st.form_submit_button("기록 저장"):
                new_data = pd.DataFrame([{"date": str(f_date), "type": f_type, "category": f_cat, "amount": f_amt, "memo": f_memo, "is_recurring": str(f_rec).upper()}])
                conn.update(worksheet="CashFlow", data=pd.concat([df_cf.drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf, new_data], ignore_index=True)); st.success("저장되었습니다!"); st.rerun()
    with t3:
        if not df_cf.empty:
            m_exp_only = df_cf[(df_cf['type'] == 'EXPENSE') & (pd.to_datetime(df_cf['date']).dt.strftime("%Y-%m") == sel_period)]
            if not m_exp_only.empty:
                fig = px.pie(m_exp_only, values='amount', names='category', hole=0.4); st.plotly_chart(fig, use_container_width=True)
                st.dataframe(m_exp_only[['date', 'category', 'amount', 'memo']].sort_values('date', ascending=False), use_container_width=True)
    with t4:
        if not df_cf.empty:
            m_data = df_cf[pd.to_datetime(df_cf['date'], errors='coerce').dt.strftime("%Y-%m") == sel_period]
            if not m_data.empty:
                edit_list = m_data.apply(lambda x: f"[{x['date']}] {x['category']} - {x['memo']} ({int(x['amount']):,}원)", axis=1).tolist()
                sel_item = st.selectbox("항목 선택", options=edit_list); sel_idx = m_data.index[edit_list.index(sel_item)]
                with st.form("edit_cf_v3"):
                    e_date = st.date_input("날짜", value=pd.to_datetime(df_cf.loc[sel_idx, 'date']).date()); e_amt = st.number_input("금액", value=int(df_cf.loc[sel_idx, 'amount']))
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("💾 수정"):
                        df_cf.at[sel_idx, 'amount'] = e_amt; df_cf.at[sel_idx, 'date'] = str(e_date); conn.update(worksheet="CashFlow", data=df_cf.drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf); st.rerun()
                    if b2.form_submit_button("🗑️ 삭제"):
                        conn.update(worksheet="CashFlow", data=df_cf.drop(sel_idx).drop(columns=['date_dt'], errors='ignore') if 'date_dt' in df_cf.columns else df_cf); st.rerun()
    with t5:
        with st.form("budget_form"):
            new_bg = st.number_input("목표 예산", value=int(current_budget), step=100000)
            if st.form_submit_button("예산 저장"):
                if not df_bg.empty and (df_bg['period'] == sel_period).any(): df_bg.loc[df_bg['period'] == sel_period, 'budget_amount'] = new_bg
                else: df_bg = pd.concat([df_bg, pd.DataFrame([{"category": "전체", "budget_amount": new_bg, "period": sel_period}])], ignore_index=True)
                conn.update(worksheet="Budgets", data=df_bg); st.rerun()

# --- [4. 개인자산] ---
elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_per.empty and 'date' in df_per.columns:
            def get_w(k):
                try:
                    y = int(str(k)[1:5]); w = int(str(k).split('W')[1]); d = datetime.date(y, 1, 1) + datetime.timedelta(weeks=w-1)
                    return f"{d.month}월 {((d.day-1)//7)+1}주 (W{w})"
                except: return str(k)
            weeks = sorted([str(d) for d in df_per['date'].unique()])
            if weeks:
                recent = weeks[-3:]; df_r = df_per[df_per['date'].isin(recent)]
                w_total = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                cur = w_total.iloc[-1]; prev = w_total.iloc[-2] if len(w_total) > 1 else cur
                diff = cur - prev
                c1, c2 = st.columns(2)
                c1.metric(f"{get_w(recent[-1])} 합계", f"{int(cur):,}원"); c2.metric("전주 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
                fig = go.Figure()
                for acc in sorted(df_r['account'].unique()):
                    acc_df = df_r[df_r['account'] == acc].set_index('date').reindex(recent).fillna(0).reset_index()
                    fig.add_trace(go.Bar(x=[get_w(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
                fig.update_layout(barmode='stack', height=400); st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2026, 2027, 2028]); perw = c2.number_input("주차", 1, 53, 14)
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타']); per_amt = st.number_input("금액(원)", step=10000)
        if st.button("저장"):
            df = load_data_safe("PersonalData")
            t_date = f"Y{pery}W{perw}"; mask = (df['date'] == t_date) & (df['account'] == p_acc_per)
            if mask.any(): df.loc[mask, 'amount'] = int(per_amt)
            else: df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc_per, "amount": int(per_amt), "memo": ""}])], ignore_index=True)
            conn.update(worksheet="PersonalData", data=df); st.toast("저장 완료!"); st.rerun()

# --- [5. 영어공부] ---
elif menu == "🔤 영어공부":
    st.header("🔤 영어 공부")
    df_en = load_data_safe("Sheet1")
    t1, t2, t3, t4 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "✏️ 문장 수정/삭제", "🧠 퀴즈"])
    with t1:
        if not df_en.empty:
            ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True, key="en_ed")
            if st.button("암기 상태 저장"):
                save_df = df_en.copy(); save_df.update(ed); conn.update(worksheet="Sheet1", data=save_df); st.toast("✅ 저장 완료!"); st.rerun()
    with t2:
        with st.form("en_in_form", clear_on_submit=True):
            new_en = st.text_input("영어 문장"); new_ko = st.text_input("한글 뜻")
            if st.form_submit_button("문장 저장"):
                new_row = pd.DataFrame([{"date": str(now_kst), "english": new_en, "korean": new_ko, "memorized": False}])
                conn.update(worksheet="Sheet1", data=pd.concat([df_en, new_row], ignore_index=True)); st.rerun()
    with t3:
        if not df_en.empty:
            edit_list = df_en.apply(lambda x: f"[{x['date']}] {x['english']}", axis=1).tolist(); sel_en = st.selectbox("수정할 문장", options=edit_list); en_idx = df_en.index[edit_list.index(sel_en)]
            with st.form("edit_en"):
                e_en = st.text_input("영어", value=str(df_en.loc[en_idx, 'english'])); e_ko = st.text_input("한글", value=str(df_en.loc[en_idx, 'korean']))
                if st.form_submit_button("💾 수정"):
                    df_en.at[en_idx, 'english'] = e_en; df_en.at[en_idx, 'korean'] = e_ko; conn.update(worksheet="Sheet1", data=df_en); st.rerun()
                if st.form_submit_button("🗑️ 삭제"):
                    conn.update(worksheet="Sheet1", data=df_en.drop(en_idx)); st.rerun()
    with t4:
        unmem = df_en[df_en['memorized'] == False] if not df_en.empty else pd.DataFrame()
        if not unmem.empty:
            if 'q_idx' not in st.session_state: st.session_state.q_idx = unmem.sample(n=1).index[0]
            q = unmem.loc[st.session_state.q_idx]; st.info(f"뜻: {q['korean']}")
            ans = st.text_input("영어로 입력", key="quiz_input")
            if st.button("정답 확인"):
                if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                else: st.error(f"오답! 정답: {q['english']}")
            st.button("다음 문제", on_click=reset_quiz)

# --- [6. 도서관리: 전 필드 수정 보강] ---
elif menu == "📚 도서관리":
    st.header("📚 도서 관리 시스템 (Cloud)")
    df_books = load_data_safe("Books")
    
    if not df_books.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        sel_y_book = c1.selectbox("조회 연도", options=["2026년", "2027년", "2028년"])
        y_int = int(sel_y_book.replace("년", ""))
        y_df = df_books[pd.to_datetime(df_books['날짜'], errors='coerce').dt.year == y_int]
        c2.metric(f"{y_int}년 독서량", f"{len(y_df)} 권")
        c3.metric(f"{y_int}년 도서 구입비", f"₩{int(y_df['가격'].sum()):,}")
    
    st.divider()
    tab1, tab2, tab3 = st.tabs(["📖 서재 보기", "➕ 신규 등록", "✏️ 수정/삭제"])
    with tab1:
        if not df_books.empty:
            st.table(df_books.iloc[::-1][['날짜', '제목', '저자', '가격', '구입처', '분류']].head(15))
    with tab2:
        with st.form("book_reg_cloud", clear_on_submit=True):
            tc1, tc2 = st.columns(2)
            t = tc1.text_input("제목 (필수)"); a = tc1.text_input("저자"); p = tc1.number_input("가격", step=1000); s = tc1.text_input("구입처")
            d = tc2.date_input("구입일", now_kst); cat = tc2.selectbox("분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "에세이", "역사", "기타"])
            r = tc2.slider("별점", 1, 5, 5); cmt = st.text_area("코멘트")
            if st.form_submit_button("도서 등록") and t:
                new_book = pd.DataFrame([{'날짜': str(d), '제목': t, '저자': a, '가격': int(p), '구입처': s, '분류': cat, '별점': int(r), '코멘트': cmt, '연도': d.year}])
                conn.update(worksheet="Books", data=pd.concat([df_books, new_book], ignore_index=True)); st.rerun()
    with tab3:
        if not df_books.empty:
            edit_list = df_books.apply(lambda x: f"{x['제목']} ({x['저자']})", axis=1).tolist()
            sel_b = st.selectbox("책 선택", options=edit_list); b_idx = df_books.index[edit_list.index(sel_b)]
            with st.form("edit_book_full"):
                ec1, ec2 = st.columns(2)
                e_t = ec1.text_input("제목", value=df_books.loc[b_idx, '제목'])
                e_a = ec1.text_input("저자", value=df_books.loc[b_idx, '저자'])
                e_p = ec1.number_input("가격", value=int(df_books.loc[b_idx, '가격']))
                e_s = ec1.text_input("구입처", value=str(df_books.loc[b_idx, '구입처']))
                e_cat = ec2.selectbox("분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "기타"])
                e_r = ec2.slider("별점", 1, 5, int(df_books.loc[b_idx, '별점']))
                e_cmt = st.text_area("코멘트", value=str(df_books.loc[b_idx, '코멘트']))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 수정 저장"):
                    df_books.loc[b_idx, ['제목', '저자', '가격', '구입처', '분류', '별점', '코멘트']] = [e_t, e_a, e_p, e_s, e_cat, e_r, e_cmt]
                    conn.update(worksheet="Books", data=df_books); st.rerun()
                if c2.form_submit_button("🗑️ 삭제"):
                    conn.update(worksheet="Books", data=df_books.drop(b_idx)); st.rerun()

# --- [7. 여행관리: 일자별 요약 복구 및 수정 보강] ---
elif menu == "✈️ 여행관리":
    st.header("✈️ Byungjoo 여행기록 (Cloud)")
    df_dest = load_data_safe("TravelDest"); df_exp = load_data_safe("TravelExp")
    
    t_home, t_ledger, t_timeline, t_stats, t_edit = st.tabs(["🗺️ 여행지 관리", "💰 비용 리스트", "🗓️ 타임라인", "📊 지출 요약", "⚙️ 수정/삭제"])
    with t_home:
        with st.form("new_dest_cloud", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 2, 1]); new_name = c1.text_input("여행지명"); new_start = c2.date_input("시작일", now_kst); new_end = c2.date_input("종료일", now_kst + timedelta(days=3)); new_status = c3.selectbox("상태", ["준비", "여행중", "완료"])
            if st.form_submit_button("여행지 추가") and new_name:
                new_id = int(df_dest['id'].max() + 1) if not df_dest.empty else 1
                new_row = pd.DataFrame([{'id': new_id, 'name': new_name, 'start_date': str(new_start), 'end_date': str(new_end), 'status': new_status}])
                conn.update(worksheet="TravelDest", data=pd.concat([df_dest, new_row], ignore_index=True)); st.rerun()
    
    if not df_dest.empty:
        sel_city = st.sidebar.selectbox("📍 여행지 선택", options=df_dest['name'].tolist())
        curr = df_dest[df_dest['name'] == sel_city].iloc[0]
        d_exp = df_exp[df_exp['dest_id'] == curr['id']].copy() if not df_exp.empty else pd.DataFrame()
        
        with t_ledger:
            st.metric(f"'{sel_city}' 총 지출", f"₩{int(d_exp['amount'].sum()):,}" if not d_exp.empty else "₩0")
            with st.expander("➕ 비용 등록"):
                with st.form("t_add_cloud"):
                    c1, c2 = st.columns(2); d = c1.date_input("날짜", now_kst); it = c2.text_input("항목"); pl = c2.text_input("장소")
                    cat = st.selectbox("카테고리", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"]); amt = c2.number_input("금액", min_value=0)
                    if st.form_submit_button("저장"):
                        new_e = pd.DataFrame([{'dest_id': curr['id'], 'date': str(d), 'time': '12:00', 'item': it, 'place': pl, 'category': cat, 'method': '현금', 'amount': int(amt), 'unit': 'KRW', 'memo': ''}])
                        conn.update(worksheet="TravelExp", data=pd.concat([df_exp, new_e], ignore_index=True)); st.rerun()
        with t_timeline:
            if not d_exp.empty:
                for _, row in d_exp.sort_values('date').iterrows():
                    st.write(f"**{row['date']}** | {row['item']} @ {row['place']} (₩{int(row['amount']):,})")
        with t_stats:
            if not d_exp.empty:
                st.subheader("📅 일자별 지출 요약") # Byungjoo님, 요청하신 일자별 요약 복구
                daily_sum = d_exp.groupby('date')['amount'].sum().reset_index()
                st.table(daily_sum.assign(amount=lambda x: x['amount'].map('{:,}원'.format)))
                st.subheader("📁 카테고리별 지출")
                st.write(d_exp.groupby('category')['amount'].sum().map(lambda x: f"₩{int(x):,}"))
        with t_edit:
            if not d_exp.empty:
                edit_list = d_exp.apply(lambda x: f"[{x['date']}] {x['item']} ({int(x['amount']):,}원)", axis=1).tolist()
                sel_l = st.selectbox("항목 선택", options=edit_list); t_idx = d_exp.index[edit_list.index(sel_l)]
                with st.form("edit_t_exp"): # 수정 기능 보강
                    e_it = st.text_input("항목명", value=d_exp.loc[t_idx, 'item'])
                    e_pl = st.text_input("장소", value=d_exp.loc[t_idx, 'place'])
                    e_amt = st.number_input("금액", value=int(d_exp.loc[t_idx, 'amount']))
                    c1, c2 = st.columns(2)
                    if c1.form_submit_button("💾 수정 저장"):
                        df_exp.loc[t_idx, ['item', 'place', 'amount']] = [e_it, e_pl, e_amt]
                        conn.update(worksheet="TravelExp", data=df_exp); st.rerun()
                    if c2.form_submit_button("🗑️ 삭제"):
                        conn.update(worksheet="TravelExp", data=df_exp.drop(t_idx)); st.rerun()

# --- [8. 다이어리: 저장/확인 탭 분리 및 수정 기능] ---
elif menu == "📓 다이어리":
    st.header("📓 Byungjoo's 다이어리 & 아이디어")
    df_diary = load_data_safe("Diary")
    dt1, dt2 = st.tabs(["📝 신규 저장", "📖 기록 확인 및 수정"])
    with dt1:
        with st.form("diary_in", clear_on_submit=True):
            d_title = st.text_input("제목")
            d_tags = st.multiselect("태그", ["아이디어", "회고", "계획", "학습", "일상"])
            d_content = st.text_area("내용", height=200)
            if st.form_submit_button("저장하기"):
                new_diary = pd.DataFrame([{'date': str(now_kst), 'title': d_title, 'content': d_content, 'tags': ", ".join(d_tags), 'level': 'Normal'}])
                conn.update(worksheet="Diary", data=pd.concat([df_diary, new_diary], ignore_index=True)); st.rerun()
    with dt2:
        if not df_diary.empty:
            search_q = st.text_input("🔍 제목 검색")
            filt_df = df_diary[df_diary['title'].str.contains(search_q, na=False)] if search_q else df_diary
            for i, row in filt_df.iloc[::-1].iterrows():
                with st.expander(f"{row['date']} | {row['title']}"):
                    with st.form(f"edit_diary_{i}"):
                        e_title = st.text_input("제목", value=row['title'])
                        e_content = st.text_area("내용", value=row['content'], height=150)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 수정 저장"):
                            df_diary.at[i, 'title'] = e_title; df_diary.at[i, 'content'] = e_content
                            conn.update(worksheet="Diary", data=df_diary); st.rerun()
                        if c2.form_submit_button("🗑️ 삭제"):
                            conn.update(worksheet="Diary", data=df_diary.drop(i)); st.rerun()

# --- [9. 뉴스저장] ---
elif menu == "📰 뉴스저장":
    st.header("📰 지식 큐레이션 (뉴스 & 아티클)")
    df_media = load_data_safe("Media")
    with st.form("media_form", clear_on_submit=True):
        m_title = st.text_input("기사 제목"); m_url = st.text_input("URL"); m_insight = st.text_area("인사이트")
        if st.form_submit_button("지식 저장"):
            new_media = pd.DataFrame([{'date': str(now_kst), 'category': '기타', 'title': m_title, 'url': m_url, 'insight': m_insight}])
            conn.update(worksheet="Media", data=pd.concat([df_media, new_media], ignore_index=True)); st.rerun()
    if not df_media.empty:
        for i, row in df_media.iloc[::-1].iterrows():
            with st.expander(f"{row['title']}"):
                st.write(f"💡 {row['insight']}"); st.markdown(f"🔗 [기사 읽으러 가기]({row['url']})")
                if st.button("🗑️ 삭제", key=f"mdel_{i}"):
                    conn.update(worksheet="Media", data=df_media.drop(i)); st.rerun()