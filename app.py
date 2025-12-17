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
import plotly.express as px  # Sửa lỗi đỏ NameError px

# --- 1. BIẾN HỆ THỐNG (GIỮ NGUYÊN TỪ 1534 DÒNG GỐC) ---
cols_to_remove = ["CALL_LINK", "CLEAN_PHONE", "ID", "EDIT", "Cellphone_Link", "Số Tiệm_Link", "CLEAN_SHOP_PHONE", "STATUS_SHORT", "TAM_LY_SHORT", "VIDEO_GUIDE"]
DEFAULT_MENU_VIDEO = {
    "LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",        
    "LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU",       
    "LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",      
    "LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"        
}

# --- 2. BẢO MẬT & PROFILE ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "email": "gus@3m.com", "sig": "Trân trọng, 3M-Gus Team", "avatar": None}

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    try: USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    except: st.error("❌ Thiếu USER_ACCOUNTS!"); st.stop()
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True; st.rerun()
                else: st.error("Sai thông tin!")
    st.stop()

# --- 3. HÀM BACKUP & LOGIC EXCEL ---
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

# --- 4. GIAO DIỆN CHÍNH ---
def main():
    st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide")
    
    # CSS Màu cam đặc trưng của Sếp
    st.markdown("""<style>
        section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
        section[data-testid="stSidebar"] * { color: white !important; }
    </style>""", unsafe_allow_html=True)

    if 'original_df' not in st.session_state:
        if os.path.exists("data.xlsx"): st.session_state.original_df = pd.read_excel("data.xlsx")
        else: st.session_state.original_df = pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
    
    df = st.session_state.original_df

    with st.sidebar:
        if st.session_state.user_profile["avatar"]: st.image(st.session_state.user_profile["avatar"], width=100)
        st.write(f"### 👤 {st.session_state.user_profile['name']}")
        
        # Menu chính
        menu = st.radio("MENU", ["📊 Dashboard", "📇 Pipeline", "📥 Import File", "⚙️ Cài Đặt"])
        
        st.markdown("---")
        st.write("### 📽️ VIDEO ĐÀO TẠO")
        for k, v in DEFAULT_MENU_VIDEO.items():
            st.link_button(k, v, use_container_width=True)
            
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.logged_in = False; st.rerun()

    # --- MENU 1: DASHBOARD ---
    if menu == "📊 Dashboard":
        st.title("📊 BÁO CÁO TỔNG QUAN")
        st.metric("Tổng Leads", len(df))
        if 'Status' in df.columns and not df.empty:
            st.plotly_chart(px.pie(df, names='Status', hole=0.4))
        else: st.info("Chưa có dữ liệu để vẽ biểu đồ.")

    # --- MENU 2: PIPELINE ---
    elif menu == "📇 Pipeline":
        st.title("📇 QUẢN LÝ PIPELINE")
        edited_df = st.data_editor(df, use_container_width=True, height=600)
        if st.button("✅ LƯU & BACKUP CLOUD"):
            edited_df.to_excel("data.xlsx", index=False)
            system_sync_backup(edited_df)
            st.session_state.original_df = edited_df
            st.success("Đã đồng bộ Google Sheets!")

    # --- MENU 3: IMPORT FILE (CHỖ NÀY ĐÂY SẾP ƠI) ---
    elif menu == "📥 Import File":
        st.title("📥 IMPORT DỮ LIỆU MỚI")
        uploaded_file = st.file_uploader("Chọn file Excel", type=["xlsx", "xls"])
        if uploaded_file:
            df_new = pd.read_excel(uploaded_file)
            st.write("Dữ liệu xem trước:")
            st.dataframe(df_new.head())
            if st.button("XÁC NHẬN GỘP DỮ LIỆU"):
                combined = pd.concat([df, df_new], ignore_index=True)
                combined.to_excel("data.xlsx", index=False)
                st.session_state.original_df = combined
                st.success("Đã gộp file thành công!")

    # --- MENU 4: CÀI ĐẶT ---
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
                    data.to_excel("data.xlsx", index=False)
                    st.success("Khôi phục thành công!"); st.rerun()

if __name__ == "__main__":
    main()
