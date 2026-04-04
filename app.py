import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go
import os
import plotly.express as px
import requests

# 1. 앱 설정
st.set_page_config(page_title="은퇴 준비하기 v4.8.5", layout="wide")

# 2. 구글 시트 연결 (원본 유지)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [데이터 로드 함수 - 절대 수정 금지] ---
def load_data_safe(s_name):
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet=s_name, ttl=0)
        if df is None or df.empty: return pd.DataFrame()
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        if 'date' in df.columns: df['date'] = df['date'].astype(str).str.strip().str.upper()
        if s_name in ["Data", "PersonalData"] and 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        if s_name == "Sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
        return df
    except Exception as e:
        st.error(f"❌ '{s_name}' 로드 실패: {e}")
        return pd.DataFrame()

# --- [도서/여행 데이터 로드] ---
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
    return pd.read_csv('travel_dest.csv'), pd.read_csv('travel_expenses.csv')

# --- [환율 계산] ---
def get_rate(unit):
    if unit == "KRW": return 1
    try:
        res = requests.get(f"https://api.exchangerate-api.com/v4/latest/{unit}").json()
        return res['rates']['KRW']
    except:
        backup = {"TWD": 47, "USD": 1490, "EUR": 1500}
        return backup.get(unit, 1)

# --- [기존 저장 로직 - 절대 수정 금지] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    df = load_data_safe(s_name)
    target_date = str(date_val).strip().upper()
    mask = (df['date'] == target_date) & (df['account'] == str(acc))
    if mask.any(): df.loc[mask, 'amount'] = int(amt_val)
    else: 
        new_row = pd.DataFrame([{"date": target_date, "account": str(acc), "amount": int(amt_val), "memo": ""}])
        df = pd.concat([df, new_row], ignore_index=True)
    conn.update(spreadsheet=SHEET_URL, worksheet=s_name, data=df)
    st.session_state[amt_key] = 0
    st.toast(f"✅ {acc} 저장 완료!")

def handle_save_english():
    en, ko = st.session_state.new_en, st.session_state.new_ko
    if en and ko:
        df_en = load_data_safe("Sheet1")
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": False}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=df_en)
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✅ 문장 저장 완료!")

# --- [사이드바] ---
with st.sidebar:
    st.title("은퇴 준비하기")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부", "📚 도서관리", "✈️ 여행관리"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직: 자산/영어/도서 원본 유지] ---
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
                fig.update_layout(barmode='stack', xaxis={'categoryorder':'array', 'categoryarray':recent}, height=400)
                st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        py = c1.selectbox("연도", [2026, 2027, 2028], key="p_y")
        pm = c2.selectbox("월", [f"{i:02d}" for i in range(1, 13)], index=datetime.date.today().month-1, key="p_m")
        p_acc = st.selectbox("항목", ['퇴직연금', 'IRP', 'ISA', '개인연금'])
        st.number_input("금액(원)", step=100000, key="p_amt")
        st.button("연금 저장", on_click=handle_save_asset, args=("Data", f"{py}-{pm}", p_acc, "p_amt"))

elif menu == "💵 개인자산":
    st.header("💵 개인자산 관리")
    df_per = load_data_safe("PersonalData")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_per.empty and 'date' in df_per.columns:
            def get_w(k):
                try:
                    k = str(k).upper().strip(); y = int(k[1:5]); w = int(k.split('W')[1])
                    d = datetime.date(y, 1, 1) + datetime.timedelta(weeks=w-1)
                    return f"{d.month}월 {((d.day-1)//7)+1}주 (W{w})"
                except: return k
            weeks = sorted([str(d) for d in df_per['date'].unique()])
            if weeks:
                recent = weeks[-3:]; df_r = df_per[df_per['date'].isin(recent)]
                w_total = df_r.groupby('date')['amount'].sum().reindex(recent).fillna(0)
                cur = w_total.iloc[-1]; prev = w_total.iloc[-2] if len(w_total)>1 else cur
                diff = cur - prev
                c1, c2 = st.columns(2)
                c1.metric(f"{get_w(recent[-1])} 합계", f"{int(cur):,}원")
                p_change = (diff/prev*100) if prev != 0 else 0
                c2.metric("전주 대비", f"{p_change:+.1f}%", f"{int(diff):+,}원")
                fig = go.Figure()
                for acc in sorted(df_r['account'].unique()):
                    acc_df = df_r[df_r['account'] == acc].set_index('date').reindex(recent).fillna(0).reset_index()
                    fig.add_trace(go.Bar(x=[get_w(d) for d in acc_df['date']], y=acc_df['amount'], name=acc))
                fig.update_layout(barmode='stack', xaxis={'categoryorder':'array', 'categoryarray':recent}, height=400)
                st.plotly_chart(fig, use_container_width=True)
    with t2:
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2026, 2027, 2028], key="per_y")
        perw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

