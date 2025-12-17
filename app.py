import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date, timedelta
import time 
import numpy as np 
import plotly.express as px
import json
import gspread # Thêm thư viện backup
from oauth2client.service_account import ServiceAccountCredentials
from openpyxl import load_workbook 
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from PIL import Image
import io

# =============================================================================
# 0. KHỞI TẠO BẢO MẬT & ĐĂNG NHẬP (YÊU CẦU MỚI V7.33.15)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {
        "name": "Sếp Gus", 
        "email": "gus@3m.com", 
        "sig": "Trân trọng, \n3M-Gus Team",
        "avatar": None
    }

# --- ĐỌC SECRETS BẢO MẬT ---
try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    if 'OPENAI_API_KEY' in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
except:
    st.error("❌ Cấu hình Secrets chưa đúng (Thiếu USER_ACCOUNTS hoặc API Key)!")
    st.stop()

# --- GIAO DIỆN ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
                else: st.error("Thông tin xác thực sai!")
    st.stop()

# =============================================================================
# 1. HÀM SAO LƯU GOOGLE SHEETS (BACKUP BÍ MẬT)
# =============================================================================
def system_sync_backup(df):
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
        return True
    except Exception as e:
        print(f"Backup Error: {e}")
        return False

# --- GIỮ NGUYÊN PHẦN CẤU HÌNH AI CỦA SẾP ---
AI_CLIENT_STATUS = True
AI_MODEL = "openai/gpt-4o-mini" 

# =============================================================================
# 2. CSS & GIAO DIỆN CHUẨN CỦA SẾP (GIỮ NGUYÊN 100%)
# =============================================================================
st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    .stApp { background-color: #FAFAFA !important; }
    section[data-testid="stSidebar"] { 
        min-width: 250px !important; 
        background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; 
    }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    /* Nút gọi RingCentral của Sếp */
    .call-btn { width:100%; padding:12px; background:#2ecc71; color:white; border-radius:8px; border:none; font-weight:bold; cursor:pointer; }
</style>
""", unsafe_allow_html=True)
# --- TRONG PHẦN PIPELINE (Dòng khoảng 800+ trong code của Sếp) ---
# Sếp tìm đoạn hiển thị nút gọi RingCentral, em đã thêm phần Checkbox AI như ý Sếp:

show_ai_panel = st.checkbox("🔍 Hiện bảng phân tích kịch bản & Đánh giá Status (AI)")

if show_ai_panel:
    with st.expander("🤖 GÓC CỐ VẤN AI", expanded=True):
        # Giữ nguyên logic run_gus_ai_analysis của Sếp ở đây
        st.info("Hệ thống AI đang sẵn sàng phân tích dựa trên Note và Status của khách hàng.")

# --- NÚT LƯU THAY ĐỔI (Sếp dán đè lên nút lưu cũ) ---
if st.button("✅ CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
    save_dataframe_changes(edited_df) # Hàm gốc của Sếp
    if system_sync_backup(edited_df): # Gọi hàm backup mới
        st.success("Hệ thống đã đồng bộ hóa và sao lưu Google Sheets thành công!")
    else:
        st.warning("Đã lưu nội bộ nhưng lỗi kết nối Google Sheets Backup.")

# =============================================================================
# 3. MỤC CÀI ĐẶT PROFILE MỚI (Email, Tên, Chữ ký, Avatar)
# =============================================================================
elif menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 QUẢN LÝ HỒ SƠ CÁ NHÂN")
    col_av, col_info = st.columns([1, 2])
    
    with col_av:
        st.subheader("Avatar")
        if st.session_state.user_profile["avatar"] is not None:
            st.image(st.session_state.user_profile["avatar"], width=150)
        
        up_file = st.file_uploader("Đổi hình đại diện", type=['png', 'jpg', 'jpeg'])
        if up_file:
            img = Image.open(up_file)
            st.session_state.user_profile["avatar"] = img
            st.rerun()

    with col_info:
        st.session_state.user_profile["name"] = st.text_input("Họ và Tên", st.session_state.user_profile["name"])
        st.session_state.user_profile["email"] = st.text_input("Email liên hệ", st.session_state.user_profile["email"])
        st.session_state.user_profile["sig"] = st.text_area("Chữ ký Email / Tư vấn", st.session_state.user_profile["sig"], height=150)
        
        if st.button("💾 LƯU THAY ĐỔI PROFILE"):
            st.success("Đã cập nhật thông tin cá nhân!")

# --- BỔ SUNG BỘ LỌC 14/30 NGÀY VÀO DASHBOARD ---
# (Trong hàm show_dashboard của Sếp)
today = date.today()
if 'LAST_CALL_DATETIME' in df.columns:
    df['date_only'] = pd.to_datetime(df['LAST_CALL_DATETIME']).dt.date
    over_14 = df[(today - df['date_only']) > timedelta(days=14)]
    st.error(f"💀 CẢNH BÁO: {len(over_14)} khách hàng đã 'nguội' (Quá 14 ngày chưa gọi)")
