import streamlit as st
import pandas as pd
import json
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from litellm import completion
from datetime import datetime

# =============================================================================
# 1. CẤU HÌNH HỆ THỐNG & BACKUP (GOOGLE SHEETS)
# =============================================================================
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except: return None

def backup_to_sheets(df):
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
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    with st.form("login"):
        u = st.text_input("Tài khoản")
        p = st.text_input("Mật khẩu", type="password")
        if st.form_submit_button("ĐĂNG NHẬP"):
            users = json.loads(st.secrets["USER_ACCOUNTS"])
            if u in users and str(users[u]) == str(p):
                st.session_state.logged_in = True
                st.session_state.user_profile["name"] = u.upper()
                st.rerun()
            else: st.error("Sai tài khoản!")
    st.stop()

# =============================================================================
# 3. GIAO DIỆN CHÍNH
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM", layout="wide")
apply_css = st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    h1 { color: #D35400; border-bottom: 2px solid #D35400; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👤 {st.session_state.user_profile['name']}")
    menu = st.radio("HỆ THỐNG", ["📊 Dashboard", "📇 Pipeline & AI", "📥 Import Data", "⚙️ Profile & Chữ Ký"])
    if st.button("🚪 Thoát"):
        st.session_state.logged_in = False
        st.rerun()

# --- MODULES ---
if menu == "⚙️ Profile & Chữ Ký":
    st.title("👤 THIẾT LẬP PROFILE")
    st.session_state.user_profile["name"] = st.text_input("Họ Tên", st.session_state.user_profile["name"])
    st.session_state.user_profile["email"] = st.text_input("Email", st.session_state.user_profile["email"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn", st.session_state.user_profile["sig"])
    if st.button("Lưu"): st.success("Đã cập nhật!")

elif menu == "📥 Import Data":
    st.title("📥 NẠP DATA (KHÔNG TỐN AI)")
    up = st.file_uploader("Chọn file Excel", type=['xlsx'])
    if up:
        df = pd.read_excel(up)
        st.dataframe(df.head(5))
        if st.button("Xác nhận & Sao lưu bí mật"):
            st.session_state.data = df
            if backup_to_sheets(df): st.toast("✅ Đã backup Google Sheets!")
            st.success("Đã nạp xong!")

elif menu == "📇 Pipeline & AI":
    st.title("📇 QUẢN LÝ PIPELINE")
    if 'data' in st.session_state:
        df = st.session_state.data
        sel_name = st.selectbox("Chọn khách hàng để chạy AI phân tích", ["-- Chọn --"] + df['NAME'].tolist())
        
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            if st.button(f"🧠 Chạy AI phân tích cho {sel_name}"):
                with st.spinner("GUS đang phân tích..."):
                    res = completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": f"Phân tích tâm lý từ note: {row['NOTE']}"}])
                    st.info(res.choices[0].message.content)
            
            # Nút gọi điện
            phone = str(row['Cellphone'])
            st.markdown(f'<a href="tel:{phone}"><button style="width:100%; padding:10px; background:#2ecc71; color:white; border:none; border-radius:5px;">📞 GỌI {phone}</button></a>', unsafe_allow_html=True)
            st.code(st.session_state.user_profile["sig"], language="text") # Chữ ký để copy
        
        st.markdown("---")
        st.data_editor(df, use_container_width=True)
    else: st.info("Chưa có dữ liệu.")

elif menu == "📊 Dashboard":
    st.title("📊 KẾT QUẢ KINH DOANH")
    if 'data' in st.session_state:
        st.metric("Tổng Leads", len(st.session_state.data))
        # (Vẽ biểu đồ tương tự các bản trước)
    else: st.info("Vui lòng Import data.")
