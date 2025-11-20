import streamlit as st
import pandas as pd
import secrets
from supabase import create_client, Client

# --- 1. 설정 ---
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except:
    st.error("Secrets 설정이 필요합니다.")
    st.stop()

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

# --- 2. 라우팅 ---
query_params = st.query_params
access_token = query_params.get("access_token")

# ==========================================
# 🏭 공급사(Supplier) 화면 (통합 링크 접속)
# ==========================================
if access_token:
    st.set_page_config(page_title="공급사 문서 제출", page_icon="🏭", layout="wide")
    
    # 1. 토큰으로 해당 공급사의 '제출 대기' 품목 전체 조회
    response = supabase.table("purchase_orders").select("*").eq("access_token", access_token).order("id").execute()
    
    if not response.data:
        st.error("⛔ 유효하지 않은 링크이거나, 이미 처리가 완료된 건입니다.")
        st.stop()
    
    # 공급사명 추출 (첫 번째 데이터 기준)
    supplier_name = response.data[0]['supplier_name']
    st.title(f"🏭 {supplier_name} - 품질 문서 제출 센터")
    st.info(f"총 {len(response.data)}건의 품목에 대한 성적서(CoA)를 업로드해주세요.")

    # 2. 품목 리스트 및 업로드 (반복문)
    for item in response.data:
        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # ERP 상세 정보 표시
                st.markdown(f"### 📦 **{item['item_name']}** ({item['spec']})")
                st.caption(f"Lot No: **{item['lot_no']}** | 수량: {item['quantity']} | 발주번호: {item['po_number']}")
            
            with col2:
                # 상태에 따른 표시
                if item['status'] == 'DONE':
                    st.success(f"✅ 제출 완료 ({item['file_name']})")
                else:
                    # 파일 업로더 (Key를 유니크하게 설정)
                    uploaded_file = st.file_uploader("성적서 업로드", type=['pdf', 'png', 'jpg'], key=f"up_{item['id']}")
                    
                    if uploaded_file:
                        if st.button("제출", key=f"btn_{item['id']}", type="primary"):
                            # (1) 스토리지 저장
                            file_path = f"{supplier_name}/{item['lot_no']}_{uploaded_file.name}"
                            file_body = uploaded_file.read()
                            supabase.storage.from_("files").upload(file_path, file_body, file_options={"content-type": uploaded_file.type, "upsert": "true"})
                            
                            # (2) DB 업데이트 (상태 완료 처리)
                            supabase.table("purchase_orders").update({
                                "status": "DONE",
                                "file_url": file_path,
                                "file_name": uploaded_file.name
                            }).eq("id", item['id']).execute()
                            
                            st.rerun() # 화면 새로고침

# ==========================================
# 🧑‍💼 구매자(Admin) 화면
# ==========================================
else:
    st.set_page_config(page_title="PO-브릿지 Pro", page_icon="🌉", layout="wide")
    st.title("🌉 PO-브릿지 (ERP 연동 버전)")
    
    with st.expander("ℹ️ 사용 가이드", expanded=True):
        st.markdown("ERP에서 다운받은 **'납품품목조회' 엑셀 파일**을 그대로 업로드하세요.")

    uploaded_file = st.file_uploader("ERP 엑셀 파일 업로드 (.xlsx)", type=['xlsx', 'xls'])
    
    if uploaded_file:
        try:
            # ERP 엑셀 읽기 (헤더가 복잡할 수 있으므로 첫 줄을 컬럼으로 인식)
            df = pd.read_excel(uploaded_file)
            
            # [핵심] ERP 컬럼 매핑 확인
            required_cols = ['발주번호', '구매거래처', '품명'] # 필수라고 생각되는 최소한의 컬럼
            # 실제 데이터 프레임의 컬럼명 리스트
            df_cols = df.columns.tolist()
            
            # 매핑 로직: 컬럼명이 정확히 일치해야 함 (사용자가 준 정보 기준)
            # G:발주번호, H:구매거래처, O:품명, C:LotNo, N:규격, R:금회납품수량
            
            st.write("👇 업로드된 데이터 미리보기")
            st.dataframe(df.head(3))
            
            if st.button("🚀 공급사별 통합 링크 생성", type="primary"):
                
                # 공급사별로 그룹화 (Grouping)
                grouped = df.groupby('구매거래처')
                
                total_count = 0
                supplier_count = 0
                
                progress_text = "데이터 처리 중..."
                my_bar = st.progress(0, text=progress_text)
                
                for supplier, group_df in grouped:
                    # 공급사별 고유 토큰 생성 (이 토큰 하나로 여러 품목 관리)
                    token = secrets.token_urlsafe(16)
                    
                    batch_data = []
                    for idx, row in group_df.iterrows():
                        # NaN 값 처리
                        row = row.fillna('')
                        
                        po_data = {
                            "user_id": "admin",
                            "po_number": str(row.get('발주번호', '')),
                            "supplier_name": str(supplier),
                            "item_name": str(row.get('품명', '')),
                            "item_code": str(row.get('품번', '')),
                            "spec": str(row.get('규격', '')),
                            "lot_no": str(row.get('LotNo', '')),
                            "quantity": str(row.get('금회납품수량', '')),
                            "manufacturer": str(row.get('제조사', '')),
                            "status": "PENDING_UPLOAD",
                            "access_token": token # 같은 공급사는 같은 토큰 공유!
                        }
                        batch_data.append(po_data)
                    
                    # DB 저장
                    if batch_data:
                        supabase.table("purchase_orders").insert(batch_data).execute()
                        total_count += len(batch_data)
                        supplier_count += 1
                
                my_bar.progress(100, text="완료!")
                st.success(f"총 {supplier_count}개 공급사, {total_count}개 품목 등록 완료!")
                
        except Exception as e:
            st.error(f"오류 발생: {e}")

    st.divider()
    st.subheader("📨 공급사별 링크 발송")
    
    if st.button("🔄 링크 목록 새로고침"):
        # 공급사별로 하나씩만 가져오기 (Distinct)
        # Supabase SQL로 distinct가 까다로우니, 전체를 가져와서 파이썬에서 중복 제거
        response = supabase.table("purchase_orders").select("supplier_name, access_token, created_at").order("created_at", desc=True).execute()
        
        if response.data:
            # 중복 제거 (최신 생성된 토큰 기준)
            df_links = pd.DataFrame(response.data)
            df_unique = df_links.drop_duplicates(subset=['supplier_name', 'access_token'])
            
            base_url = "https://po-bridge-wlmv3rkpgybe6d5u42ekvr.streamlit.app"
            
            display_list = []
            for index, row in df_unique.iterrows():
                link = f"{base_url}/?access_token={row['access_token']}"
                display_list.append({
                    "공급사명": row['supplier_name'],
                    "생성일시": row['created_at'][:10],
                    "전용 링크": link
                })
            
            st.data_editor(
                display_list,
                column_config={
                    "전용 링크": st.column_config.LinkColumn(
                        "전달용 링크", display_text="🔗 링크 복사"
                    )
                },
                hide_index=True
            )