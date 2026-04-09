import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go
import os
import plotly.express as px
import requests
import numpy as np
from io import StringIO

# 1. 앱 설정
st.set_page_config(page_title="은퇴 준비하기 v5.6.7", layout="wide")

# 2. 구글 시트 고유 ID (에러 방지용 무적 로직)
SHEET_ID = "1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA"

# --- [데이터 로드 함수: 라이브러리 버그를 우회하는 직접 호출] ---
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
        
        if s_name.lower() in ["data", "personaldata", "cashflow"] and 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            
        if s_name.lower() == "sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
        return df
    except:
        return pd.DataFrame()

# 저장 기능을 위한 커넥션 선언
conn = st.connection("gsheets", type=GSheetsConnection)

def load_book_data():
    if os.path.exists('books.csv'):
        try:
            df = pd.read_csv('books.csv')
            df = df.dropna(subset=['제목'])
            df['구입일'] = pd.to_datetime(df['구입일']).dt.date
            df['연도'] = pd.to_datetime(df['구입일']).dt.year.fillna(0).astype(int)
            df['가격'] = pd.to_numeric(df['가격'], errors='coerce').fillna(0).astype(int)
            df['별점'] = pd.to_numeric(df['별점'], errors='coerce').fillna(5).astype(int)
            return df
        except: return pd.DataFrame(columns=['제목', '저자', '가격', '구입일', '구입처', '분류', '별점', '코멘트', '연도'])
    return pd.DataFrame(columns=['제목', '저자', '가격', '구입일', '구입처', '분류', '별점', '코멘트', '연도'])

def load_travel_data():
    if not os.path.exists('travel_dest.csv'): pd.DataFrame(columns=['id', 'name', 'start_date', 'end_date', 'status']).to_csv('travel_dest.csv', index=False)
    if not os.path.exists('travel_expenses.csv'): pd.DataFrame(columns=['dest_id', 'date', 'time', 'item', 'place', 'category', 'method', 'amount', 'unit', 'memo']).to_csv('travel_expenses.csv', index=False)
    dest, exp = pd.read_csv('travel_dest.csv'), pd.read_csv('travel_expenses.csv')
    exp['item'] = exp['item'].fillna('미입력'); exp['place'] = exp['place'].fillna('미입력')
    return dest, exp

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

# --- [사이드바 메뉴] ---
with st.sidebar:
    st.title("은퇴 준비하기")
    menu = st.radio("메뉴", ["💰 연금자산", "📈 연금시뮬", "💸 현금흐름", "💵 개인자산", "🔤 영어공부", "📚 도서관리", "✈️ 여행관리"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

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
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        p_amt = st.number_input("금액(원)", step=100000)
        if st.button("저장"):
            df = load_data_safe("Data")
            t_date = f"{py}-{pm}"; mask = (df['date'] == t_date) & (df['account'] == p_acc)
            if mask.any(): df.loc[mask, 'amount'] = int(p_amt)
            else: df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc, "amount": int(p_amt), "memo": ""}])], ignore_index=True)
            conn.update(worksheet="Data", data=df); st.toast("저장 완료!"); st.rerun()

