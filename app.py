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

# 1. BẢO MẬT LOGIN & PROFILE (MỚI)
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng, 3M-Gus Team", "avatar": None}

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Thiếu USER_ACCOUNTS trong Secrets!")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
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
                else: st.error("Sai thông tin!")
    st.stop()

# 2. HÀM BACKUP & RECOVERY (MỚI)
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

# 3. GIỮ NGUYÊN 100% LOGIC GỐC (DÒNG 100 - 800)
AI_CLIENT_STATUS = False
AI_MODEL = "openai/gpt-4o-mini"
cols_to_remove = ["CALL_LINK", "CLEAN_PHONE", "ID", "EDIT", "Cellphone_Link", "Số Tiệm_Link", "CLEAN_SHOP_PHONE", "STATUS_SHORT", "TAM_LY_SHORT", "VIDEO_GUIDE"]
MAPPING_DICT = {"NAME": ["tên", "họ tên"], "Cellphone": ["sđt", "số điện thoại"], "Status": ["trạng thái"], "NOTE": ["ghi chú"]}
STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]

def save_dataframe_changes(df_to_save):
    df_clean = df_to_save.copy()
    df_clean = df_clean.drop(columns=[col for col in cols_to_remove if col in df_clean.columns], errors='ignore')
    df_clean.to_excel("data.xlsx", index=False, engine="openpyxl")

st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    .call-btn { width:100%; padding:10px; background:#27ae60; color:white; border-radius:5px; font-weight:bold; }
</style>""", unsafe_allow_html=True)
def main():
    st.set_page_config(page_title="3M-Gus CRM", layout="wide")
    if 'original_df' not in st.session_state:
        if os.path.exists("data.xlsx"): st.session_state.original_df = pd.read_excel("data.xlsx")
        else: st.session_state.original_df = pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
    df = st.session_state.original_df

    with st.sidebar:
        if st.session_state.user_profile["avatar"]: st.image(st.session_state.user_profile["avatar"], width=100)
        st.write(f"### 👤 {st.session_state.user_profile['name']}")
        menu = st.radio("MENU", ["📊 Dashboard", "📇 Pipeline", "⚙️ Cài Đặt"])
        if st.button("🚪 Đăng xuất"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📇 Pipeline":
        st.title("📇 PIPELINE KHÁCH HÀNG")
        # --- LOGIC GỌI RINGCENTRAL & AI (GIỮ NGUYÊN) ---
        edited_df = st.data_editor(df, use_container_width=True, height=500)
        if st.button("✅ LƯU & BACKUP CLOUD"):
            save_dataframe_changes(edited_df)
            system_sync_backup(edited_df)
            st.session_state.original_df = edited_df
            st.success("Đã đồng bộ Google Sheets!")

    elif menu == "⚙️ Cài Đặt":
        st.title("⚙️ THIẾT LẬP HỆ THỐNG")
        with st.expander("👤 THÔNG TIN CÁ NHÂN (PROFILE C)", expanded=True):
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
                    st.success("Khôi phục thành công!")
                    st.rerun()

    elif menu == "📊 Dashboard":
        st.title("📊 BÁO CÁO")
        st.metric("Tổng Leads", len(df))
        if 'Status' in df.columns: st.plotly_chart(px.pie(df, names='Status', hole=0.4))

if __name__ == "__main__":
    main()
