import streamlit as st
import pandas as pd
import secrets
from supabase import create_client, Client
import time

# --- 1. 설정 ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Secrets 설정 오류")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 2. 라우팅 및 세션 관리 ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

query_params = st.query_params
access_token = query_params.get("access_token")

# ==========================================
# [시나리오 A] 🏭 공급사 (로그인 불필요)
# ==========================================
if access_token:
    st.set_page_config(page_title="공급사 문서 제출", page_icon="🏭", layout="wide")
    
    # 토큰 검증 및 데이터 조회
    response = supabase.table("purchase_orders").select("*").eq("access_token", access_token).order("id").execute()
    
    if not response.data:
        st.error("⛔ 유효하지 않은 링크입니다.")
        st.stop()
    
    supplier_name = response.data[0]['supplier_name']
    st.title(f"🏭 {supplier_name} - 문서 제출 센터")
    
    # 품목 리스트 반복
    for item in response.data:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{item['item_name']}** | Lot: `{item['lot_no']}` | 수량: {item['quantity']}")
                st.caption(f"발주번호: {item['po_number']} | 규격: {item['spec']}")
            with col2:
                if item['status'] == 'DONE':
                    st.success("✅ 제출완료")
                else:
                    uploaded_file = st.file_uploader("파일", key=f"up_{item['id']}", label_visibility="collapsed")
                    if uploaded_file and st.button("제출", key=f"btn_{item['id']}"):
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
    st.set_page_config(page_title="PO-브릿지 Pro", page_icon="🌉")
    
    # --- 로그인 화면 (세션에 유저 없으면 표시) ---
    if not st.session_state['user']:
        st.title("🌉 PO-브릿지 로그인")
        
        tab1, tab2 = st.tabs(["로그인", "회원가입"])
        
        with tab1:
            email = st.text_input("이메일")
            password = st.text_input("비밀번호", type="password")
            if st.button("로그인하기", type="primary"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state['user'] = res.user
                    st.rerun()
                except Exception as e:
                    st.error(f"로그인 실패: 이메일/비번을 확인하세요. ({e})")

        with tab2:
            new_email = st.text_input("가입할 이메일")
            new_password = st.text_input("설정할 비밀번호", type="password")
            if st.button("가입하기"):
                try:
                    res = supabase.auth.sign_up({"email": new_email, "password": new_password})
                    st.success("가입 성공! 바로 로그인하세요.")
                except Exception as e:
                    st.error(f"가입 실패: {e}")
        st.stop() # 로그인 전에는 아래 코드 실행 안 함

    # --- 메인 대시보드 (로그인 성공 후) ---
    user_email = st.session_state['user'].email
    user_id = st.session_state['user'].id
    
    with st.sidebar:
        st.write(f"👤 **{user_email}**님")
        if st.button("로그아웃"):
            supabase.auth.sign_out()
            st.session_state['user'] = None
            st.rerun()

    st.title("🌉 PO-브릿지 (Admin)")
    
    uploaded_file = st.file_uploader("ERP 엑셀 업로드 (.xlsx)", type=['xlsx', 'xls'])
    
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        # (간소화된 로직: 실제 ERP 컬럼 매핑은 이전 코드 참조)
        if st.button("DB 저장 & 링크 생성"):
            grouped = df.groupby('구매거래처') # H열 기준 가정
            count = 0
            for supplier, group in grouped:
                token = secrets.token_urlsafe(16)
                batch = []
                for _, row in group.iterrows():
                    batch.append({
                        "user_id": user_id, # [핵심] 로그인한 내 아이디로 저장!
                        "po_number": str(row.get('발주번호', '')),
                        "supplier_name": str(supplier),
                        "item_name": str(row.get('품명', '')),
                        "lot_no": str(row.get('LotNo', '')),
                        "quantity": str(row.get('금회납품수량', '')),
                        "spec": str(row.get('규격', '')),
                        "status": "PENDING_UPLOAD",
                        "access_token": token
                    })
                supabase.table("purchase_orders").insert(batch).execute()
                count += 1
            st.success(f"{count}개 공급사 링크 생성 완료!")

    st.divider()
    st.subheader("내 발주 목록")
    
    # [핵심] 내 데이터만 조회 (.eq("user_id", user_id))
    if st.button("새로고침"):
        res = supabase.table("purchase_orders").select("*").eq("user_id", user_id).execute()
        if res.data:
            df_res = pd.DataFrame(res.data)
            # 중복 링크 제거 로직 등은 이전과 동일
            base_url = "https://po-bridge-wlmv3rkpgybe6d5u42ekvr.streamlit.app"
            
            # 보여주기용 데이터 가공
            display_list = []
            seen_tokens = set()
            for item in res.data:
                if item['access_token'] not in seen_tokens:
                    display_list.append({
                        "공급사": item['supplier_name'],
                        "링크": f"{base_url}/?access_token={item['access_token']}"
                    })
                    seen_tokens.add(item['access_token'])
            
            st.data_editor(display_list, column_config={"링크": st.column_config.LinkColumn("전송용 링크")})