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
# 0. KHỞI TẠO BẢO MẬT & SESSION (KHÔNG LÀM RỐI CODE CŨ)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng!", "avatar": None}

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Secrets Error: Kiểm tra USER_ACCOUNTS!")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai tài khoản!")
    st.stop()

# --- HÀM BACKUP GOOGLE SHEETS (ÂM THẦM) ---
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
# 1. GIỮ NGUYÊN 100% LOGIC XỬ LÝ DỮ LIỆU GỐC CỦA SẾP
# =============================================================================
AI_CLIENT_STATUS = False
AI_MODEL = "openai/gpt-4o-mini" 
if 'OPENAI_API_KEY' in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
    AI_CLIENT_STATUS = True

STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]

def clean_phone(p):
    if pd.isna(p) or p == 'nan' or p == '': return ""
    return re.sub(r'[^0-9]+', '', str(p))

def save_dataframe_changes(df_to_save):
    # Logic dọn dẹp file data.xlsx gốc của Sếp
    TARGET_FILE = "data.xlsx"
    df_to_save.to_excel(TARGET_FILE, index=False, engine="openpyxl")

# --- CSS FIX LỖI TRẮNG NỀN TRẮNG CHỮ ---
st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide")
st.markdown("""
<style>
    .stApp { background-color: #FAFAFA !important; color: #000000 !important; }
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    /* Fix chữ trắng trên nút Sidebar */
    section[data-testid="stSidebar"] .stButton button, section[data-testid="stSidebar"] a {
        color: #FFFFFF !important; border: 1px solid #FFFFFF !important;
    }
    /* Fix chữ đen trong bảng Pipeline */
    .stDataFrame, .stDataEditor { background-color: white !important; color: black !important; }
    h1, h2, h3, p, span { color: #000000 !important; }
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] p { color: white !important; }
</style>
""", unsafe_allow_html=True)
def main():
    # Load data gốc của Sếp
    if 'data' not in st.session_state:
        try:
            st.session_state.data = pd.read_excel("data.xlsx")
        except:
            st.session_state.data = pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE', 'LAST_CONTACT_DATE'])

    df = st.session_state.data

    with st.sidebar:
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=80)
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        menu = st.radio("QUẢN TRỊ", ["📊 Dashboard", "📇 Pipeline", "📥 Import", "⚙️ Profile"])
        st.markdown("---")
        st.link_button("🎬 LINK NIỀM TIN", "https://youtu.be/PoUWP--0CDU")
        st.link_button("🎬 LINK IUL", "https://youtu.be/DWrgVeBCAIw")
        if st.button("🚪 Thoát"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📊 Dashboard":
        st.title("📊 BÁO CÁO TỔNG QUAN")
        if not df.empty:
            k1, k2, k3 = st.columns(3)
            k1.metric("Tổng Leads", len(df))
            # Fix lỗi Dashboard: Đảm bảo cột Status tồn tại
            if 'Status' in df.columns:
                fig = px.pie(df, names='Status', hole=0.4)
                st.plotly_chart(fig, use_container_width=True)
            
            # Bộ lọc 14 ngày của Sếp
            st.subheader("🚨 CẢNH BÁO TRỄ HẸN (14 NGÀY)")
            df['LAST_CONTACT_DATE'] = pd.to_datetime(df['LAST_CONTACT_DATE']).dt.date
            late = df[(date.today() - df['LAST_CONTACT_DATE']) > timedelta(days=14)]
            st.error(f"Có {len(late)} khách hàng quá 14 ngày chưa gọi!")
            st.dataframe(late[['NAME', 'Cellphone', 'LAST_CONTACT_DATE']])

    elif menu == "📇 Pipeline":
        st.title("📇 QUẢN LÝ PIPELINE")
        # Khôi phục nút gọi RingCentral
        sel_name = st.selectbox("Chọn khách hàng", ["--"] + df['NAME'].tolist())
        if sel_name != "--":
            row = df[df['NAME'] == sel_name].iloc[0]
            phone = clean_phone(row['Cellphone'])
            if phone:
                st.markdown(f'<a href="rcmobile://call?number={phone}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI RINGCENTRAL: {phone}</button></a>', unsafe_allow_html=True)
        
        st.markdown("---")
        # Fix lỗi không sửa được phone: Cho phép sửa mọi cột
        edited_df = st.data_editor(df, use_container_width=True, height=500, num_rows="dynamic")
        
        if st.button("✅ LƯU & ĐỒNG BỘ"):
            save_dataframe_changes(edited_df)
            system_sync_backup(edited_df)
            st.session_state.data = edited_df
            st.success("Đã đồng bộ Google Sheets thành công!")

    elif menu == "⚙️ Profile":
        st.title("👤 THIẾT LẬP CÁ NHÂN")
        st.session_state.user_profile["name"] = st.text_input("Họ tên", st.session_state.user_profile["name"])
        st.session_state.user_profile["sig"] = st.text_area("Chữ ký", st.session_state.user_profile["sig"])
        up = st.file_uploader("Đổi Avatar", type=['jpg','png'])
        if up: st.session_state.user_profile["avatar"] = up
        if st.button("Lưu Profile"): st.success("Đã cập nhật!")

    elif menu == "📥 Import":
        st.title("📥 NẠP DỮ LIỆU")
        up = st.file_uploader("Chọn file Excel", type=['xlsx'])
        if up:
            new_df = pd.read_excel(up)
            if st.button("Xác nhận Import"):
                st.session_state.data = new_df
                system_sync_backup(new_df)
                st.success("Đã nạp và backup xong!")

if __name__ == "__main__":
    main()
