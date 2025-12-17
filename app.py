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
# 0. KHỞI TẠO CẤU HÌNH GLOBAL & BẢO MẬT (V7.33.12)
# =============================================================================
AI_CLIENT_STATUS = False
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

# --- ĐỌC SECRETS (BẢO MẬT TỐI CAO) ---
try:
    # 1. API Key cho AI
    if 'OPENAI_API_KEY' in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
        AI_CLIENT_STATUS = True
    else:
        AI_ERROR = "⚠️ Thiếu OPENAI_API_KEY trong Secrets."

    # 2. Danh sách tài khoản (Thay thế users.xlsx)
    if 'USER_ACCOUNTS' in st.secrets:
        USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    else:
        USER_CREDENTIALS = {"admin": "123456"}

except Exception as e:
    AI_ERROR = f"❌ Lỗi cấu hình Secrets: {e}"

# =============================================================================
# 1. HỆ THỐNG ĐĂNG NHẬP & QUẢN LÝ SESSION
# =============================================================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {"name": "", "email": "", "sig": "Trân trọng, \n3M-Gus Team"}

# --- GIAO DIỆN ĐĂNG NHẬP ---
if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        if AI_ERROR: st.warning(AI_ERROR)
        with st.form("login"):
            u = st.text_input("Mã định danh (Username)")
            p = st.text_input("Mật khẩu truy cập", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.user_profile["name"] = u.upper()
                    st.rerun()
                else: st.error("Thông tin xác thực không chính xác.")
    st.stop()

# =============================================================================
# 2. HỆ THỐNG SAO LƯU BÍ MẬT (GOOGLE SHEETS)
# =============================================================================
def system_sync_backup(df):
    """Hàm ngụy trang: Đồng bộ hệ thống (Thực chất là Backup bí mật)"""
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
# 3. GIỮ NGUYÊN CODE CHUẨN CỦA SẾP (LOGIC XỬ LÝ)
# =============================================================================

# --- CẤU HÌNH VIDEO ---
DEFAULT_MENU_VIDEO = {
    "🎬 LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",        
    "🎬 LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU&list=PLFkppJwxKoxXNFfYDwntyTQB9JT8tZ0yR",       
    "🎬 LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",      
    "🎬 LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"        
}

STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]

def clean_phone(p):
    if pd.isna(p) or p == 'nan' or p == '': return None
    return re.sub(r'[^0-9]+', '', str(p))

@retry(wait=wait_random_exponential(min=4, max=30), stop=stop_after_attempt(5))
def call_gpt_analysis(note_content, current_status):
    if not AI_CLIENT_STATUS: raise Exception("AI_OFF")
    system_prompt = f"Bạn là cố vấn chiến thuật GUS. Phân tích NOTE khách hàng và trả về kịch bản tư vấn. Status hiện tại: {current_status}"
    response = completion(model=AI_MODEL, messages=[{"role": "user", "content": f"Note: {note_content}\n{system_prompt}"}])
    return response.choices[0].message.content

# =============================================================================
# 4. GIAO DIỆN CHÍNH (FULL TÍNH NĂNG + PROFILE)
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM", page_icon="💎", layout="wide")

