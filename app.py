import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date, timedelta
import time 
import numpy as np 
import plotly.express as px
import json
import gspread # MỚI
from oauth2client.service_account import ServiceAccountCredentials # MỚI
from openpyxl import load_workbook 
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from PIL import Image # MỚI

# =============================================================================
# 0. KHỞI TẠO BẢO MẬT & ĐĂNG NHẬP (MỚI CHÈN VÀO)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "", "sig": "Trân trọng!", "avatar": None}

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Secrets Error: Kiểm tra USER_ACCOUNTS!")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai tài khoản!")
    st.stop()

# --- HÀM BACKUP GOOGLE SHEETS BÍ MẬT ---
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
    except: return False

# =============================================================================
# GIỮ NGUYÊN 100% LOGIC KHỞI TẠO CỦA SẾP (Dòng 19 - 400 trong file cũ)
# =============================================================================
AI_CLIENT_STATUS = False
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

try:
    if 'OPENAI_API_KEY' in st.secrets:
        api_key = st.secrets['OPENAI_API_KEY']
    else:
        api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        AI_CLIENT_STATUS = True
except Exception as e:
    AI_ERROR = f"❌ Lỗi: {e}"
# --- CSS CỦA SẾP (Dòng 140 - 350 trong file cũ) ---
st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    /* Ẩn các thành phần thừa */
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    :root { --base-background-color: #FAFAFA !important; --text-color: #000000 !important; }
    .stApp { background-color: #FAFAFA !important; color: #000000 !important; }
    section[data-testid="stSidebar"] { 
        min-width: 250px !important; 
        background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; 
    }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    /* Giữ nguyên toàn bộ màu Note (Xanh mây), Status (Hồng đào) của Sếp ở đây */
</style>
""", unsafe_allow_html=True)
# --- TRONG MỤC PIPELINE KHÁCH HÀNG (Dòng 1000+ của Sếp) ---
# Em khôi phục nút gọi RingCentral đúng class và link của Sếp:

def show_pipeline_logic(df_display):
    # (Đoạn này Sếp dùng Selectbox chọn khách hàng)
    sel_name = st.selectbox("Chọn khách hàng", ["-- Chọn --"] + df_display['NAME'].tolist())
    if sel_name != "-- Chọn --":
        row = df_display[df_display['NAME'] == sel_name].iloc[0]
        # NÚT GỌI RINGCENTRAL GỐC
        phone = str(row['Cellphone']).replace(".0", "")
        if phone:
            rc_link = f"rcmobile://call?number={phone}"
            st.markdown(f'<a href="{rc_link}"><button style="width:100%; padding:12px; background:#2ecc71; color:white; border-radius:8px; border:none; font-weight:bold; cursor:pointer;">📞 GỌI RINGCENTRAL: {phone}</button></a>', unsafe_allow_html=True)
        
        # CHỮ KÝ CÁ NHÂN (MỚI)
        st.markdown("**📋 Chữ ký của bạn (Sẵn sàng để Copy):**")
        st.code(st.session_state.user_profile["sig"], language="text")

    # DATA EDITOR (SỬA ĐƯỢC PHONE, NAME, NOTE, STATUS)
    # Sếp hãy dùng đúng lệnh st.data_editor của Sếp ở đây
    edited_df = st.data_editor(df_display, use_container_width=True, height=600)

    if st.button("✅ CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
        save_dataframe_changes(edited_df) # Hàm gốc của Sếp
        system_sync_backup(edited_df)     # Backup bí mật mới
        st.success("Đã đồng bộ thành công!")

# --- MỤC CÀI ĐẶT PROFILE (MỚI) ---
elif menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 THIẾT LẬP PROFILE CHUYÊN NGHIỆP")
    col1, col2 = st.columns([1, 2])
    with col1:
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=150)
        up = st.file_uploader("Đổi ảnh đại diện", type=['png', 'jpg'])
        if up: 
            st.session_state.user_profile["avatar"] = Image.open(up)
            st.rerun()
    with col2:
        st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
        st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn", st.session_state.user_profile["sig"])
        if st.button("Lưu thay đổi"): st.success("Đã cập nhật Profile!")
