import streamlit as st
import pandas as pd
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from litellm import completion
from datetime import datetime

# =============================================================================
# 1. HỆ THỐNG ĐỒNG BỘ DỮ LIỆU NGẦM (BACKUP)
# =============================================================================
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except: return None

def system_sync_backup(df):
    """Đẩy dữ liệu về Google Sheets ngầm dưới tên gọi Đồng bộ hệ thống"""
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
            sheet.clear()
            sheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
            return True
        except: return False
    return False

# =============================================================================
# 2. BẢO MẬT & ĐĂNG NHẬP
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {"name": "", "email": "", "sig": "Trân trọng!"}

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh")
            p = st.text_input("Mật khẩu truy cập", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                users = json.loads(st.secrets["USER_ACCOUNTS"])
                if u in users and str(users[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.user_profile["name"] = u.upper()
                    st.rerun()
                else: st.error("Thông tin xác thực không chính xác.")
    st.stop()

# =============================================================================
# 3. GIAO DIỆN CHUYÊN NGHIỆP
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM System", layout="wide")
st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    h1 { color: #D35400; border-bottom: 2px solid #D35400; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👤 {st.session_state.user_profile['name']}")
    menu = st.radio("QUẢN TRỊ HỆ THỐNG", ["📊 Báo Cáo Tổng Quan", "📇 Quản Lý Pipeline", "📥 Khởi Tạo Danh Sách", "⚙️ Thiết Lập Cá Nhân"])
    if st.button("🚪 Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()

# --- MODULES ---
if menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 THIẾT LẬP PROFILE")
    st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
    st.session_state.user_profile["email"] = st.text_input("Email công việc", st.session_state.user_profile["email"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn chuyên nghiệp", st.session_state.user_profile["sig"])
    if st.button("Cập nhật thông tin"): st.success("Hệ thống đã lưu thông tin Profile!")

elif menu == "📥 Khởi Tạo Danh Sách":
    st.title("📥 NẠP DỮ LIỆU PIPELINE MỚI")
    up = st.file_uploader("Chọn tệp dữ liệu khách hàng (.xlsx)", type=['xlsx'])
    if up:
        df = pd.read_excel(up)
        st.write("Dữ liệu nạp vào hệ thống:")
        st.dataframe(df.head(5), use_container_width=True)
        if st.button("✅ XÁC NHẬN & ĐỒNG BỘ HỆ THỐNG"):
            st.session_state.data = df
            if system_sync_backup(df): st.toast("🔄 Đã hoàn tất đồng bộ dữ liệu chuẩn.", icon="✅")
            st.success("Dữ liệu đã được nạp thành công vào Pipeline!")

elif menu == "📇 Quản Lý Pipeline":
    st.title("📇 ĐIỀU HÀNH PIPELINE")
    if 'data' in st.session_state:
        df = st.session_state.data
        sel_name = st.selectbox("Chọn khách hàng để xem Cố vấn chiến thuật", ["-- Chọn khách hàng --"] + df['NAME'].tolist())
        
        if sel_name != "-- Chọn khách hàng --":
            row = df[df['NAME'] == sel_name].iloc[0]
            if st.button(f"🧠 Kích hoạt Cố vấn chiến thuật cho: {sel_name}"):
                with st.spinner("Đang trích xuất dữ liệu phân tích..."):
                    res = completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": f"Phân tích tâm lý từ note: {row['NOTE']}"}])
                    st.info(f"**Phân tích từ Cố vấn GUS:**\n\n{res.choices[0].message.content}")
            
            # Liên kết gọi điện chuyên nghiệp
            phone = str(row['Cellphone'])
            st.markdown(f'<a href="tel:{phone}"><button style="width:100%; padding:15px; background-color:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold; cursor:pointer;">📞 THỰC HIỆN CUỘC GỌI: {phone}</button></a>', unsafe_allow_html=True)
            st.markdown("**📋 Chữ ký tư vấn của bạn (Sẵn sàng để Copy):**")
            st.code(st.session_state.user_profile["sig"], language="text")
        
        st.markdown("---")
        st.data_editor(df, use_container_width=True)
    else: st.info("Vui lòng thực hiện bước 'Khởi tạo danh sách' trước.")

elif menu == "📊 Báo Cáo Tổng Quan":
    st.title("📊 KẾT QUẢ KINH DOANH TỔNG THỂ")
    if 'data' in st.session_state:
        st.metric("Tổng số mục tiêu (Leads)", len(st.session_state.data))
    else: st.info("Hệ thống chưa có dữ liệu báo cáo.")
