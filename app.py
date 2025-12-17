import streamlit as st
import pandas as pd
import json
import os
import gspread
import plotly.express as px
import plotly.graph_objects as go
from oauth2client.service_account import ServiceAccountCredentials
from litellm import completion
from datetime import datetime

# =============================================================================
# 1. HỆ THỐNG ĐỒNG BỘ DỮ LIỆU NGẦM (BACKUP)
# =============================================================================
def get_gspread_client():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        return gspread.authorize(creds)
    except: return None

def system_sync_backup(df):
    client = get_gspread_client()
    if client:
        try:
            sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
            sheet.clear()
            sheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
            return True
        except: return False
    return False

# =============================================================================
# 2. BẢO MẬT & ĐĂNG NHẬP
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {"name": "", "email": "", "sig": "Trân trọng!"}

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Mã định danh")
            p = st.text_input("Mật khẩu truy cập", type="password")
            if st.form_submit_button("XÁC THỰC TRUY CẬP", use_container_width=True):
                users = json.loads(st.secrets["USER_ACCOUNTS"])
                if u in users and str(users[u]) == str(p):
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"role": "admin" if u.lower() == "admin" else "sale"}
                    st.session_state.user_profile["name"] = u.upper()
                    st.rerun()
                else: st.error("Thông tin xác thực không chính xác.")
    st.stop()

# =============================================================================
# 3. GIAO DIỆN & DASHBOARD TRỰC QUAN (KHÔI PHỤC VỀ BẢN CŨ)
# =============================================================================
st.set_page_config(page_title="3M-Gus CRM System", layout="wide")
st.markdown("""<style>
    section[data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
    h1 { color: #D35400; border-bottom: 2px solid #D35400; }
    .stMetric { background-color: #ffffff; border: 1px solid #eee; padding: 15px; border-radius: 10px; }
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👤 {st.session_state.user_profile['name']}")
    menu = st.radio("QUẢN TRỊ HỆ THỐNG", ["📊 Báo Cáo Tổng Quan", "📇 Quản Lý Pipeline", "📥 Khởi Tạo Danh Sách", "⚙️ Thiết Lập Cá Nhân"])
    if st.button("🚪 Đăng Xuất"):
        st.session_state.logged_in = False
        st.rerun()

# --- MODULE: DASHBOARD (KHÔI PHỤC) ---
if menu == "📊 Báo Cáo Tổng Quan":
    st.title("📊 DASHBOARD TỔNG QUAN")
    if 'data' in st.session_state:
        df = st.session_state.data
        
        # 1. Chỉ số KPIs
        st.subheader("📈 Chỉ số Hiệu suất Chính (KPIs)")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Tổng số Khách Hàng", len(df))
        k2.metric("Khách Cần Gọi Lại 📞", len(df[df['Status'].str.contains('Interest|Follow', na=False)]))
        k3.metric("Khách DONE ✅", len(df[df['Status'].str.contains('Done', na=False)]))
        k4.metric("Khách STOP/TỪ CHỐI ⛔", len(df[df['Status'].str.contains('Stop|Cold', na=False)]))
        
        # 2. Phân tích Dữ liệu (Biểu đồ)
        st.markdown("---")
        st.subheader("📊 Phân tích Dữ liệu")
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.write("**Phân bổ Khách Hàng theo Giai đoạn Bán hàng (%)**")
            fig_pie = px.pie(df, names='Status', hole=0.5, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col_c2:
            st.write("**Phân tích Tâm lý Khách Hàng (GUS AI)**")
            # Giả lập phân tích tâm lý nếu chưa có dữ liệu AI cho tất cả
            if 'PHÂN TÍCH TÂM LÝ (GUS)' in df.columns:
                fig_bar = px.histogram(df, x='PHÂN TÍCH TÂM LÝ (GUS)', color_discrete_sequence=['#D35400'])
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Chưa có dữ liệu phân tích tâm lý tập trung.")
    else:
        st.info("Chào mừng Sếp Gus! Vui lòng 'Khởi tạo danh sách' để xem báo cáo.")

# --- CÁC MODULE KHÁC (NGỤY TRANG CHUYÊN NGHIỆP) ---
elif menu == "📥 Khởi Tạo Danh Sách":
    st.title("📥 NẠP DỮ LIỆU PIPELINE MỚI")
    up = st.file_uploader("Chọn tệp dữ liệu khách hàng (.xlsx)", type=['xlsx'])
    if up:
        df = pd.read_excel(up)
        st.dataframe(df.head(5), use_container_width=True)
        if st.button("✅ XÁC NHẬN & ĐỒNG BỘ HỆ THỐNG"):
            st.session_state.data = df
            system_sync_backup(df)
            st.success("Đã đồng bộ hóa dữ liệu thành công!")

elif menu == "📇 Quản Lý Pipeline":
    st.title("📇 ĐIỀU HÀNH PIPELINE")
    if 'data' in st.session_state:
        df = st.session_state.data
        sel_name = st.selectbox("Chọn khách hàng", ["-- Chọn --"] + df['NAME'].tolist())
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            if st.button(f"🧠 Kích hoạt Cố vấn GUS cho {sel_name}"):
                with st.spinner("Đang phân tích..."):
                    res = completion(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": f"Phân tích tâm lý từ note: {row['NOTE']}"}])
                    st.info(res.choices[0].message.content)
            st.markdown(f'<a href="tel:{row["Cellphone"]}"><button style="width:100%; padding:15px; background:#2ecc71; color:white; border:none; border-radius:10px; font-weight:bold;">📞 GỌI KHÁCH HÀNG: {row["Cellphone"]}</button></a>', unsafe_allow_html=True)
        st.data_editor(df, use_container_width=True)

elif menu == "⚙️ Thiết Lập Cá Nhân":
    st.title("👤 THIẾT LẬP PROFILE")
    st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
    st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn chuyên nghiệp", st.session_state.user_profile["sig"])
    st.success("Profile đã được cập nhật!")
