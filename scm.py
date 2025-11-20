import streamlit as st
import pandas as pd
import secrets
from supabase import create_client, Client

# --- 1. 설정 ---
# (대표님의 실제 키값으로 유지하세요!)
SUPABASE_URL = "https://znziamdnzuboxqtsstwa.supabase.co"
SUPABASE_KEY = "sb_secret_ObqhLN-U8CIvfxwWyBvCuA_4-iG7sze"

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 2. 라우팅 (구매자 vs 공급사 구분) ---
# URL에 '?access_token=xyz'가 있으면 공급사 모드로 전환
query_params = st.query_params
access_token = query_params.get("access_token")

# ==========================================
# 🏭 공급사(Supplier) 화면
# ==========================================
if access_token:
    st.title("🏭 문서 제출 센터")
    
    # 1. 토큰으로 주문 정보 조회
    try:
        response = supabase.table("purchase_orders").select("*").eq("access_token", access_token).execute()
        
        if not response.data:
            st.error("⛔ 유효하지 않거나 만료된 링크입니다.")
            st.stop()
            
        po_data = response.data[0]
        
        # 2. 정보 표시
        st.info(f"발주번호: {po_data['po_number']} / 품목: {po_data['item_name']}")
        st.write(f"**{po_data['supplier_name']}** 담당자님, 요청된 문서를 업로드해주세요.")
        
        # 3. 파일 업로드
        uploaded_file = st.file_uploader("성적서(CoA) 파일 업로드 (PDF/IMG)", type=['pdf', 'png', 'jpg'])
        
        if uploaded_file:
            if st.button("📤 문서 제출하기"):
                with st.spinner("파일 전송 중..."):
                    # (1) Storage에 파일 저장
                    file_path = f"{po_data['po_number']}/{uploaded_file.name}"
                    file_body = uploaded_file.read()
                    
                    # 'files' 버킷에 업로드
                    supabase.storage.from_("files").upload(
                        file_path, 
                        file_body, 
                        file_options={"content-type": uploaded_file.type, "upsert": "true"}
                    )
                    
                    # (2) DB 상태 업데이트 (PENDING_APPROVAL 로 변경)
                    supabase.table("purchase_orders").update({
                        "status": "PENDING_APPROVAL"
                    }).eq("id", po_data['id']).execute()
                    
                    st.success("✅ 제출이 완료되었습니다! 담당자가 곧 확인합니다.")
                    st.balloons()
                    
    except Exception as e:
        st.error(f"오류 발생: {e}")

# ==========================================
# 🧑‍💼 구매자(Buyer) 화면
# ==========================================
else:
    st.title("🌉 PO-브릿지 (Admin)")
    st.markdown("### 1. 발주 엑셀 업로드")
    
    uploaded_file = st.file_uploader("ERP 엑셀 업로드", type=['xlsx', 'xls'])
    
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        st.dataframe(df.head(3))
        
        if st.button("🚀 DB 저장 & 링크 생성"):
            pos_to_create = []
            for index, row in df.iterrows():
                if '발주번호' in row:
                    po_data = {
                        "po_number": str(row['발주번호']),
                        "item_name": str(row.get('품목명', 'Unknown')),
                        "supplier_name": str(row.get('공급사명', 'Unknown')),
                        "status": "PENDING_UPLOAD",
                        "access_token": secrets.token_urlsafe(16)
                    }
                    pos_to_create.append(po_data)
            
            if pos_to_create:
                supabase.table("purchase_orders").insert(pos_to_create).execute()
                st.success(f"{len(pos_to_create)}건 저장 완료!")

    st.divider()
    st.markdown("### 2. 발주 현황 및 공급사 링크")
    
    # 목록 새로고침
    if st.button("🔄 목록 새로고침"):
        response = supabase.table("purchase_orders").select("*").order("id", desc=True).execute()
        if response.data:
            # 데이터 가공: 비밀 링크 생성
            display_data = []
            for item in response.data:
                # 로컬 테스트용 링크 생성
                link = f"http://localhost:8501/?access_token={item['access_token']}"
                item['secret_link'] = link # 화면에 링크 표시
                display_data.append(item)
                
            st.data_editor(
                display_data, 
                column_config={
                    "secret_link": st.column_config.LinkColumn("공급사 접속 링크")
                }
            )
        else:
            st.info("데이터가 없습니다.")