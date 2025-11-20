import streamlit as st
import pandas as pd
import secrets
from supabase import create_client, Client

# --- 1. 설정 ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Secrets 설정이 필요합니다. Streamlit 대시보드에서 설정해주세요.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 2. 라우팅 (구매자 vs 공급사 구분) ---
query_params = st.query_params
access_token = query_params.get("access_token")

# ==========================================
# 🏭 공급사(Supplier) 화면 (비밀 링크 접속 시)
# ==========================================
if access_token:
    st.set_page_config(page_title="문서 제출 센터", page_icon="🏭")
    st.title("🏭 문서 제출 센터")
    
    # 1. 토큰으로 주문 정보 조회
    try:
        response = supabase.table("purchase_orders").select("*").eq("access_token", access_token).execute()
        
        if not response.data:
            st.error("⛔ 유효하지 않거나 만료된 링크입니다. 담당자에게 문의하세요.")
            st.stop()
            
        po_data = response.data[0]
        
        # 2. 정보 표시
        st.success(f"✅ 확인됨: {po_data['supplier_name']} (담당자용)")
        
        with st.container(border=True):
            st.markdown(f"""
            **요청 정보**
            - **발주번호:** `{po_data['po_number']}`
            - **품목명:** **{po_data['item_name']}**
            """)
            
            st.warning("📢 아래 버튼을 눌러 성적서(CoA) 파일을 업로드해주세요.")
            
            # 3. 파일 업로드
            uploaded_file = st.file_uploader("파일 선택 (PDF, 이미지)", type=['pdf', 'png', 'jpg', 'jpeg'])
            
            if uploaded_file:
                if st.button("📤 문서 제출하기 (클릭)", type="primary"):
                    with st.spinner("파일을 전송하고 있습니다..."):
                        # (1) Storage에 파일 저장
                        file_path = f"{po_data['po_number']}/{uploaded_file.name}"
                        file_body = uploaded_file.read()
                        
                        supabase.storage.from_("files").upload(
                            file_path, 
                            file_body, 
                            file_options={"content-type": uploaded_file.type, "upsert": "true"}
                        )
                        
                        # (2) DB 상태 업데이트
                        supabase.table("purchase_orders").update({
                            "status": "PENDING_APPROVAL"
                        }).eq("id", po_data['id']).execute()
                        
                        st.success("🎉 제출이 완료되었습니다! 창을 닫으셔도 됩니다.")
                        st.balloons()

    except Exception as e:
        st.error("시스템 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

# ==========================================
# 🧑‍💼 구매자(Admin) 화면 (기본 접속 시)
# ==========================================
else:
    st.set_page_config(page_title="PO-브릿지 Admin", page_icon="🌉")
    
    st.title("🌉 PO-브릿지 (Admin)")
    
    # --- [NEW] 사용 가이드 추가 ---
    with st.expander("ℹ️ 처음 오셨나요? 사용법 보기 (클릭)", expanded=True):
        st.markdown("""
        1. **발주 엑셀 업로드:** ERP에서 다운받은 엑셀 파일을 아래에 업로드하세요. (필수 컬럼: `발주번호`, `품목명`, `공급사명`)
        2. **DB 저장:** '🚀 DB 저장 & 링크 생성' 버튼을 누르세요.
        3. **링크 전달:** 아래 표에 생성된 **'공급사 접속 링크'**를 복사해서 공급사 담당자(카톡/메일)에게 보내세요.
        4. **자동 수취:** 공급사가 파일을 올리면 상태가 '승인 대기'로 바뀝니다.
        """)
    
    st.divider()

    st.subheader("1. 발주 엑셀 업로드")
    uploaded_file = st.file_uploader("ERP 엑셀 파일 (.xlsx)", type=['xlsx', 'xls'])
    
    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file)
            st.dataframe(df.head(3), hide_index=True)
            
            if st.button("🚀 DB 저장 & 링크 생성", type="primary"):
                pos_to_create = []
                for index, row in df.iterrows():
                    # 컬럼명 유연성 확보 (공백 제거 등)
                    row = {k.strip(): v for k, v in row.items()} # 컬럼명 공백 제거
                    
                    if '발주번호' in row:
                        po_data = {
                            "user_id": "admin", # 임시
                            "po_number": str(row['발주번호']),
                            "item_name": str(row.get('품목명', 'Unknown')),
                            "supplier_name": str(row.get('공급사명', 'Unknown')),
                            "status": "PENDING_UPLOAD",
                            "access_token": secrets.token_urlsafe(16)
                        }
                        pos_to_create.append(po_data)
                
                if pos_to_create:
                    supabase.table("purchase_orders").insert(pos_to_create).execute()
                    st.success(f"✅ {len(pos_to_create)}건의 발주서가 등록되었습니다! 아래 목록을 확인하세요.")
                else:
                    st.error("❌ 엑셀 파일에 '발주번호' 컬럼이 있는지 확인해주세요.")
        except Exception as e:
            st.error(f"파일 읽기 오류: {e}")

    st.divider()
    st.subheader("2. 발주 현황 및 공급사 링크")
    
    if st.button("🔄 목록 새로고침"):
        response = supabase.table("purchase_orders").select("*").order("id", desc=True).execute()
        if response.data:
            display_data = []
            # 현재 접속 중인 URL (로컬 vs 배포 환경 자동 감지)
            base_url = "https://po-bridge-wlmv3rkpgybe6d5u42ekvr.streamlit.app" # 대표님 배포 URL
            
            for item in response.data:
                # 비밀 링크 생성
                link = f"{base_url}/?access_token={item['access_token']}"
                item['공급사 접속 링크'] = link
                display_data.append(item)
                
            st.data_editor(
                display_data, 
                column_config={
                    "공급사 접속 링크": st.column_config.LinkColumn(
                        "공급사 전달용 링크 (복사하세요)", display_text="🔗 링크 열기"
                    ),
                    "access_token": None, # 토큰은 숨김
                    "user_id": None
                },
                hide_index=True
            )
        else:
            st.info("등록된 발주 건이 없습니다. 위에서 엑셀을 업로드해주세요.")