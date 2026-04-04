import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import plotly.graph_objects as go
import os

# 1. 앱 설정
st.set_page_config(page_title="Byungjoo Pro v4.4", layout="wide")

# 2. 구글 시트 연결 (원본 유지)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1LrVto7YUbodWwGsRBQ0PR7evNnEmDtf_gNEj8gM7ngA/edit#gid=0"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [기존 데이터 로드 함수 - 절대 수정 금지] ---
def load_data_safe(s_name):
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet=s_name, ttl=0)
        if df is None or df.empty:
            return pd.DataFrame()
        df.columns = [str(c).strip().lower() for c in df.columns]
        df = df.dropna(how='all')
        if 'date' in df.columns:
            df['date'] = df['date'].astype(str).str.strip().str.upper()
        if s_name in ["Data", "PersonalData"] and 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        if s_name == "Sheet1" and 'memorized' in df.columns:
            df['memorized'] = df['memorized'].astype(str).str.upper().str.strip() == "TRUE"
        return df
    except Exception as e:
        st.error(f"❌ '{s_name}' 로드 실패: {e}")
        return pd.DataFrame()

# --- [도서 관리 로드/저장 - 연도 표기 수정 반영] ---
def load_book_data():
    if os.path.exists('books.csv'):
        try:
            df = pd.read_csv('books.csv')
            df['구입일'] = pd.to_datetime(df['구입일']).dt.date
            # 연도를 정수형으로 확실히 변환하여 .0 방지
            df['연도'] = pd.to_datetime(df['구입일']).dt.year.fillna(0).astype(int)
            df['별점'] = pd.to_numeric(df['별점'], errors='coerce').fillna(5).astype(int)
            return df
        except:
            return pd.DataFrame(columns=['제목', '저자', '가격', '구입일', '구입처', '분류', '별점', '코멘트', '연도'])
    return pd.DataFrame(columns=['제목', '저자', '가격', '구입일', '구입처', '분류', '별점', '코멘트', '연도'])

# --- [기존 저장 로직 - 절대 수정 금지] ---
def handle_save_asset(s_name, date_val, acc, amt_key):
    amt_val = st.session_state[amt_key]
    if amt_val <= 0: return
    df = load_data_safe(s_name)
    if df.empty:
        df = pd.DataFrame(columns=['date', 'account', 'amount', 'memo'])
    target_date = str(date_val).strip().upper()
    mask = (df['date'] == target_date) & (df['account'] == str(acc))
    if mask.any(): 
        df.loc[mask, 'amount'] = int(amt_val)
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
        if df_en.empty:
            df_en = pd.DataFrame(columns=['date', 'english', 'korean', 'memorized'])
        new_row = pd.DataFrame([{"date": str(datetime.date.today()), "english": en, "korean": ko, "memorized": False}])
        df_en = pd.concat([df_en, new_row], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=df_en)
        st.session_state.new_en = ""; st.session_state.new_ko = ""
        st.toast("✅ 문장 저장 완료!")

# --- [사이드바] ---
with st.sidebar:
    st.title("Byungjoo Pro v4.4")
    menu = st.radio("메뉴", ["💰 연금자산", "💵 개인자산", "🔤 영어공부", "📚 도서관리"])
    st.divider()
    ret_date = datetime.date(2028, 12, 31)
    st.metric("은퇴 D-Day", f"D-{(ret_date - datetime.date.today()).days}")