elif menu == "🔤 영어공부":
    st.header("🔤 영어 공부")
    df_en = load_data_safe("Sheet1")
    t1, t2, t3 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈"])
    with t1:
        if not df_en.empty:
            ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True, key="en_ed")
            if st.button("암기 상태 저장"):
                df_en.update(ed); save_df = df_en.copy(); save_df['memorized'] = save_df['memorized'].astype(str).str.upper()
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=save_df); st.toast("✅ 저장 완료!"); st.rerun()

elif menu == "📚 도서관리":
    st.header("📚 도서 관리 시스템")
    df_books = load_book_data()
    c1, c2, c3 = st.columns([1, 1, 2])
    sel_y = c1.selectbox("조회 연도", options=["2026년", "2027년", "2028년"])
    y_int = int(sel_y.replace("년", "")); y_df = df_books[df_books['연도'] == y_int]
    c2.metric(f"{y_int}년 독서량", f"{len(y_df)} 권"); c3.metric(f"{y_int}년 도서 구입비", f"₩{int(y_df['가격'].sum()):,}")
    st.divider()
    tab1, tab2, tab3 = st.tabs(["📖 서재 보기", "➕ 신규 등록", "✏️ 수정/삭제"])
    with tab1:
        if not df_books.empty:
            st.table(df_books.iloc[::-1][['구입일', '제목', '저자', '분류', '별점', '가격']].head(10).assign(
                별점=lambda x: x['별점'].map(lambda s: '⭐' * int(s)), 가격=lambda x: x['가격'].map(lambda p: f"{int(p):,}")
            ))

