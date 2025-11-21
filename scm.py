import streamlit as st
import pandas as pd
import secrets
from supabase import create_client, Client
import time

# --- 1. Supabase 설정 ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Secrets 설정 오류: Streamlit 대시보드에서 Supabase 키를 설정해주세요.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 2. 디자인 시스템 (CSS 주입) ---
def inject_custom_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
        
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --secondary: #475569;
            --bg-color: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-main: #1e293b;
            --text-sub: #64748b;
            --success: #10b981;
        }

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: var(--text-main);
            background-color: var(--bg-color);
        }

        /* Card Style */
        div[data-testid="stVerticalBlock"] > div[style*="background-color"] {
             background-color: var(--card-bg);
             border-radius: 12px;
             border: 1px solid #e2e8f0;
             box-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1);
        }

        /* Buttons */
        .stButton > button {
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.2s;
        }
        
        div[data-testid="stButton"] > button[kind="primary"] {
            background-color: var(--primary);
            border-color: var(--primary);
        }
        div[data-testid="stButton"] > button[kind="primary"]:hover {
            background-color: var(--primary-dark);
            border-color: var(--primary-dark);
        }

        /* Status Badge */
        .status-badge {
            display: inline-flex;
            align-items: center;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .status-done {
            background-color: #dcfce7;
            color: #166534;
        }
        .status-pending {
            background-color: #f1f5f9;
            color: #475569;
        }
    </style>
    """, unsafe_allow_html=True)

# --- 3. 라우팅 및 세션 관리 ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

query_params = st.query_params
access_token = query_params.get("access_token")

# ==========================================
# [시나리오 A] 🏭 공급사 (로그인 불필요)
# ==========================================
if access_token:
    st.set_page_config(page_title="공급사 문서 제출", page_icon="🏭", layout="centered")
    inject_custom_css()
    
    # 토큰 검증
    response = supabase.table("purchase_orders").select("*").eq("access_token", access_token).order("id").execute()
    
    if not response.data:
        st.error("⛔ 유효하지 않은 링크입니다.")
        st.stop()
    
    supplier_name = response.data[0]['supplier_name']
    
    # Header
    with st.container():
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 2rem;">
            <div style="font-size: 3rem;">🏭</div>
            <h1 style="margin-top: 0.5rem;">문서 제출 센터</h1>
            <p style="color: var(--text-sub); font-size: 1.1rem;">{supplier_name} 귀하</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 품목 리스트 반복
    for item in response.data:
        with st.container(border=True):
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 1rem;">
                <div>
                    <h3 style="margin: 0; color: var(--text-main);">{item['item_name']}</h3>
                    <p style="margin: 0; color: var(--text-sub); font-size: 0.9rem;">Lot: {item['lot_no']}</p>
                </div>
                <span class="status-badge {'status-done' if item['status'] == 'DONE' else 'status-pending'}">
                    {'제출완료' if item['status'] == 'DONE' else '대기중'}
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([2, 1])
            with col1:
                 st.markdown(f"""
                 <div style="font-size: 0.9rem; color: var(--text-sub); margin-bottom: 0.5rem;">
                    <div><strong>발주번호:</strong> {item['po_number']}</div>
                    <div><strong>수량:</strong> {item['quantity']} | <strong>규격:</strong> {item['spec']}</div>
                 </div>
                 """, unsafe_allow_html=True)
            
            with col2:
                if item['status'] == 'DONE':
                    st.markdown('<div style="text-align: right; color: var(--success); font-weight:bold;">✅ 저장됨</div>', unsafe_allow_html=True)
                else:
                    uploaded_file = st.file_uploader("파일 업로드", key=f"up_{item['id']}", label_visibility="collapsed")
                    if uploaded_file:
                        if st.button("제출하기", key=f"btn_{item['id']}", type="primary", use_container_width=True):
                            with st.spinner("전송 중..."):
                                file_path = f"{supplier_name}/{item['lot_no']}_{uploaded_file.name}"
                                supabase.storage.from_("files").upload(file_path, uploaded_file.read(), file_options={"upsert": "true"})
                                supabase.table("purchase_orders").update({
                                    "status": "DONE", "file_url": file_path, "file_name": uploaded_file.name
                                }).eq("id", item['id']).execute()
                                st.rerun()

# ==========================================
# [시나리오 B] 🧑‍💼 구매자 (로그인 필수!)
# ==========================================
else:
    st.set_page_config(page_title="PO-브릿지 Pro", page_icon="🌉", layout="wide")
    inject_custom_css()
    
    # --- 로그인 화면 ---
    if not st.session_state['user']:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            with st.container(border=True):
                st.markdown("""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <h2 style="color: var(--primary);">PO-브릿지</h2>
                    <p style="color: var(--text-sub);">Enterprise SCM Dashboard</p>
                </div>
                """, unsafe_allow_html=True)
                
                tab1, tab2 = st.tabs(["로그인", "회원가입"])
                
                with tab1:
                    email = st.text_input("이메일", key="login_email")
                    password = st.text_input("비밀번호", type="password", key="login_pw")
                    if st.button("로그인하기", type="primary", use_container_width=True):
                        try:
                            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                            st.session_state['user'] = res.user
                            st.rerun()
                        except Exception as e:
                            st.error("로그인 실패: 이메일/비밀번호를 확인하세요.")

                with tab2:
                    new_email = st.text_input("가입할 이메일", key="signup_email")
                    new_password = st.text_input("설정할 비밀번호", type="password", key="signup_pw")
                    if st.button("가입하기", use_container_width=True):
                        if not new_email or not new_password:
                            st.warning("이메일과 비밀번호를 입력해주세요.")
                        else:
                            try:
                                res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                                st.success("🎉 가입 성공! '로그인' 탭에서 로그인하세요.")
                            except Exception as e:
                                st.error(f"가입 실패: {e}")
        st.stop()

    # --- 메인 대시보드 ---
    user_email = st.session_state['user'].email
    user_id = st.session_state['user'].id
    
    with st.sidebar:
        st.write(f"👤 **{user_email}**")
        if st.button("로그아웃", use_container_width=True):
            supabase.auth.sign_out()
            st.session_state['user'] = None
            st.rerun()

    st.title("Dashboard")
    
    # 내 데이터 조회
    res = supabase.table("purchase_orders").select("*").eq("user_id", user_id).execute()
    df_res = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    # Metrics
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("총 발주 품목", len(df_res) if not df_res.empty else 0)
    with m2:
        completed = len(df_res[df_res['status'] == 'DONE']) if not df_res.empty else 0
        st.metric("제출 완료", completed)
    with m3:
        pending = len(df_res[df_res['status'] != 'DONE']) if not df_res.empty else 0
        st.metric("미제출", pending, delta_color="inverse")
    
    st.divider()
    
    # Upload Section
    with st.expander("📤 신규 발주 엑셀 업로드 (Click)", expanded=False):
        uploaded_file = st.file_uploader("ERP 엑셀 업로드 (.xlsx)", type=['xlsx', 'xls'])
        if uploaded_file:
            # [핵심 수정] header=1 옵션으로 첫 줄(제목) 무시하고 두 번째 줄부터 읽기
            df = pd.read_excel(uploaded_file, header=1)
            
            # [핵심 수정] '구매거래처'가 비어있는 행(Total 행 등) 제거
            if '구매거래처' in df.columns:
                df = df.dropna(subset=['구매거래처'])
            
            # [추가] 품목코드 숨김 처리
            cols_to_hide = ['item_code', '품목코드']
            df_preview = df.drop(columns=[c for c in cols_to_hide if c in df.columns])
            
            st.write("👇 데이터 미리보기 (상위 3개)")
            st.dataframe(df_preview.head(3))
            
            if st.button("DB 저장 & 링크 생성", type="primary"):
                try:
                    grouped = df.groupby('구매거래처')
                    count = 0
                    for supplier, group in grouped:
                        token = secrets.token_urlsafe(16)
                        batch = []
                        for _, row in group.iterrows():
                            row = row.fillna('')
                            batch.append({
                                "user_id": user_id,
                                "po_number": str(row.get('발주번호', '')),
                                "supplier_name": str(supplier),
                                "item_name": str(row.get('품명', '')),
                                "lot_no": str(row.get('LotNo', '')),
                                "quantity": str(row.get('금회납품수량', '')),
                                "spec": str(row.get('규격', '')),
                                "manufacturer": str(row.get('제조사', '')), # [추가] 제조사 매핑
                                "status": "PENDING_UPLOAD",
                                "access_token": token
                            })
                        if batch:
                            supabase.table("purchase_orders").insert(batch).execute()
                            count += 1
                    st.success(f"✅ {count}개 공급사용 링크 생성 완료!")
                    time.sleep(1)
                    st.rerun()
                except KeyError as e:
                    st.error(f"엑셀 컬럼명을 찾을 수 없습니다: {e}. '구매거래처', '발주번호' 컬럼이 있는지 확인하세요.")

    # Data Table Section
    st.subheader("발주 및 링크 현황")
    
    if not df_res.empty:
        col_filter, _ = st.columns([1, 3])
        with col_filter:
            status_filter = st.selectbox("상태 보기", ["전체", "제출완료", "미제출"])
        
        if status_filter == "제출완료":
            df_display = df_res[df_res['status'] == 'DONE']
        elif status_filter == "미제출":
            df_display = df_res[df_res['status'] != 'DONE']
        else:
            df_display = df_res
            
        base_url = "https://po-bridge-wlmv3rkpgybe6d5u42ekvr.streamlit.app"
        df_display['link'] = df_display['access_token'].apply(lambda x: f"{base_url}/?access_token={x}")
        
        # [수정] 편집 가능한 데이터 에디터 설정
        # ID를 포함하여 데이터프레임 준비 (ID는 숨김)
        df_editor = df_display.copy()
        
        changes = st.data_editor(
            df_editor,
            column_config={
                "id": None, # ID 숨김
                "user_id": None, # 사용자 ID 숨김
                "access_token": None, # 토큰 숨김
                "created_at": None, # 생성일 숨김
                "file_url": None, # 파일 URL 숨김
                "file_name": None, # 파일명 숨김
                "supplier_name": "공급사",
                "po_number": "발주번호",
                "item_name": "품명",
                "lot_no": "Lot No",
                "quantity": "수량",
                "spec": "규격",
                "manufacturer": "제조사", # [추가] 제조사 표시
                "status": st.column_config.SelectboxColumn("상태", options=["PENDING_UPLOAD", "DONE"]),
                "link": st.column_config.LinkColumn("공급사 전달용 링크", display_text="🔗 링크 복사")
            },
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic", # 행 추가/삭제 허용
            key="data_editor"
        )

        # 변경사항 저장 버튼
        if st.button("💾 변경사항 저장", type="primary"):
            try:
                # 1. 삭제된 행 처리
                for index in changes['deleted_rows']:
                    # 원본 데이터프레임에서 해당 인덱스의 ID를 찾음
                    # 주의: Streamlit의 deleted_rows 인덱스는 편집 전 원본 데이터프레임 기준
                    row_id = df_editor.iloc[index]['id']
                    supabase.table("purchase_orders").delete().eq("id", row_id).execute()

                # 2. 수정된 행 처리
                for index, updates in changes['edited_rows'].items():
                    row_id = df_editor.iloc[index]['id']
                    supabase.table("purchase_orders").update(updates).eq("id", row_id).execute()
                
                st.success("✅ 변경사항이 저장되었습니다!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"저장 중 오류 발생: {e}")
    else:
        st.info("등록된 발주 내역이 없습니다. 위에서 엑셀을 업로드해주세요.")