import streamlit as st
import pandas as pd
import os
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PIL import Image
import plotly.express as px
from litellm import completion

# --- 1. CẤU HÌNH HỆ THỐNG & AI ---
AI_MODEL = "openai/gpt-4o-mini"
VIDEO_LINKS = {
    "LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",
    "LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU",
    "LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",
    "LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"
}

# --- 2. BẢO MẬT LOGIN ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {"name": "Sếp Gus", "sig": "Trân trọng, 3M-Gus Team", "avatar": None}

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus Login", page_icon="🔐")
    try:
        USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
        os.environ["OPENAI_API_KEY"] = st.secrets['OPENAI_API_KEY']
    except:
        st.error("❌ Thiếu Secrets (USER_ACCOUNTS hoặc OPENAI_API_KEY)!")
        st.stop()
        
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<h1 style='text-align: center; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True; st.rerun()
                else: st.error("Sai thông tin!")
    st.stop()

# --- 3. HÀM LOGIC (AI, CALL, SAVE) ---
def clean_phone(p):
    return re.sub(r'[^0-9]+', '', str(p)) if pd.notna(p) else ""

def call_ai_gus(note):
    try:
        resp = completion(model=AI_MODEL, messages=[{"role":"user","content":f"Phân tích tâm lý ngắn gọn khách này: {note}"}])
        return resp.choices[0].message.content
    except: return "AI đang bận, thử lại sau."

def save_data(df):
    df.to_excel("data.xlsx", index=False)
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(st.secrets["GOOGLE_SHEET_ID"]).sheet1
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.fillna("").values.tolist())
    except: pass

# --- 4. GIAO DIỆN ---
def main():
    st.set_page_config(page_title="3M-Gus CRM", page_icon="💎", layout="wide")
    
    # CSS: Fix Sidebar & Nút Video chữ Đen
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; }
        [data-testid="stSidebar"] .stButton button { 
            background-color: white !important; color: #333333 !important; 
            font-weight: bold !important; border-radius: 8px !important;
        }
        .call-btn {
            background-color: #27ae60; color: white; padding: 15px;
            text-align: center; border-radius: 10px; text-decoration: none;
            display: block; font-weight: bold; margin-bottom: 20px;
        }
    </style>
    """, unsafe_allow_html=True)

    if 'original_df' not in st.session_state:
        if os.path.exists("data.xlsx"): st.session_state.original_df = pd.read_excel("data.xlsx")
        else: st.session_state.original_df = pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
    
    df = st.session_state.original_df

    with st.sidebar:
        if st.session_state.user_profile["avatar"]: st.image(st.session_state.user_profile["avatar"], width=100)
        st.write(f"### 👤 {st.session_state.user_profile['name']}")
        menu = st.radio("MENU", ["📊 Dashboard", "📇 Pipeline", "📥 Import File", "⚙️ Cài Đặt"])
        st.markdown("---")
        st.write("📽️ **VIDEO ĐÀO TẠO**")
        for k, v in VIDEO_LINKS.items(): st.link_button(k, v, use_container_width=True)
        if st.button("🚪 Đăng xuất", use_container_width=True):
            st.session_state.logged_in = False; st.rerun()

    if menu == "📇 Pipeline":
        st.title("📇 QUẢN LÝ PIPELINE")
        
        # CHỌN KHÁCH HÀNG ĐỂ GỌI & DÙNG AI
        sel_name = st.selectbox("🎯 CHỌN KHÁCH HÀNG", ["-- Chọn khách --"] + df['NAME'].tolist())
        if sel_name != "-- Chọn khách --":
            row = df[df['NAME'] == sel_name].iloc[0]
            phone = clean_phone(row['Cellphone'])
            col_call, col_ai = st.columns(2)
            with col_call:
                if phone: st.markdown(f'<a href="rcmobile://call?number={phone}" class="call-btn">📞 GỌI RINGCENTRAL: {phone}</a>', unsafe_allow_html=True)
            with col_ai:
                if st.button("🧠 AI GUS PHÂN TÍCH TÂM LÝ"):
                    st.info(call_ai_gus(row['NOTE']))

        # BẢNG DỮ LIỆU
        edited_df = st.data_editor(df[['NAME', 'Cellphone', 'Status', 'NOTE']], use_container_width=True, height=500, num_rows="dynamic")
        if st.button("💾 LƯU DỮ LIỆU", use_container_width=True):
            save_data(edited_df); st.session_state.original_df = edited_df; st.success("Đã lưu & đồng bộ!")

    elif menu == "📥 Import File":
        st.title("📥 IMPORT FILE")
        file = st.file_uploader("Chọn file .xlsx", type=["xlsx"])
        if file:
            df_new = pd.read_excel(file)
            st.dataframe(df_new.head())
            if st.button("✅ XÁC NHẬN GỘP"):
                combined = pd.concat([df, df_new], ignore_index=True).drop_duplicates(subset=['Cellphone'], keep='last')
                save_data(combined); st.session_state.original_df = combined; st.success("Đã gộp thành công!")

    elif menu == "📊 Dashboard":
        st.title("📊 BÁO CÁO")
        st.metric("Tổng Leads", len(df))
        if not df.empty and 'Status' in df.columns:
            st.plotly_chart(px.pie(df, names='Status', hole=0.4))

    elif menu == "⚙️ Cài Đặt":
        st.title("⚙️ CÀI ĐẶT")
        st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
        st.session_state.user_profile["sig"] = st.text_area("Chữ ký", st.session_state.user_profile["sig"])
        up = st.file_uploader("Đổi Avatar", type=['jpg','png'])
        if up: st.session_state.user_profile["avatar"] = Image.open(up)

if __name__ == "__main__":
    main()