# --- [메인 로직 - 연금/개인자산/영어는 원본 유지] ---
if menu == "💰 연금자산":
    st.header("💰 연금자산 관리")
    df_p = load_data_safe("Data")
    t1, t2 = st.tabs(["📊 대시보드", "📝 입력"])
    with t1:
        if not df_p.empty and 'date' in df_p.columns:
            dates = sorted([str(d) for d in df_p['date'].unique()])
            if dates:
                recent = dates[-3:]
                df_r = df_p[df_p['date'].isin(recent)]
                m_total = df_r.groupby('date')['amount'].sum().reset_index().sort_values('date')
                cur = m_total.iloc[-1]['amount']
                prev = m_total.iloc[-2]['amount'] if len(m_total)>1 else cur
                diff = cur - prev
                c1, c2 = st.columns(2)
                c1.metric(f"{recent[-1]} 합계", f"{int(cur):,}원")
                c2.metric("전월 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
                fig = go.Figure()
                for acc in sorted(df_r['account'].unique()):
                    acc_df = df_r[df_r['account'] == acc]
                    fig.add_trace(go.Bar(x=acc_df['date'], y=acc_df['amount'], name=acc, hovertemplate="%{y:,.0f}원"))
                fig.update_layout(barmode='stack', xaxis_type='category', height=400)
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    with t2:
        st.subheader("📝 자산 데이터 입력")
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
                w_total = df_r.groupby('date')['amount'].sum().reset_index().sort_values('date')
                cur = w_total.iloc[-1]['amount']; prev = w_total.iloc[-2]['amount'] if len(w_total)>1 else cur
                diff = cur - prev
                c1, c2 = st.columns(2)
                c1.metric(f"{get_w(recent[-1])} 합계", f"{int(cur):,}원")
                c2.metric("전주 대비", f"{(diff/prev*100) if prev!=0 else 0:+.1f}%", f"{int(diff):+,}원")
                fig = go.Figure()
                for acc in sorted(df_r['account'].unique()):
                    acc_df = df_r[df_r['account'] == acc]
                    fig.add_trace(go.Bar(x=[get_w(d) for d in acc_df['date']], y=acc_df['amount'], name=acc, hovertemplate="%{y:,.0f}원"))
                fig.update_layout(barmode='stack', xaxis_type='category', height=400)
                st.plotly_chart(fig, use_container_width=True)
        else: st.info("데이터가 없습니다.")
    with t2:
        st.subheader("📝 개인자산 데이터 입력")
        c1, c2 = st.columns(2)
        pery = c1.selectbox("연도", [2026, 2027, 2028], key="per_y")
        perw = c2.number_input("주차", 1, 53, 14, key="per_w")
        p_acc_per = st.selectbox("계좌", ['KB증권', '삼성증권', '카카오', '한투증권', '현금/기타'])
        st.number_input("금액(원)", step=10000, key="per_amt")
        st.button("개인자산 저장", on_click=handle_save_asset, args=("PersonalData", f"Y{pery}W{perw}", p_acc_per, "per_amt"))

elif menu == "🔤 영어공부":
    st.header("🔤 Byungjoo의 영어 공부")
    df_en = load_data_safe("Sheet1")
    t1, t2, t3 = st.tabs(["📖 문장 리스트", "✍️ 문장 입력", "🧠 퀴즈"])
    with t1:
        if not df_en.empty and 'english' in df_en.columns:
            ed = st.data_editor(df_en[['date', 'english', 'korean', 'memorized']].iloc[::-1], use_container_width=True, key="en_ed")
            if st.button("암기 상태 저장"):
                df_en.update(ed); save_df = df_en.copy(); save_df['memorized'] = save_df['memorized'].astype(str).str.upper()
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=save_df)
                st.toast("✅ 저장 완료!"); st.rerun()
        else: st.warning("'Sheet1' 데이터를 찾을 수 없습니다.")
    with t2:
        st.subheader("✍️ 새 문장 추가")
        st.text_input("영어 문장", key="new_en")
        st.text_input("한글 뜻", key="new_ko")
        st.button("문장 저장", on_click=handle_save_english)
    with t3:
        if not df_en.empty and 'english' in df_en.columns:
            unmem = df_en[df_en['memorized'] == False]
            if not unmem.empty:
                if 'q_idx' not in st.session_state or st.session_state.q_idx not in unmem.index:
                    st.session_state.q_idx = unmem.sample(n=1).index[0]
                q = unmem.loc[st.session_state.q_idx]; st.info(f"뜻: {q['korean']}")
                ans = st.text_input("영어로 입력", key="q_in")
                if st.button("정답 확인"):
                    if ans.strip().lower() == str(q['english']).strip().lower(): st.success("정답!"); st.balloons()
                    else: st.error(f"오답! 정답: {q['english']}")
                def next_q(): 
                    if 'q_idx' in st.session_state: del st.session_state.q_idx
                st.button("다음 문제", on_click=next_q)
            else: st.success("🎉 완료!")

