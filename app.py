import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date, timedelta
import time 
import numpy as np 
import plotly.express as px
import json
from openpyxl import load_workbook 
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

# =============================================================================
# 0. KHỞI TẠO CẤU HÌNH BẢO MẬT (V7.33.5 - SECRETS ONLY)
# =============================================================================
AI_CLIENT_STATUS = False
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

try:
    if 'OPENAI_API_KEY' in st.secrets:
        api_key = st.secrets['OPENAI_API_KEY']
        os.environ["OPENAI_API_KEY"] = api_key
        AI_CLIENT_STATUS = True
    else:
        AI_ERROR = "⚠️ Thiếu OPENAI_API_KEY trong Secrets."

    if 'USER_ACCOUNTS' in st.secrets:
        USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    else:
        USER_CREDENTIALS = {"admin": "123456"}
        AI_ERROR = "⚠️ Thiếu USER_ACCOUNTS trong Secrets."
except Exception as e:
    AI_ERROR = f"❌ Lỗi cấu hình Secrets: {e}"

# =============================================================================
# 1. GIAO DIỆN ĐĂNG NHẬP
# =============================================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.set_page_config(page_title="Đăng nhập | 3M-Gus CRM", page_icon="🔐")
    st.markdown("""
    <style>
    .stApp { background-color: #FAFAFA !important; }
    div[data-testid="stForm"] { background-color: #ffffff; border-radius: 15px; border: 1px solid #D35400; padding: 30px; }
    </style>
    """, unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center; border: none; color: #D35400;'>3M-Gus CRM</h1>", unsafe_allow_html=True)
        if AI_ERROR: st.warning(AI_ERROR)
        with st.form("login_form"):
            u = st.text_input("👤 Tên đăng nhập")
            p = st.text_input("🔑 Mật khẩu", type="password")
            if st.form_submit_button("ĐĂNG NHẬP", type="primary", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"name": u, "username": u, "role": "admin" if u == "admin" else "sale"}
                    st.rerun()
                else:
                    st.error("❌ Sai tài khoản hoặc mật khẩu!")
    st.stop()

# =============================================================================
# 2. CẤU HÌNH GIAO DIỆN CHÍNH & CSS CHI TIẾT
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM", page_icon="💎", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .stApp { background-color: #FAFAFA !important; color: #000000 !important; }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; min-width: 300px !important; }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    h1 { color: #D35400 !important; border-bottom: 3px solid #D35400; font-weight: bold; }
    .stMetric { background-color: #ffffff; border-left: 5px solid #D35400; padding: 15px; border-radius: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
    div[data-testid="stDataFrame"] { background-color: #FFFFFF !important; border: 1px solid #ddd; border-radius: 10px; }
    .st-emotion-cache-1kyxreq { color: #000000 !important; } /* Fix text color in main area */
</style>
""", unsafe_allow_html=True)

# --- CONFIG OPTIONS ---
STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]
MENU_VIDEO = {
    "🎬 LINK NIỀM TIN": "https://youtu.be/PoUWP--0CDU",
    "🎬 LINK IUL": "https://youtu.be/DWrgVeBCAIw",
    "🎬 LINK BỒI THƯỜNG": "https://youtu.com/ZXi79hgbLW0",
    "🎬 LINK REVIEW KH": "https://youtu.com/3KWj3A4S-RA"
}

# =============================================================================
# 3. HÀM XỬ LÝ DỮ LIỆU CHUYÊN SÂU
# =============================================================================

def clean_phone(phone_str):
    return re.sub(r'[^0-9]+', '', str(phone_str)) if pd.notna(phone_str) else None

@retry(wait=wait_random_exponential(min=4, max=30), stop=stop_after_attempt(5))
def call_gpt_analysis(note_content, current_status):
    if not AI_CLIENT_STATUS: return {"PHAN_TICH_TAM_LY": "AI Tắt", "GOI_Y_HANH_DONG": "N/A", "NOI_DUNG_TU_VAN": "N/A"}
    system_prompt = f"Bạn là trợ lý AI chuyên nghiệp tên GUS. Nhiệm vụ: Phân tích NOTE khách hàng ngành bảo hiểm (IUL/Annuity) tại Mỹ. Trả về JSON: PHAN_TICH_TAM_LY, GOI_Y_HANH_DONG, NOI_DUNG_TU_VAN. Trạng thái hiện tại: {current_status}"
    response = completion(model=AI_MODEL, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Nội dung Note: {note_content}"}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def save_dataframe_changes(df_to_save):
    # Dọn dẹp cột trước khi lưu vào State
    cols_to_remove = ["CALL_LINK", "CLEAN_PHONE", "ID", "EDIT", "Cellphone_Link", "Số Tiệm_Link", "CLEAN_SHOP_PHONE", "STATUS_SHORT", "TAM_LY_SHORT", "VIDEO_GUIDE"]
    df_clean = df_to_save.copy()
    if 'LAST_CONTACT_DATE' in df_clean.columns:
         df_clean['LAST_CONTACT_DATE'] = pd.to_datetime(df_clean['LAST_CONTACT_DATE'], errors='coerce').dt.date
    df_clean = df_clean.drop(columns=[col for col in cols_to_remove if col in df_clean.columns], errors='ignore')
    st.session_state.original_df = df_clean.copy()
    st.toast("✅ Đã lưu dữ liệu thành công!", icon="💾")

def load_data():
    if 'original_df' in st.session_state:
        return st.session_state.original_df
    # Nếu chưa có dữ liệu, trả về khung trống chuẩn
    return pd.DataFrame(columns=['NAME', 'Cellphone', 'Số Tiệm', 'NOTE', 'Status', 'ASSIGNED', 'LAST_CONTACT_DATE', 'PHÂN TÍCH TÂM LÝ (GUS)', 'GỢI Ý HÀNH ĐỘNG (GUS)', 'NỘI DUNG TƯ VẤN (COPY)'])

# =============================================================================
# 4. GIAO DIỆN CHÍNH (MAIN APP)
# =============================================================================

def main_app():
    user = st.session_state.user_info
    
    # Khởi tạo dữ liệu lần đầu
    if 'edited_df' not in st.session_state or st.session_state.edited_df.empty:
        st.session_state.edited_df = load_data()

    # --- SIDEBAR NAVIGATION ---
    with st.sidebar:
        st.markdown(f"<h2 style='text-align: center;'>👤 {user['name']}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: center;'>Quyền hạn: <b>{user['role'].upper()}</b></p>", unsafe_allow_html=True)
        st.markdown("---")
        menu = st.radio("ĐIỀU HƯỚNG HỆ THỐNG", ["📊 Dashboard Tổng Quan", "📇 Pipeline Khách Hàng", "📥 Import & AI Phân Tích"])
        
        st.markdown("---")
        if menu == "📇 Pipeline Khách Hàng":
            st.subheader("▶️ VIDEO TÀI LIỆU")
            for name, url in MENU_VIDEO.items():
                st.link_button(name, url, use_container_width=True, type="primary")
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("🚪 Đăng Xuất Hệ Thống", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    # --- TAB 1: DASHBOARD ---
    if menu == "📊 Dashboard Tổng Quan":
        st.title("📈 3M-GUS BUSINESS INSIGHTS")
        df = st.session_state.edited_df
        
        if df.empty:
            st.info("👋 Chào mừng Sếp Gus! Hiện tại chưa có dữ liệu. Vui lòng vào mục Import để nạp file Excel khách hàng.")
        else:
            # Hàng chỉ số KPI
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng Leads", len(df))
            c2.metric("Hot (85%) 🔥", len(df[df['Status'] == "Hot Interest (85%)"]))
            c3.metric("Chốt Đơn ✅", len(df[df['Status'] == "Done (100%)"]))
            c4.metric("Follow Up 📞", len(df[df['Status'] == "Follow Up (50%)"]))
            
            st.markdown("---")
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                status_counts = df['Status'].value_counts().reset_index()
                fig_pie = px.pie(status_counts, values='count', names='Status', title='Phân bổ Pipeline (%)', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with col_chart2:
                # Bảng xếp hạng Sale
                st.subheader("🏅 Bảng Xếp Hạng Sale")
                if 'ASSIGNED' in df.columns:
                    rank = df.groupby('ASSIGNED').size().reset_index(name='Số Leads').sort_values(by='Số Leads', ascending=False)
                    st.table(rank)

    # --- TAB 2: PIPELINE KHÁCH HÀNG ---
    elif menu == "📇 Pipeline Khách Hàng":
        st.title("📇 QUẢN LÝ PIPELINE CHI TIẾT")
        df = st.session_state.edited_df
        
        if df.empty:
            st.warning("⚠️ Dữ liệu Pipeline đang trống.")
        else:
            # Bộ lọc tìm kiếm
            col_s1, col_s2 = st.columns([3, 1])
            with col_s1:
                search = st.text_input("🔍 Tìm kiếm theo Tên hoặc Số điện thoại...", "")
            with col_s2:
                filter_status = st.selectbox("Lọc theo trạng thái", ["Tất cả"] + STATUS_OPTIONS)

            # Áp dụng lọc
            if search:
                df = df[df.apply(lambda row: search.lower() in str(row).lower(), axis=1)]
            if filter_status != "Tất cả":
                df = df[df['Status'] == filter_status]

            # Chế độ View/Edit
            st.markdown("---")
            edit_mode = st.toggle("🟢 Kích hoạt chế độ Chỉnh sửa & Cập nhật Note")

            if edit_mode:
                st.caption("💡 Mẹo: Sếp có thể sửa trực tiếp trên bảng và nhấn nút Lưu phía dưới.")
                edited_df = st.data_editor(
                    df, 
                    use_container_width=True, 
                    height=500, 
                    num_rows="dynamic",
                    column_config={
                        "Status": st.column_config.SelectboxColumn("Trạng thái", options=STATUS_OPTIONS, required=True),
                        "NOTE": st.column_config.TextColumn("Ghi chú Sale", width="large")
                    }
                )
                if st.button("💾 XÁC NHẬN LƯU THAY ĐỔI", type="primary"):
                    save_dataframe_changes(edited_df)
                    st.rerun()
            else:
                # Hiển thị bảng dạng View sắc nét
                st.dataframe(df, use_container_width=True, height=500)
                
                # --- KHU VỰC GỌI ĐIỆN & AI INSIGHT ---
                st.markdown("---")
                st.subheader("🧠 TRUNG TÂM ĐIỀU HÀNH AI & CALL")
                
                sel_name = st.selectbox("Chọn khách hàng để xem phân tích AI & Gọi điện nhanh", ["-- Click để chọn khách hàng --"] + df['NAME'].tolist())
                
                if sel_name != "-- Click để chọn khách hàng --":
                    row = df[df['NAME'] == sel_name].iloc[0]
                    col_info, col_call = st.columns([2, 1])
                    
                    with col_info:
                        st.markdown(f"### Khách hàng: {row['NAME']}")
                        st.markdown(f"**🤖 Tâm lý khách hàng (AI):** {row.get('PHÂN TÍCH TÂM LÝ (GUS)', 'Chưa có dữ liệu')}")
                        st.markdown(f"**🎯 Chiến thuật gợi ý:** {row.get('GỢI Ý HÀNH ĐỘNG (GUS)', 'Chưa có dữ liệu')}")
                        st.success(f"**📝 Kịch bản Copy:** {row.get('NỘI DUNG TƯ VẤN (COPY)', 'N/A')}")
                    
                    with col_call:
                        phone = clean_phone(row['Cellphone'])
                        if phone:
                            st.markdown(f"""
                            <a href="tel:+1{phone}">
                                <div style="background-color:#2ecc71; color:white; padding:20px; text-align:center; border-radius:15px; cursor:pointer; font-weight:bold; font-size:20px;">
                                    📞 GỌI KHÁCH HÀNG<br>{row['Cellphone']}
                                </div>
                            </a>
                            """, unsafe_allow_html=True)
                        
                        shop_phone = clean_phone(row.get('Số Tiệm'))
                        if shop_phone:
                            st.markdown(f"""
                            <br><a href="tel:+1{shop_phone}">
                                <div style="background-color:#3498db; color:white; padding:15px; text-align:center; border-radius:15px; cursor:pointer; font-weight:bold;">
                                    📞 GỌI TIỆM: {row['Số Tiệm']}
                                </div>
                            </a>
                            """, unsafe_allow_html=True)

    # --- TAB 3: IMPORT & AI ---
    elif menu == "📥 Import & AI Phân Tích":
        st.title("📥 NẠP DATA & KÍCH HOẠT TRỢ LÝ AI")
        st.info("Sếp hãy tải file Excel (.xlsx) chứa danh sách khách hàng mới lên đây. Hệ thống sẽ tự động lọc trùng và dùng AI phân tích Note.")
        
        up = st.file_uploader("Chọn file Excel Pipeline", type=['xlsx'])
        
        if up:
            temp_df = pd.read_excel(up)
            st.write("Preview dữ liệu nạp vào:")
            st.dataframe(temp_df.head(5))
            
            if st.button("🚀 BẮT ĐẦU IMPORT & CHẠY AI (FULL PROCESS)", type="primary"):
                with st.status("🛠️ Đang xử lý dữ liệu chuyên sâu...") as s:
                    st.write("1. Đang chuẩn hóa số điện thoại...")
                    temp_df['Cellphone'] = temp_df['Cellphone'].astype(str)
                    
                    st.write("2. Đang kết nối trợ lý AI GUS...")
                    # Chạy AI cho từng Note
                    for idx, row in temp_df.iterrows():
                        note = str(row.get('NOTE', '')).strip()
                        if note and len(note) > 5:
                            try:
                                ai_res = call_gpt_analysis(note, row.get('Status', 'Mới'))
                                temp_df.at[idx, 'PHÂN TÍCH TÂM LÝ (GUS)'] = ai_res.get('PHAN_TICH_TAM_LY', 'N/A')
                                temp_df.at[idx, 'GỢI Ý HÀNH ĐỘNG (GUS)'] = ai_res.get('GOI_Y_HANH_DONG', 'N/A')
                                temp_df.at[idx, 'NỘI DUNG TƯ VẤN (COPY)'] = ai_res.get('NOI_DUNG_TU_VAN', 'N/A')
                            except:
                                pass
                    
                    st.write("3. Đang chống trùng lặp và lưu hệ thống...")
                    save_dataframe_changes(temp_df)
                    s.update(label="✅ HOÀN TẤT! Dữ liệu đã sẵn sàng.", state="complete")
                
                st.balloons()
                st.success("Tuyệt vời Sếp Gus! Toàn bộ Pipeline đã được cập nhật và phân tích AI.")
                time.sleep(2)
                st.rerun()

if __name__ == "__main__":
    main_app()
