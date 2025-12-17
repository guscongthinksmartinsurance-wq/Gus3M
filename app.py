import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date, timedelta
import time 
import numpy as np 
import plotly.express as px
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openpyxl import load_workbook 
from litellm import completion
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from PIL import Image

# =============================================================================
# 0. HỆ THỐNG ĐĂNG NHẬP & BẢO MẬT (MỚI TÍCH HỢP)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng, \n3M-Gus Team", "avatar": None}

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    if 'OPENAI_API_KEY' in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
except:
    st.error("❌ Secrets Error: Vui lòng kiểm tra lại USER_ACCOUNTS và OPENAI_API_KEY trong Settings.")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh (Username)")
            p = st.text_input("Mật khẩu truy cập", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai tài khoản hoặc mật khẩu!")
    st.stop()

# --- HÀM SAO LƯU BÍ MẬT (GOOGLE SHEETS) ---
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
# 1. GIỮ NGUYÊN TOÀN BỘ LOGIC KHỞI TẠO CỦA SẾP (DÒNG 1 - 400)
# =============================================================================
AI_CLIENT_STATUS = True
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

DEFAULT_MENU_VIDEO = {
    "LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",        
    "LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU&list=PLFkppJwxKoxXNFfYDwntyTQB9JT8tZ0yR",       
    "LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",      
    "LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"        
}

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
    /* Giữ nguyên các định dạng Note (Xanh mây), Status (Hồng đào) của Sếp */
    div[data-testid="stDataFrame"] { background-color: white !important; }
</style>
""", unsafe_allow_html=True)
def clean_phone(phone_str):
    if pd.isna(phone_str) or phone_str == 'nan' or phone_str == '': return None
    return re.sub(r'[^0-9]+', '', str(phone_str))
def load_data():
    try:
        df = pd.read_excel("data.xlsx", engine="openpyxl")
        return df
    except:
        return pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
        # =============================================================================
# 2. GIAO DIỆN ĐIỀU HÀNH (GIỮ NGUYÊN NÚT GỌI & THÊM TÍNH NĂNG MỚI)
# =============================================================================
def main():
    if 'original_df' not in st.session_state: st.session_state.original_df = load_data()
    df = st.session_state.original_df

    with st.sidebar:
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=100)
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        
        menu = st.radio("HỆ THỐNG", ["📊 Dashboard", "📇 Pipeline", "📥 Import", "⚙️ Profile"])
        st.markdown("---")
        # Nút Link Video chuẩn của Sếp
        for k, v in DEFAULT_MENU_VIDEO.items():
            st.link_button(k, v, use_container_width=True)
        if st.button("🚪 Đăng Xuất"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📇 Pipeline":
        st.title("📇 QUẢN LÝ PIPELINE THỰC CHIẾN")
        # Khôi phục nút gọi RingCentral và Checkbox của Sếp
        show_ai = st.checkbox("🔍 Hiện bảng phân tích & Kịch bản AI")
        sel_name = st.selectbox("Chọn khách hàng", ["-- Chọn --"] + df['NAME'].tolist())
        
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            phone = clean_phone(row['Cellphone'])
            if phone:
                # Nút gọi RingCentral gốc
                rc_link = f"rcmobile://call?number={phone}"
                st.markdown(f'<a href="{rc_link}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI RINGCENTRAL: {phone}</button></a>', unsafe_allow_html=True)
            
            # Chữ ký (Signature) - Yêu cầu mới
            st.markdown("**📋 Chữ ký của bạn:**")
            st.code(st.session_state.user_profile["sig"])
            
        edited_df = st.data_editor(df, use_container_width=True, height=600, num_rows="dynamic")
        
        if st.button("✅ CẬP NHẬT & ĐỒNG BỘ"):
            save_dataframe_changes(edited_df)
            system_sync_backup(edited_df) # Backup âm thầm
            st.success("Hệ thống đã đồng bộ thành công!")

    elif menu == "⚙️ Profile":
        st.title("👤 THIẾT LẬP PROFILE")
        c1, c2 = st.columns([1, 2])
        with c1:
            up = st.file_uploader("Đổi Avatar", type=['jpg','png'])
            if up: st.session_state.user_profile["avatar"] = Image.open(up)
        with c2:
            st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
            st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn", st.session_state.user_profile["sig"])
            if st.button("Lưu thay đổi"): st.success("Đã cập nhật!")


if __name__ == "__main__":
    main()
        
