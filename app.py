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

# =============================================================================
# 0. KHỞI TẠO BẢO MẬT & ĐĂNG NHẬP (YÊU CẦU MỚI)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "", "email": "", "sig": "Trân trọng, \n3M-Gus Team"}

# --- ĐỌC SECRETS BẢO MẬT ---
try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    if 'OPENAI_API_KEY' in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
        AI_CLIENT_STATUS = True
except:
    st.error("❌ Thiếu cấu hình Secrets!")
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
                    st.session_state.user_profile["name"] = u.upper()
                    st.rerun()
                else: st.error("Thông tin xác thực sai!")
    st.stop()

# =============================================================================
# 1. GIỮ NGUYÊN TOÀN BỘ CSS & CẤU HÌNH GỐC CỦA SẾP
# =============================================================================
st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide")

# --- CSS GỐC (GIỮ NGUYÊN KHÔNG SỬA) ---
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
    h1 { color: #D35400 !important; border-bottom: 2px solid #D35400; }
    div[data-testid="stFileUploaderDropzone"] { background-color: #EBF5FB !important; color: #000000 !important; }
</style>
""", unsafe_allow_html=True)

# --- SAO LƯU GOOGLE SHEETS (ÂM THẦM) ---
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
# 2. KHÔI PHỤC MODULE DASHBOARD TRỰC QUAN (GIỮ NGUYÊN LOGIC GỐC)
# =============================================================================
def show_dashboard(df):
    st.title("📊 DASHBOARD TỔNG QUAN")
    if df.empty:
        st.info("Chưa có dữ liệu.")
        return

    # KPIs GỐC
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Tổng số Khách Hàng", len(df))
    need_call = df[df['Status'].str.contains('Interest|Follow', na=False)]
    k2.metric("Khách Cần Gọi Lại 📞", len(need_call))
    k3.metric("Khách DONE ✅", len(df[df['Status'].str.contains('Done', na=False)]))
    k4.metric("Khách STOP/TỪ CHỐI ⛔", len(df[df['Status'].str.contains('Stop|Cold', na=False)]))

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        fig_pie = px.pie(df, names='Status', hole=0.5, title="Phân bổ Giai đoạn (%)")
        st.plotly_chart(fig_pie, use_container_width=True)
    with c2:
        # BỘ LỌC QUÊN GỌI (YÊU CẦU MỚI)
        st.subheader("⚠️ BỘ LỌC QUÊN GỌI")
        today = date.today()
        df['LAST_CONTACT_DATE'] = pd.to_datetime(df['LAST_CONTACT_DATE']).dt.date
        over_14 = df[(today - df['LAST_CONTACT_DATE']) > timedelta(days=14)]
        st.warning(f"🔴 Quá 14 ngày chưa tương tác: {len(over_14)} khách")

# =============================================================================
# 3. KHÔI PHỤC PIPELINE THỰC CHIẾN (NÚT GỌI, SỬA PHONE, STATUS, AI CHECKBOX)
# =============================================================================
def show_pipeline(df):
    st.title("📇 ĐIỀU HÀNH CHIẾN THUẬT")
    
    # CHECKBOX XEM PHÂN TÍCH
    show_ai_panel = st.checkbox("🔍 Kích hoạt Chế độ Cố vấn AI cho khách hàng đã chọn")
    
    sel_name = st.selectbox("Chọn khách hàng để xem Cố vấn chiến thuật", ["-- Chọn --"] + df['NAME'].tolist())
    
    if sel_name != "-- Chọn --":
        row = df[df['NAME'] == sel_name].iloc[0]
        col_call, col_sig = st.columns(2)
        
        with col_call:
            # GỌI RINGCENTRAL + SỐ PHONE
            phone = str(row['Cellphone']).replace(".0", "")
            if phone and phone != "None":
                rc_link = f"rcmobile://call?number={phone}"
                st.markdown(f'<a href="{rc_link}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI RINGCENTRAL: {phone}</button></a>', unsafe_allow_html=True)
            
            if show_ai_panel and st.button(f"🧠 Kích hoạt Cố vấn GUS cho {sel_name}"):
                with st.spinner("Đang trích xuất dữ liệu..."):
                    res = completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": f"Phân tích note: {row['NOTE']}"}])
                    st.info(res.choices[0].message.content)

        with col_sig:
            st.markdown("**📋 Chữ ký tư vấn cá nhân:**")
            st.code(st.session_state.user_profile["sig"])

    st.markdown("---")
    # DATA EDITOR ĐẦY ĐỦ (SỬA ĐƯỢC PHONE, STATUS, NOTE...)
    STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]
    edited_df = st.data_editor(df, use_container_width=True, height=600,
                               column_config={
                                   "Status": st.column_config.SelectboxColumn("Trạng thái", options=STATUS_OPTIONS, required=True),
                                   "Cellphone": st.column_config.TextColumn("Số Phone (Sửa)"),
                                   "LAST_CONTACT_DATE": st.column_config.DateColumn("Ngày tương tác")
                               })
    
    if st.button("✅ CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
        st.session_state.data = edited_df
        system_sync_backup(edited_df)
        st.success("Dữ liệu đã được đồng bộ hóa và sao lưu bảo mật!")

# =============================================================================
# 4. MODULE IMPORT & PROFILE
# =============================================================================
def show_import():
    st.title("📥 NẠP DATA (KHÔNG TỐN AI)")
    up = st.file_uploader("Chọn file Excel Pipeline", type=['xlsx'])
    if up:
        df_new = pd.read_excel(up)
        st.dataframe(df_new.head(10), use_container_width=True)
        if st.button("XÁC NHẬN & ĐỒNG BỘ BÍ MẬT"):
            st.session_state.data = df_new
            system_sync_backup(df_new)
            st.success("Nạp dữ liệu thành công!")

def show_profile():
    st.title("⚙️ THIẾT LẬP PROFILE")
    st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn", st.session_state.user_profile["sig"], height=150)
    if st.button("Lưu Profile"): st.success("Đã cập nhật!")

# =============================================================================
# 5. ĐIỀU HƯỚNG CHÍNH
# =============================================================================
def main():
    if 'data' not in st.session_state: st.session_state.data = pd.DataFrame()

    with st.sidebar:
        st.title(f"👤 {st.session_state.user_profile['name']}")
        menu = st.radio("QUẢN TRỊ HỆ THỐNG", ["📊 Báo Cáo Tổng Quan", "📇 Quản Lý Pipeline", "📥 Khởi Tạo Danh Sách", "⚙️ Thiết Lập Cá Nhân"])
        if st.button("🚪 Đăng Xuất"):
            st.session_state.logged_in = False
            st.rerun()

    if menu == "📊 Báo Cáo Tổng Quan": show_dashboard(st.session_state.data)
    elif menu == "📇 Quản Lý Pipeline": show_pipeline(st.session_state.data)
    elif menu == "📥 Khởi Tạo Danh Sách": show_import()
    elif menu == "⚙️ Thiết Lập Cá Nhân": show_profile()

if __name__ == "__main__":
    main()
