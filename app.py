import streamlit as st
import pandas as pd
import json
import os
import re
import gspread
import plotly.express as px
from datetime import datetime, date, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from litellm import completion

# =============================================================================
# 0. KHỞI TẠO BẢO MẬT & CẤU HÌNH (V7.33.13)
# =============================================================================
try:
    if 'OPENAI_API_KEY' in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Thiếu cấu hình Secrets!")
    st.stop()

# --- DANH MỤC TRẠNG THÁI CHUẨN ---
STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]

# =============================================================================
# 1. QUẢN LÝ ĐĂNG NHẬP & PROFILE
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "", "email": "", "sig": "Trân trọng, \n3M-Gus Team"}

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.session_state.user_profile["name"] = u.upper()
                    st.rerun()
                else: st.error("Sai thông tin!")
    st.stop()

# =============================================================================
# 2. HÀM XỬ LÝ DỮ LIỆU & BACKUP (GOOGLE SHEETS)
# =============================================================================
def clean_phone(p):
    return re.sub(r'[^0-9]+', '', str(p)) if pd.notna(p) else ""

def system_sync_backup(df):
    """Sao lưu bí mật lên Google Sheets"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
        return True
    except: return False

# =============================================================================
# 3. GIAO DIỆN CHÍNH
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM", layout="wide")

# --- CSS SIDEBAR CAM NÂU ---
st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    section[data-testid="stSidebar"] * { color: white !important; }
    h1 { color: #D35400; border-bottom: 2px solid #D35400; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👤 {st.session_state.user_profile['name']}")
    menu = st.radio("QUẢN TRỊ HỆ THỐNG", ["📊 Báo Cáo Tổng Quan", "📇 Quản Lý Pipeline", "📥 Khởi Tạo Danh Sách", "⚙️ Thiết Lập Cá Nhân"])
    
    st.markdown("---")
    st.subheader("▶️ VIDEO TÀI LIỆU")
    st.link_button("🎬 LINK NIỀM TIN", "https://youtu.be/PoUWP--0CDU", use_container_width=True)
    st.link_button("🎬 LINK IUL", "https://youtu.be/DWrgVeBCAIw", use_container_width=True)
    st.link_button("🎬 LINK BỒI THƯỜNG", "https://youtu.com/ZXi79hgbLW0", use_container_width=True)
    st.link_button("🎬 LINK REVIEW KH", "https://youtu.com/3KWj3A4S-RA", use_container_width=True)
    
    if st.button("🚪 Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()

# --- MODULE: BÁO CÁO TỔNG QUAN (KHÔI PHỤC) ---
if menu == "📊 Báo Cáo Tổng Quan":
    st.title("📊 DASHBOARD TỔNG QUAN")
    if 'data' in st.session_state:
        df = st.session_state.data
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Tổng số Khách Hàng", len(df))
        # Logic lọc khách cần gọi lại (Interest/Follow Up)
        need_call = df[df['Status'].str.contains('Interest|Follow', na=False)]
        k2.metric("Khách Cần Gọi Lại 📞", len(need_call))
        k3.metric("Khách DONE ✅", len(df[df['Status'].contains('Done', na=False)]))
        k4.metric("Khách STOP/TỪ CHỐI ⛔", len(df[df['Status'].contains('Stop|Cold', na=False)]))
        
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(df, names='Status', hole=0.5, title="Phân bổ Khách Hàng theo Giai đoạn (%)")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            st.subheader("⚠️ BỘ LỌC QUÊN GỌI")
            today = date.today()
            if 'LAST_CONTACT_DATE' in df.columns:
                df['LAST_CONTACT_DATE'] = pd.to_datetime(df['LAST_CONTACT_DATE']).dt.date
                over_14 = df[(today - df['LAST_CONTACT_DATE']) > timedelta(days=14)]
                over_30 = df[(today - df['LAST_CONTACT_DATE']) > timedelta(days=30)]
                st.warning(f"🔴 Quá 14 ngày chưa gọi: {len(over_14)} khách")
                st.error(f"💀 Quá 30 ngày chưa gọi: {len(over_30)} khách")
                if st.button("Xem danh sách khách quên gọi"):
                    st.dataframe(over_14[['NAME', 'Cellphone', 'LAST_CONTACT_DATE']])
    else: st.info("Vui lòng nạp dữ liệu.")

# --- MODULE: PIPELINE (FULL VŨ KHÍ) ---
elif menu == "📇 Quản Lý Pipeline":
    st.title("📇 ĐIỀU HÀNH CHIẾN THUẬT")
    if 'data' in st.session_state:
        df = st.session_state.data
        
        # Checkbox xem phân tích kịch bản
        show_ai = st.checkbox("🔍 Kích hoạt Chế độ Cố vấn AI cho khách hàng đã chọn")
        
        sel_name = st.selectbox("Chọn khách hàng để thực hiện chiến thuật", ["-- Chọn --"] + df['NAME'].tolist())
        
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            col_a, col_b = st.columns(2)
            
            with col_a:
                if show_ai and st.button(f"🧠 Chạy AI phân tích cho {sel_name}"):
                    with st.spinner("GUS đang phân tích..."):
                        res = completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": f"Phân tích kịch bản tư vấn từ note: {row['NOTE']}"}])
                        st.info(res.choices[0].message.content)
                
                # Nút gọi RingCentral
                phone = clean_phone(row['Cellphone'])
                if phone:
                    rc_link = f"rcmobile://call?number={phone}"
                    st.markdown(f'<a href="{rc_link}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI RINGCENTRAL: {row["Cellphone"]}</button></a>', unsafe_allow_html=True)
            
            with col_b:
                st.markdown("**📋 Chữ ký tư vấn của bạn:**")
                st.code(st.session_state.user_profile["sig"])

        st.markdown("---")
        # Editor cho phép sửa Tên, Phone, Note, Status, ASSIGNED...
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic",
                                   column_config={
                                       "Status": st.column_config.SelectboxColumn("Trạng thái", options=STATUS_OPTIONS, required=True),
                                       "Cellphone": st.column_config.TextColumn("Số Phone (Sửa trực tiếp)"),
                                       "LAST_CONTACT_DATE": st.column_config.DateColumn("Ngày gọi cuối")
                                   })
        
        if st.button("✅ CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
            st.session_state.data = edited_df
            system_sync_backup(edited_df)
            st.success("Hệ thống đã đồng bộ hóa thành công!")
    else: st.info("Chưa có dữ liệu.")

elif menu == "📥 Khởi Tạo Danh Sách":
    st.title("📥 NẠP DỮ LIỆU (KHÔNG TỐN AI)")
    up = st.file_uploader("Chọn file Excel Pipeline", type=['xlsx'])
    if up:
        df_new = pd.read_excel(up)
        st.dataframe(df_new.head(5))
        if st.button("Xác nhận & Đồng bộ hệ thống"):
            st.session_state.data = df_new
            system_sync_backup(df_new)
            st.success("Đã nạp dữ liệu!")

elif menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 THIẾT LẬP PROFILE")
    st.session_state.user_profile["name"] = st.text_input("Họ tên", st.session_state.user_profile["name"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký chuyên nghiệp", st.session_state.user_profile["sig"])
    st.success("Đã lưu!")