# --- [✈️ 여행관리: 여행지 등록 기능 최상단 배치 및 소수점 제거] ---
elif menu == "✈️ 여행관리":
    st.header("✈️ Byungjoo 여행기록")
    df_dest, df_exp = load_travel_data()
    
    # 탭 구성: 여행지 관리 탭을 첫 번째로 배치하여 접근성 강화
    t_home, t_ledger, t_timeline, t_stats, t_edit = st.tabs(["🗺️ 여행지 관리", "💰 비용 리스트", "🗓️ 타임라인", "📊 지출 요약", "⚙️ 항목 수정/삭제"])

    with t_home:
        st.subheader("📍 신규 여행지 등록")
        with st.form("new_destination_form"):
            c1, c2 = st.columns(2)
            n_name = c1.text_input("여행지명 (예: 마드리드, 타이페이)")
            n_status = c1.selectbox("여행 상태", ["준비중", "진행중", "완료"])
            n_start = c2.date_input("시작일", datetime.date.today())
            n_end = c2.date_input("종료일", datetime.date.today() + datetime.timedelta(days=3))
            if st.form_submit_button("🌎 새로운 여행지 저장"):
                if n_name:
                    new_dest_id = int(df_dest['id'].max() + 1) if not df_dest.empty else 1
                    new_dest = pd.DataFrame([{'id': new_dest_id, 'name': n_name, 'start_date': str(n_start), 'end_date': str(n_end), 'status': n_status}])
                    pd.concat([df_dest, new_dest]).to_csv('travel_dest.csv', index=False)
                    st.success(f"'{n_name}' 여행지가 등록되었습니다!"); st.rerun()
                else: st.error("여행지명을 입력해주세요.")
        
        st.divider()
        st.subheader("📂 기존 여행지 목록")
        if not df_dest.empty:
            st.table(df_dest[['name', 'start_date', 'end_date', 'status']])
        else: st.info("등록된 여행지가 없습니다.")

    # 여행지 선택 섹션
    if not df_dest.empty:
        st.sidebar.divider()
        sel_city = st.sidebar.selectbox("📍 현재 조회 중인 여행지", options=df_dest['name'].tolist())
        curr = df_dest[df_dest['name'] == sel_city].iloc[0]
        st.sidebar.info(f"📅 **{curr['name']}**\n{curr['start_date']} ~ {curr['end_date']}")
        
        d_exp = df_exp[df_exp['dest_id'] == curr['id']].copy()
        # [소수점 제거] 데이터 타입 정수형으로 강제 변환
        d_exp['amount'] = pd.to_numeric(d_exp['amount'], errors='coerce').fillna(0).astype(int)
        d_exp = d_exp.sort_values(['date', 'time'], ascending=False)

        with t_ledger:
            st.metric(f"'{sel_city}' 총 지출", f"₩{int(d_exp['amount'].sum()):,}")
            st.write("---")
            for i, r in d_exp.iterrows():
                with st.container():
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.markdown(f"**{r['item']}** @ {r['place']}")
                        st.caption(f"{r['date']} {r['time']} | {r['method']} | {r['category']}")
                    with c2:
                        # [소수점 제거 표시]
                        st.markdown(f"<p style='text-align:right; font-weight:bold; color:#0d6efd;'>₩{int(r['amount']):,}</p>", unsafe_allow_html=True)
                    st.divider()

        with t_timeline:
            for _, r in d_exp.sort_values(['date', 'time']).iterrows():
                st.markdown(f"🔵 **{r['date']} {r['time']}** | {r['place']}  \n**{r['item']}** (₩{int(r['amount']):,})")
                st.divider()

        with t_stats:
            col1, col2 = st.columns(2)
            col1.write("**📅 일자별 지출**")
            col1.write(d_exp.groupby('date')['amount'].sum().map(lambda x: f"₩{int(x):,}"))
            col2.write("**📁 카테고리별**")
            col2.write(d_exp.groupby('category')['amount'].sum().map(lambda x: f"₩{int(x):,}"))

        with t_edit:
            if not d_exp.empty:
                edit_list = d_exp.apply(lambda x: f"[{x['date']} {x['time']}] {x['item']}", axis=1).tolist()
                sel_label = st.selectbox("편집할 항목 선택", options=edit_list)
                t_idx = d_exp.index[edit_list.index(sel_label)]
                t_row = d_exp.loc[t_idx]
                
                with st.form("edit_travel_safe"):
                    e_col1, e_col2 = st.columns(2)
                    e_it = e_col1.text_input("항목명", value=str(t_row['item']))
                    e_pl = e_col1.text_input("장소", value=str(t_row['place']))
                    # [소수점 제거] step을 1로 설정하여 정수 입력 유도
                    e_amt = e_col1.number_input("금액(원)", value=int(t_row['amount']), step=1)
                    e_date = e_col2.date_input("날짜", value=pd.to_datetime(t_row['date']).date())
                    e_time = e_col2.time_input("시간", value=datetime.datetime.strptime(str(t_row['time']), "%H:%M").time())
                    
                    cats = ["식비", "교통", "관광", "쇼핑", "숙박", "기타"]
                    e_cat = e_col2.selectbox("카테고리", options=cats, index=cats.index(t_row['category']) if t_row['category'] in cats else 0)
                    pays = ["트래블월렛", "하나카드", "삼성카드", "현금"]
                    e_pay = e_col2.selectbox("결제수단", options=pays, index=pays.index(t_row['method']) if t_row['method'] in pays else 0)
                    
                    if st.form_submit_button("💾 수정 내용 저장"):
                        df_exp.at[t_idx, 'item'] = e_it
                        df_exp.at[t_idx, 'place'] = e_pl
                        df_exp.at[t_idx, 'amount'] = int(e_amt) # 정수 저장
                        df_exp.at[t_idx, 'date'] = str(e_date)
                        df_exp.at[t_idx, 'time'] = e_time.strftime('%H:%M')
                        df_exp.at[t_idx, 'category'] = e_cat
                        df_exp.at[t_idx, 'method'] = e_pay
                        df_exp.to_csv('travel_expenses.csv', index=False); st.success("수정되었습니다."); st.rerun()

    # 비용 등록 폼 (사이드바 선택된 도시에 종속)
    if not df_dest.empty:
        with st.expander(f"➕ [{sel_city}] 새 비용/일정 등록"):
            with st.form("t_form_add", clear_on_submit=True):
                c1, c2 = st.columns(2)
                d = c1.date_input("날짜", datetime.date.today()); tm = c1.time_input("시간", datetime.datetime.now().time())
                it = c2.text_input("항목"); pl = c2.text_input("장소")
                cat = st.selectbox("카테고리", ["식비", "교통", "관광", "쇼핑", "숙박", "기타"])
                pay = st.selectbox("결제수단", ["트래블월렛", "하나카드", "삼성카드", "현금"])
                unit = st.selectbox("통화", ["KRW", "TWD", "USD", "EUR"])
                # [소수점 제거] step을 1로 설정
                amt = st.number_input("금액", min_value=0, step=1)
                if st.form_submit_button("저장"):
                    rate = get_rate(unit)
                    amt_krw = int(amt * rate) # 환율 계산 후에도 정수형 유지
                    new_e = pd.DataFrame([{'dest_id': curr['id'], 'date': d, 'time': tm.strftime('%H:%M'), 'item': it, 'place': pl, 'category': cat, 'method': pay, 'amount': amt_krw, 'unit': 'KRW', 'memo': f"{amt}{unit}(환율:{rate:.2f})" }])
                    pd.concat([df_exp, new_e]).to_csv('travel_expenses.csv', index=False); st.success("저장 완료!"); st.rerun()