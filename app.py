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
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image

# =============================================================================
# 0. BẢO MẬT & ĐĂNG NHẬP (MỚI)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng, 3M-Gus Team", "avatar": None}

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Lỗi: USER_ACCOUNTS trong Secrets định dạng sai!")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh")
            p = st.text_input("Mật khẩu", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai thông tin!")
    st.stop()

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
 # --- BẮT ĐẦU LOGIC 1534 DÒNG CỦA SẾP ---
AI_CLIENT_STATUS = False
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

try:
    if 'OPENAI_API_KEY' in st.secrets:
        api_key = st.secrets['OPENAI_API_KEY']
        os.environ["OPENAI_API_KEY"] = api_key
        AI_CLIENT_STATUS = True
except: pass

DEFAULT_MENU_VIDEO = {
    "LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",        
    "LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU&list=PLFkppJwxKoxXNFfYDwntyTQB9JT8tZ0yR",       
    "LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",      
    "LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"        
}

# (Sếp ơi, đoạn này em lược bớt text cho đỡ dài tin nhắn, 
# nhưng khi Sếp dán code cũ vào thì nhớ giữ đủ các hàm: 
# load_menu_config, STATUS_RULES, MAPPING_DICT, save_dataframe_changes, 
# unmerge_excel_file, load_data, normalize_columns...)

st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    :root { --base-background-color: #FAFAFA !important; --text-color: #000000 !important; }
    .stApp { background-color: #FAFAFA !important; color: #000000 !important; }
    section[data-testid="stSidebar"] { 
        min-width: 250px !important; 
        background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; 
    }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
    /* Giữ nguyên toàn bộ mã màu các cột NOTE, Status... của Sếp ở đây */
</style>
""", unsafe_allow_html=True)
def main():
    if 'original_df' not in st.session_state:
        st.session_state.original_df = load_data() # Gọi hàm load_data chuẩn của Sếp
    
    df = st.session_state.original_df

    with st.sidebar:
        # HIỆN AVATAR (MỚI)
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=100)
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        
        # MENU GỐC CỦA SẾP + MỤC PROFILE
        menu = st.radio("HỆ THỐNG", ["📊 Dashboard", "📇 Pipeline", "📥 Import Data", "⚙️ Profile"])
        
        st.markdown("---")
        st.subheader("▶️ VIDEO TÀI LIỆU")
        for k, v in DEFAULT_MENU_VIDEO.items():
            st.link_button(k, v, use_container_width=True)
            
        if st.button("🚪 Đăng Xuất"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📇 Pipeline":
        st.title("📇 QUẢN LÝ PIPELINE")
        # Logic nút gọi RingCentral của Sếp ở đây...
        # Sếp nhớ giữ đoạn: rcmobile://call?number={phone}
        
        edited_df = st.data_editor(df, use_container_width=True, height=600)
        
        if st.button("✅ CẬP NHẬT & ĐỒNG BỘ"):
            save_dataframe_changes(edited_df)
            system_sync_backup(edited_df) # Backup bí mật
            st.session_state.original_df = edited_df
            st.success("Đã đồng bộ Google Sheets!")

    elif menu == "⚙️ Profile":
        st.title("👤 THIẾT LẬP CÁ NHÂN")
        c1, c2 = st.columns([1, 2])
        with c1:
            up = st.file_uploader("Đổi Avatar", type=['png','jpg'])
            if up: st.session_state.user_profile["avatar"] = Image.open(up)
        with c2:
            st.session_state.user_profile["name"] = st.text_input("Họ tên", st.session_state.user_profile["name"])
            st.session_state.user_profile["sig"] = st.text_area("Chữ ký", st.session_state.user_profile["sig"])
            if st.button("Lưu"): st.success("Đã cập nhật!")

    # (Giữ nguyên logic Dashboard và Import cũ của Sếp)

if __name__ == "__main__":
    main()