# --- [📚 도서관리 메뉴 - 4.4 업데이트] ---
elif menu == "📚 도서관리":
    st.header("📚 도서 관리 시스템")
    df_books = load_book_data()

    # (1) 상단 통계 UI - 연도 표기 .0 제거 및 명칭 변경
    st.subheader("📊 연도별 독서 현황")
    if not df_books.empty:
        c1, c2, c3 = st.columns([1, 1, 2])
        available_years = sorted(df_books['연도'].unique(), reverse=True)
        # 표시 형식을 '2026년'으로 변경
        sel_year_label = c1.selectbox("조회 연도 선택", options=[f"{y}년" for y in available_years], key="stat_year_sel")
        sel_year = int(sel_year_label.replace("년", ""))
        
        year_df = df_books[df_books['연도'] == sel_year]
        
        c2.metric(f"{sel_year}년 독서량", f"{len(year_df)} 권")
        c3.metric(f"{sel_year}년 도서 구입비", f"₩{int(year_df['가격'].sum()):,}")
        st.divider()

    tab1, tab2, tab3 = st.tabs(["📖 서재 보기 (리스트)", "➕ 신규 등록", "⚙️ 관리/수정/삭제"])

    with tab1: # 리스트 형식 + 넘버링 페이지네이션
        if not df_books.empty:
            # 최신 입력순 정렬 (인덱스 역순)
            d_view = df_books.iloc[::-1].copy()
            
            # 검색/필터
            f1, f2 = st.columns(2)
            y_f = f1.multiselect("연도 필터", options=[f"{y}년" for y in available_years])
            if y_f:
                y_f_ints = [int(y.replace("년", "")) for y in y_f]
                d_view = d_view[d_view['연도'].isin(y_f_ints)]
            
            # 페이지네이션 로직 (10개씩)
            items_per_page = 10
            total_pages = (len(d_view) // items_per_page) + (1 if len(d_view) % items_per_page > 0 else 0)
            
            if total_pages > 0:
                page = st.number_input("페이지", min_value=1, max_value=total_pages, step=1)
                start_idx = (page - 1) * items_per_page
                end_idx = start_idx + items_per_page
                
                # 표 형식으로 깔끔하게 표시
                st.table(d_view[['구입일', '제목', '저자', '분류', '별점', '가격']].iloc[start_idx:end_idx].assign(
                    별점=lambda x: x['별점'].map(lambda s: '⭐' * int(s))
                ))
                st.caption(f"총 {len(d_view)}권 중 {start_idx+1}-{min(end_idx, len(d_view))}권 표시 (전체 {total_pages}페이지)")
        else:
            st.info("데이터가 없습니다.")

    with tab2: # 신규 등록
        with st.form("book_reg_v4", clear_on_submit=True):
            col1, col2 = st.columns(2)
            b_t = col1.text_input("제목")
            b_a = col1.text_input("저자")
            b_p = col1.number_input("가격", step=1000)
            b_d = col2.date_input("구입일", datetime.date.today())
            b_c = col2.selectbox("분류", ["경제/경영", "자기계발", "에세이", "소설", "역사", "기타"])
            b_r = col2.slider("별점", 1, 5, 5)
            b_cmt = st.text_area("코멘트")
            if st.form_submit_button("서재에 추가"):
                if b_t:
                    new_b = {'제목': b_t, '저자': b_a, '가격': b_p, '구입일': b_d, '분류': b_c, '별점': int(b_r), '코멘트': b_cmt, '연도': b_d.year}
                    df_books = pd.concat([df_books, pd.DataFrame([new_b])], ignore_index=True)
                    df_books.to_csv('books.csv', index=False)
                    st.success(f"'{b_t}' 등록 완료!"); st.rerun()

    with tab3: # 관리/수정/삭제
        st.write("💡 표에서 내용을 수정하거나, 행을 선택한 후 `Delete` 키를 눌러 삭제할 수 있습니다.")
        # num_rows="dynamic" 옵션이 삭제/추가를 가능하게 함
        e_df = st.data_editor(df_books, num_rows="dynamic", use_container_width=True, key="book_editor_final")
        if st.button("💾 변경사항(수정/삭제) 최종 저장"):
            e_df['별점'] = pd.to_numeric(e_df['별점'], errors='coerce').fillna(5).astype(int)
            e_df.to_csv('books.csv', index=False)
            st.success("변경사항이 성공적으로 저장되었습니다!"); st.rerun()