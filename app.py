import streamlit as st
import pandas as pd
import os
import re
from datetime import datetime, date
import json
from openpyxl import load_workbook 
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image

# --- 1. CẤU HÌNH HỆ THỐNG & BẢO MẬT ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng, 3M-Gus", "avatar": None}

# Định nghĩa các biến hệ thống tránh lỗi NameError
cols_to_remove = ["CALL_LINK", "CLEAN_PHONE", "ID", "EDIT", "Cellphone_Link", "Số Tiệm_Link", "CLEAN_SHOP_PHONE", "STATUS_SHORT", "TAM_LY_SHORT", "VIDEO_GUIDE"]
VIDEO_MENU_KEYS = ["LINK NIỀM TIN", "LINK IUL", "LINK BỒI THƯỜNG", "LINK REVIEW KH"]

# --- 2. KIỂM TRA ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    try:
        USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    except:
        st.error("❌ Cấu hình Secrets USER_ACCOUNTS bị thiếu!")
        st.stop()
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h2 style='text-align: center;'>🔐 3M-GUS CRM LOGIN</h2>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: st.error("Sai thông tin!")
    st.stop()

# --- 3. HÀM BỔ TRỢ (BACKUP & SAVE) ---
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

def system_cloud_recovery():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        return pd.DataFrame(sheet.get_all_records())
    except: return None

def save_dataframe_changes(df_to_save):
    df_clean = df_to_save.copy()
    df_clean = df_clean.drop(columns=[col for col in cols_to_remove if col in df_clean.columns], errors='ignore')
    df_clean.to_excel("data.xlsx", index=False)

# --- 4. GIAO DIỆN CHÍNH ---
def main():
    st.set_page_config(page_title="3M-Gus CRM", page_icon="💎", layout="wide")
    
    if 'original_df' not in st.session_state:
        if os.path.exists("data.xlsx"): st.session_state.original_df = pd.read_excel("data.xlsx")
        else: st.session_state.original_df = pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
    
    df = st.session_state.original_df

    with st.sidebar:
        if st.session_state.user_profile["avatar"]: st.image(st.session_state.user_profile["avatar"], width=100)
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        menu = st.radio("MENU", ["📊 Dashboard", "📇 Pipeline", "⚙️ Cài Đặt"])
        if st.button("🚪 Đăng xuất"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📇 Pipeline":
        st.title("📇 PIPELINE KHÁCH HÀNG")
        edited_df = st.data_editor(df, use_container_width=True, height=500)
        if st.button("✅ LƯU & BACKUP"):
            save_dataframe_changes(edited_df)
            system_sync_backup(edited_df)
            st.session_state.original_df = edited_df
            st.success("Đã đồng bộ thành công!")

    elif menu == "⚙️ Cài Đặt":
        st.title("⚙️ THIẾT LẬP HỆ THỐNG")
        with st.expander("👤 THÔNG TIN CÁ NHÂN", expanded=True):
            st.session_state.user_profile["name"] = st.text_input("Họ tên", st.session_state.user_profile["name"])
            st.session_state.user_profile["sig"] = st.text_area("Chữ ký", st.session_state.user_profile["sig"])
            up = st.file_uploader("Đổi Avatar", type=['jpg','png'])
            if up: st.session_state.user_profile["avatar"] = Image.open(up)
        
        with st.expander("🛠️ QUẢN TRỊ KỸ THUẬT (SẾP)"):
            if st.button("🔄 KHÔI PHỤC DỮ LIỆU TỪ CLOUD"):
                data = system_cloud_recovery()
                if data is not None:
                    st.session_state.original_df = data
                    save_dataframe_changes(data)
                    st.success("Đã khôi phục thành công!")
                    st.rerun()

    elif menu == "📊 Dashboard":
        st.title("📊 BÁO CÁO")
        st.metric("Tổng Leads", len(df))
        if 'Status' in df.columns: st.plotly_chart(px.pie(df, names='Status', hole=0.4))

if __name__ == "__main__":
    main()