# --- CSS NGỤY TRANG (GIỮ MÀU CAM NÂU) ---
st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    h1 { color: #D35400; border-bottom: 2px solid #D35400; }
    .stMetric { background-color: #ffffff; border: 1px solid #eee; padding: 15px; border-radius: 10px; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
    menu = st.radio("QUẢN TRỊ HỆ THỐNG", ["📊 Dashboard Tổng Quan", "📇 Quản Lý Pipeline", "📥 Khởi Tạo Danh Sách", "⚙️ Thiết Lập Cá Nhân"])
    
    st.markdown("---")
    st.subheader("▶️ VIDEO TÀI LIỆU")
    for k, v in DEFAULT_MENU_VIDEO.items():
        st.link_button(k, v, use_container_width=True)
        
    if st.button("🚪 Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()

# --- MODULE: DASHBOARD (GIỮ NGUYÊN BIỂU ĐỒ CỦA SẾP) ---
if menu == "📊 Dashboard Tổng Quan":
    st.title("📊 BÁO CÁO KẾT QUẢ KINH DOANH")
    if 'data' in st.session_state:
        df = st.session_state.data
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Tổng số Khách Hàng", len(df))
        k2.metric("Hot Leads 🔥", len(df[df['Status'].str.contains('85%', na=False)]))
        k3.metric("Hoàn Thành ✅", len(df[df['Status'].str.contains('100%', na=False)]))
        k4.metric("Tạm Dừng ⛔", len(df[df['Status'].str.contains('0%', na=False)]))
        
        c1, c2 = st.columns(2)
        with c1:
            fig = px.pie(df, names='Status', title="Phân bổ Pipeline", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            if 'ASSIGNED' in df.columns:
                fig2 = px.bar(df['ASSIGNED'].value_counts(), title="Năng suất Sale")
                st.plotly_chart(fig2, use_container_width=True)
    else: st.info("Vui lòng nạp dữ liệu khách hàng.")

# --- MODULE: PIPELINE (THÊM NÚT GỌI & CHỮ KÝ) ---
elif menu == "📇 Quản Lý Pipeline":
    st.title("📇 ĐIỀU HÀNH CHIẾN THUẬT")
    if 'data' in st.session_state:
        df = st.session_state.data
        sel_name = st.selectbox("Chọn khách hàng để xem Cố vấn chiến thuật", ["-- Chọn --"] + df['NAME'].tolist())
        
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(f"🧠 Kích hoạt Cố vấn GUS cho {sel_name}"):
                    with st.spinner("Đang trích xuất dữ liệu..."):
                        res = call_gpt_analysis(row['NOTE'], row['Status'])
                        st.info(f"**Cố vấn GUS gợi ý:**\n\n{res}")
            with col_b:
                phone = clean_phone(row['Cellphone'])
                if phone:
                    st.markdown(f'<a href="tel:{phone}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI KHÁCH HÀNG: {phone}</button></a>', unsafe_allow_html=True)
                st.markdown("**📋 Chữ ký tư vấn (Copy nhanh):**")
                st.code(st.session_state.user_profile["sig"], language="text")

        st.markdown("---")
        edited = st.data_editor(df, use_container_width=True)
        if st.button("💾 CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
            st.session_state.data = edited
            if system_sync_backup(edited): st.toast("✅ Đã đồng bộ hệ thống!", icon="🔄")
            st.success("Dữ liệu đã được lưu!")
    else: st.info("Chưa có dữ liệu.")

# --- MODULE: IMPORT (KHÔNG CHẠY AI ĐỂ TIẾT KIỆM) ---
elif menu == "📥 Khởi Tạo Danh Sách":
    st.title("📥 NẠP DỮ LIỆU PIPELINE MỚI")
    up = st.file_uploader("Chọn file Excel khách hàng", type=['xlsx'])
    if up:
        df_new = pd.read_excel(up)
        st.dataframe(df_new.head(5))
        if st.button("✅ XÁC NHẬN IMPORT & ĐỒNG BỘ"):
            st.session_state.data = df_new
            system_sync_backup(df_new)
            st.success("Nạp dữ liệu thành công!")
            st.balloons()

# --- MODULE: PROFILE (THEO GÓP Ý CỦA SẾP) ---
elif menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 THIẾT LẬP PROFILE CHUYÊN NGHIỆP")
    st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
    st.session_state.user_profile["email"] = st.text_input("Email công việc", st.session_state.user_profile["email"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn cá nhân", st.session_state.user_profile["sig"], height=150)
    if st.button("Lưu thông tin cá nhân"): st.success("Đã cập nhật Profile!")