# --- [2. 연금시뮬 - 요청하신 제언/전략 100% 반영] ---
elif menu == "📈 연금시뮬":
    st.header("📈 은퇴 후 연금 마스터 시뮬레이터")
    df_p = load_data_safe("Data")
    current_total = 0
    if not df_p.empty:
        dates_sorted = sorted(df_p['date'].unique(), key=lambda x: pd.to_datetime(x, format='%Y-%m', errors='coerce'))
        latest_date = dates_sorted[-1]
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
        **1. 4% 법칙 (Safe Withdrawal Rate)**: 
        전체 자산의 4% 이내로 매년 인출하면 자산이 마르지 않을 확률이 매우 높습니다. 
        현재 Byungjoo님의 자산 규모에서는 월 600~700만원 수준이 골디락스 존(Goldilocks Zone)입니다.
        
        **2. 현금성 자산 2년치 보유**: 
        시장이 폭락할 때 연금을 인출하면 자산 회복이 불가능해집니다. 하락장을 버틸 2년치 생활비는 항상 예금/채권으로 별도 관리하세요.
        """)

# --- [3. 현금흐름 - 복합 분석 로직 100% 복구] ---
elif menu == "💸 현금흐름":
    st.header("💸 현금흐름 관리 (은퇴 준비)")
    df_cf = load_data_safe("CashFlow"); df_bg = load_data_safe("Budgets")
    CF_CATEGORIES = ["급여", "배당금", "고정지출", "변동지출", "자기계발", "저축/투자", "쇼핑", "외식", "생활비", "기기", "기타"]
    c_f1, c_f2 = st.columns(2)
    sel_y = c_f1.selectbox("조회 연도", [2025, 2026, 2027, 2028], index=1)
    sel_m = c_f2.selectbox("조회 월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1)
    sel_period = f"{sel_y}-{sel_m}"
    t1, t2, t3, t4, t5 = st.tabs(["🚦 소비 신호등", "📝 내역 기록", "📊 지출 패턴 분석", "✏️ 내역 수정/삭제", "⚙️ 예산 설정"])
    with t1:
        st.subheader(f"🚦 {sel_period} 소비 신호등")
        total_spent = 0
        if not df_cf.empty:
            df_cf['date_dt'] = pd.to_datetime(df_cf['date'], errors='coerce')
            m_exp = df_cf[(df_cf['type'] == 'EXPENSE') & (df_cf['date_dt'].dt.strftime("%Y-%m") == sel_period)]
            total_spent = m_exp['amount'].sum()
        current_budget = 0 
        if not df_bg.empty:
            bg_row = df_bg[df_bg['period'] == sel_period]
            if not bg_row.empty: current_budget = bg_row['budget_amount'].iloc[0]
        if current_budget == 0:
            st.info(f"📢 {sel_period}의 예산이 설정되지 않았습니다.")
            c1, c2 = st.columns(2); c1.metric("현재 지출", f"{int(total_spent):,}원"); c2.metric("설정 예산", "0원")
        else:
            percent = (total_spent / current_budget) * 100
            c1, c2, c3 = st.columns(3)
            if percent < 70: c1.metric("소비 상태", "✅ 안전", f"{int(current_budget-total_spent):,}원 남음"); st.success(f"예산의 {percent:.1f}% 사용 중. 아주 훌륭합니다!")
            elif percent < 90: c1.metric("소비 상태", "🟡 주의", f"{int(current_budget-total_spent):,}원 남음"); st.warning(f"예산의 {percent:.1f}% 사용 중. 지출을 조절하세요.")
            else: c1.metric("소비 상태", "🚨 위험", f"{int(current_budget-total_spent):,}원 남음"); st.error("예산 초과 임박! 소비 통제가 필요합니다.")
    with t2:
        st.subheader("📝 일일 현금흐름 기록")
        with st.form("cf_form_v2", clear_on_submit=True):
            c1, c2 = st.columns(2)
            f_date = c1.date_input("날짜", datetime.date.today()); f_type = c1.selectbox("구분", ["EXPENSE", "INCOME"])
            f_cat = c2.selectbox("카테고리", CF_CATEGORIES); f_amt = c2.number_input("금액", min_value=0, step=1000)
            f_memo = st.text_input("메모"); f_rec = st.checkbox("정기 지출/수입 여부")
            if st.form_submit_button("기록 저장"):
                new_data = pd.DataFrame([{"date": str(f_date), "type": f_type, "category": f_cat, "amount": f_amt, "memo": f_memo, "is_recurring": str(f_rec).upper()}])
                conn.update(worksheet="CashFlow", data=pd.concat([df_cf.drop(columns=['date_dt'], errors='ignore'), new_data], ignore_index=True)); st.success("저장되었습니다!"); st.rerun()
    with t3:
        st.subheader(f"📊 {sel_period} 지출 분석")
        if not df_cf.empty:
            m_exp_only = df_cf[(df_cf['type'] == 'EXPENSE') & (pd.to_datetime(df_cf['date']).dt.strftime("%Y-%m") == sel_period)]
            if not m_exp_only.empty:
                fig = px.pie(m_exp_only, values='amount', names='category', hole=0.4); st.plotly_chart(fig, use_container_width=True)
                st.dataframe(m_exp_only[['date', 'category', 'amount', 'memo']].sort_values('date', ascending=False), use_container_width=True)
            else: st.info("내역이 없습니다.")
    with t4:
        st.subheader("✏️ 내역 수정 및 삭제")
        if not df_cf.empty:
            m_data = df_cf[pd.to_datetime(df_cf['date'], errors='coerce').dt.strftime("%Y-%m") == sel_period]
            if not m_data.empty:
                edit_list = m_data.apply(lambda x: f"[{x['date']}] {x['category']} - {x['memo']} ({int(x['amount']):,}원)", axis=1).tolist()
                sel_item = st.selectbox("항목 선택", options=edit_list); sel_idx = m_data.index[edit_list.index(sel_item)]
                with st.form("edit_cf_v2"):
                    sel_row = df_cf.loc[sel_idx]; c1, c2 = st.columns(2)
                    e_date = c1.date_input("날짜", value=pd.to_datetime(sel_row['date']).date()); e_type = c1.selectbox("구분", ["EXPENSE", "INCOME"], index=0 if sel_row['type']=="EXPENSE" else 1)
                    cat_idx = CF_CATEGORIES.index(sel_row['category']) if sel_row['category'] in CF_CATEGORIES else 0
                    e_cat = c2.selectbox("카테고리", CF_CATEGORIES, index=cat_idx); e_amt = c2.number_input("금액", value=int(sel_row['amount'])); e_memo = st.text_input("메모", value=str(sel_row['memo']))
                    b1, b2 = st.columns(2)
                    if b1.form_submit_button("💾 수정"):
                        df_cf.at[sel_idx, ['date', 'type', 'category', 'amount', 'memo']] = [str(e_date), e_type, e_cat, e_amt, e_memo]
                        conn.update(worksheet="CashFlow", data=df_cf.drop(columns=['date_dt'], errors='ignore')); st.rerun()
                    if b2.form_submit_button("🗑️ 삭제"):
                        conn.update(worksheet="CashFlow", data=df_cf.drop(sel_idx).drop(columns=['date_dt'], errors='ignore')); st.rerun()
    with t5:
        st.subheader(f"⚙️ {sel_period} 예산 설정")
        with st.form("budget_form"):
            new_bg = st.number_input("목표 예산(원)", value=int(current_budget), step=100000)
            if st.form_submit_button("예산 저장"):
                if not df_bg.empty and (df_bg['period'] == sel_period).any(): df_bg.loc[df_bg['period'] == sel_period, 'budget_amount'] = new_bg
                else: df_bg = pd.concat([df_bg, pd.DataFrame([{"category": "전체", "budget_amount": new_bg, "period": sel_period}])], ignore_index=True)
                conn.update(worksheet="Budgets", data=df_bg); st.success("예산이 저장되었습니다!"); st.rerun()

# --- [4. 개인자산, 5. 영어공부 로직 (원본 동일)] ---
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
                cur = w_total.iloc[-1]; prev = w_total.iloc[-2] if len(w_total)>1 else cur
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
        pery = c1.selectbox("연도", [2026, 2027, 2028], key="per_y"); perw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타']); per_amt = st.number_input("금액(원)", step=10000)
        if st.button("개인자산 저장"):
            df = load_data_safe("PersonalData")
            t_date = f"Y{pery}W{perw}"; mask = (df['date'] == t_date) & (df['account'] == p_acc_per)
            if mask.any(): df.loc[mask, 'amount'] = int(per_amt)
            else: df = pd.concat([df, pd.DataFrame([{"date": t_date, "account": p_acc_per, "amount": int(per_amt), "memo": ""}])], ignore_index=True)
            conn.update(worksheet="PersonalData", data=df); st.toast("저장 완료!"); st.rerun()

elif menu == "🔤 영어공부":
    st.header("🔤 영어 공부")
    df_en = load_data_safe("Sheet1")
    t1, t2, t3, t4 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "✏️ 문장 수정/삭제", "🧠 퀴즈"])
    with t1:
        if not df_en.empty:
            ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True, key="en_ed")
            if st.button("암기 상태 저장"):
                df_en.update(ed); save_df = df_en.copy(); save_df['memorized'] = save_df['memorized'].astype(str).str.upper()
                conn.update(worksheet="Sheet1", data=save_df); st.toast("✅ 저장 완료!"); st.rerun()
    with t2:
        with st.form("en_in_form", clear_on_submit=True):
            new_en = st.text_input("영어 문장"); new_ko = st.text_input("한글 뜻")
            if st.form_submit_button("문장 저장"):
                if new_en and new_ko:
                    new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": new_en, "korean": new_ko, "memorized": False}])
                    conn.update(worksheet="Sheet1", data=pd.concat([df_en, new_row], ignore_index=True)); st.success("저장 완료!"); st.rerun()
    with t3:
        if not df_en.empty:
            edit_list = df_en.apply(lambda x: f"[{x['date']}] {x['english']}", axis=1).tolist(); sel_en = st.selectbox("수정할 문장", options=edit_list); en_idx = df_en.index[edit_list.index(sel_en)]
            with st.form("edit_en"):
                e_en = st.text_input("영어", value=str(df_en.loc[en_idx, 'english'])); e_ko = st.text_input("한글", value=str(df_en.loc[en_idx, 'korean']))
                c1, c2 = st.columns(2)
                if c1.form_submit_button("💾 수정"):
                    df_en.at[en_idx, 'english'] = e_en; df_en.at[en_idx, 'korean'] = e_ko; conn.update(worksheet="Sheet1", data=df_en); st.rerun()
                if c2.form_submit_button("🗑️ 삭제"):
                    conn.update(worksheet="Sheet1", data=df_en.drop(en_idx)); st.rerun()
    with t4:
        if not df_en.empty:
            unmem = df_en[df_en['memorized'] == False]
            if not unmem.empty:
                if 'q_idx' not in st.session_state: st.session_state.q_idx = unmem.sample(n=1).index[0]
                q = unmem.loc[st.session_state.q_idx]; st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력", key="quiz_input")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                    else: st.error(f"오답! 정답: {q['english']}")
                st.button("다음 문제", on_click=reset_quiz)

# --- [6. 도서관리 - 상세 기획 복구 완료] ---
elif menu == "📚 도서관리":
    st.header("📚 도서 관리 시스템")
    df_books = load_book_data()
    c1, c2, c3 = st.columns([1, 1, 2])
    sel_y = c1.selectbox("조회 연도", options=["2026년", "2027년", "2028년"])
    y_int = int(sel_y.replace("년", "")); y_df = df_books[df_books['연도'] == y_int]
    c2.metric(f"{y_int}년 독서량", f"{len(y_df)} 권"); c3.metric(f"{y_int}년 도서 구입비", f"₩{int(y_df['가격'].sum()):,}")
    st.divider(); tab1, tab2, tab3 = st.tabs(["📖 서재 보기", "➕ 신규 등록", "✏️ 수정/삭제"])
    with tab1:
        if not df_books.empty:
            st.table(df_books.iloc[::-1][['구입일', '제목', '저자', '분류', '별점', '가격']].head(10).assign(
                별점=lambda x: x['별점'].map(lambda s: '⭐' * int(s)), 가격=lambda x: x['가격'].map(lambda p: f"{int(p):,}")
            ))
    with tab2:
        with st.form("book_reg", clear_on_submit=True):
            tc1, tc2 = st.columns(2); t = tc1.text_input("제목 (필수)"); a = tc1.text_input("저자"); p = tc1.number_input("가격", step=1000); s = tc1.text_input("구입처")
            d = tc2.date_input("구입일", datetime.date.today()); cat = tc2.selectbox("분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "에세이", "역사", "기타"]); r = tc2.slider("별점", 1, 5, 5); cmt = st.text_area("코멘트")
            if st.form_submit_button("도서 등록") and t:
                new = pd.DataFrame([{'제목': t, '저자': a, '가격': int(p), '구입일': d, '구입처': s, '분류': cat, '별점': int(r), '코멘트': cmt, '연도': d.year}])
                pd.concat([df_books, new]).to_csv('books.csv', index=False); st.success("저장 완료!"); st.rerun()
    with tab3:
        if not df_books.empty:
            sel_b = st.selectbox("수정할 책 선택", options=df_books.iloc[::-1]['제목'].tolist()); b_ed = df_books[df_books['제목'] == sel_b].iloc[0]
            with st.form("edit_book_full"):
                ec1, ec2 = st.columns(2); e_t = ec1.text_input("제목", value=str(b_ed['제목'])); e_a = ec1.text_input("저자", value=str(b_ed['저자'])); e_p = ec1.number_input("가격", value=int(b_ed['가격'])); e_s = ec1.text_input("구입처", value=str(b_ed['구입처']))
                e_d = ec2.date_input("구입일", value=pd.to_datetime(b_ed['구입일']).date()); e_cat = ec2.selectbox("분류", ["경제/경영", "자기계발", "IT/과학", "외국어", "심리/인문", "소설", "에세이", "역사", "기타"], index=0); e_r = ec2.slider("별점", 1, 5, int(b_ed['별점'])); e_cmt = st.text_area("코멘트", value=str(b_ed['코멘트']))
                if st.form_submit_button("💾 수정 저장"):
                    df_books.loc[df_books['제목'] == sel_b, ['제목', '저자', '가격', '구입일', '구입처', '분류', '별점', '코멘트', '연도']] = [e_t, e_a, int(e_p), e_d, e_s, e_cat, int(e_r), e_cmt, e_d.year]
                    df_books.to_csv('books.csv', index=False); st.success("수정 완료!"); st.rerun()

# --- [7. 여행관리 - 결제수단 및 타임라인 CSS 복구 완료] ---
elif menu == "✈️ 여행관리":
    st.header("✈️ Byungjoo 여행기록")
    df_dest, df_exp = load_travel_data()
    t_home, t_ledger, t_timeline, t_stats, t_edit = st.tabs(["🗺️ 여행지 관리", "💰 비용 리스트", "🗓️ 타임라인", "📊 지출 요약", "⚙️ 항목 수정/삭제"])
    with t_home:
        st.subheader("📍 신규 여행지 등록")
        with st.form("new_dest_form", clear_on_submit=True):
            c1, c2, c3 = st.columns([2, 2, 1]); new_name = c1.text_input("여행지명"); new_start = c2.date_input("시작일", datetime.date.today()); new_end = c2.date_input("종료일", datetime.date.today() + datetime.timedelta(days=3)); new_status = c3.selectbox("상태", ["준비", "여행중", "완료"])
            if st.form_submit_button("여행지 추가") and new_name:
                new_id = int(df_dest['id'].max() + 1) if not df_dest.empty else 1
                new_row = pd.DataFrame([{'id': new_id, 'name': new_name, 'start_date': new_start, 'end_date': new_end, 'status': new_status}])
                pd.concat([df_dest, new_row]).to_csv('travel_dest.csv', index=False); st.success(f"'{new_name}' 등록 완료!"); st.rerun()
    if not df_dest.empty:
        sel_city = st.sidebar.selectbox("📍 여행지 선택", options=df_dest['name'].tolist()); curr = df_dest[df_dest['name'] == sel_city].iloc[0]; d_exp = df_exp[df_exp['dest_id'] == curr['id']].copy(); d_exp['amount'] = pd.to_numeric(d_exp['amount'], errors='coerce').fillna(0).astype(int)
        with t_ledger:
            st.metric(f"'{sel_city}' 총 지출", f"₩{int(d_exp['amount'].sum()):,}")
            with st.expander("➕ 새 비용 등록", expanded=True):
                with st.form("t_add"):
                    c1, c2 = st.columns(2); d = c1.date_input("날짜"); tm = c1.time_input("시간"); it = c2.text_input("항목"); pl = c2.text_input("장소"); cat = st.selectbox("카테고리", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"]); pay = st.selectbox("결제수단", ["트래블월렛", "하나카드", "삼성카드", "현금"]); unit = st.selectbox("통화", ["KRW", "TWD", "USD", "EUR"]); amt = c2.number_input("금액", min_value=0)
                    if st.form_submit_button("저장") and it:
                        rate = get_rate(unit); new_e = pd.DataFrame([{'dest_id': curr['id'], 'date': str(d), 'time': tm.strftime('%H:%M'), 'item': it, 'place': pl, 'category': cat, 'method': pay, 'amount': int(amt*rate), 'unit': 'KRW', 'memo': ''}])
                        pd.concat([df_exp, new_e]).to_csv('travel_expenses.csv', index=False); st.rerun()
            for i, r in d_exp.sort_values(['date', 'time'], ascending=False).iterrows():
                row_c1, row_c2 = st.columns([4, 1]); row_c1.markdown(f"**{r['item']}** @ {r['place']}"); row_c1.caption(f"{r['date']} {r['time']} | {r['method']}"); row_c2.markdown(f"<p style='text-align:right; font-weight:bold; color:#0d6efd;'>₩{int(r['amount']):,}</p>", unsafe_allow_html=True); st.divider()
        with t_timeline:
            if not d_exp.empty:
                tl_df = d_exp.copy(); tl_df['datetime'] = pd.to_datetime(tl_df['date'] + ' ' + tl_df['time']); tl_df = tl_df.sort_values('datetime', ascending=True)
                st.markdown("""<style>.timeline-container { position: relative; padding: 20px 0; margin-left: 20px; border-left: 2px solid #007bff; }.timeline-item { position: relative; margin-bottom: 30px; padding-left: 30px; }.timeline-dot { position: absolute; left: -9px; top: 5px; width: 16px; height: 16px; background-color: #007bff; border-radius: 50%; }.timeline-date { font-size: 0.85rem; color: #007bff; font-weight: bold; }</style>""", unsafe_allow_html=True)
                for _, row in tl_df.iterrows():
                    st.markdown(f'<div class="timeline-container"><div class="timeline-item"><div class="timeline-dot"></div><div class="timeline-date">{row["date"]} {row["time"]} | {row["place"]}</div><div class="timeline-title">{row["item"]} (₩{int(row["amount"]):,})</div></div></div>', unsafe_allow_html=True)
        with t_stats:
            c1, c2 = st.columns(2); c1.write("**📅 일자별 지출**"); c1.write(d_exp.groupby('date')['amount'].sum().map(lambda x: f"₩{int(x):,}")); c2.write("**💳 결제수단별**"); c2.write(d_exp.groupby('method')['amount'].sum().map(lambda x: f"₩{int(x):,}"))
        with t_edit:
            edit_list = d_exp.apply(lambda x: f"[{x['date']} {x['time']}] {x['item']}", axis=1).tolist(); sel_l = st.selectbox("항목 선택", options=edit_list); t_idx = d_exp.index[edit_list.index(sel_l)]
            if st.button("항목 삭제"):
                df_exp = df_exp.drop(t_idx); df_exp.to_csv('travel_expenses.csv', index=False); st.rerun()