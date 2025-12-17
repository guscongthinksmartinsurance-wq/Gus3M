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
# 0. KHỞI TẠO BẢO MẬT & SESSION STATE (YÊU CẦU MỚI)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {
        "name": "Sếp Gus", 
        "email": "gus@3m.com", 
        "sig": "Trân trọng, \n3M-Gus Team",
        "avatar": None
    }

# --- ĐỌC SECRETS BẢO MẬT ---
try:
    if 'USER_ACCOUNTS' in st.secrets:
        USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
    else:
        USER_CREDENTIALS = {"admin": "123456"}
except:
    st.error("❌ Lỗi: USER_ACCOUNTS trong Secrets định dạng sai!")
    st.stop()

# --- GIAO DIỆN ĐĂNG NHẬP ---
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
                    st.session_state.username = u
                    st.rerun()
                else: st.error("Thông tin xác thực sai!")
    st.stop()

# =============================================================================
# 1. HỆ THỐNG SAO LƯU BÍ MẬT (GOOGLE SHEETS)
# =============================================================================
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
# 2. KHỞI TẠO CẤU HÌNH GLOBAL & AI CLIENT (V7.33.4 GỐC CỦA ANH)
# =============================================================================
AI_CLIENT_STATUS = False
AI_ERROR = None
AI_MODEL = "openai/gpt-4o-mini" 

try:
    if 'OPENAI_API_KEY' in st.secrets:
        api_key = st.secrets['OPENAI_API_KEY']
    else:
        api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        if api_key.startswith(('sk-', 'sk-proj-')):
            os.environ["OPENAI_API_KEY"] = api_key
            AI_CLIENT_STATUS = True
        else:
            AI_ERROR = "❌ Lỗi: API Key định dạng sai."
    else:
        AI_ERROR = "⚠️ Lỗi: Không tìm thấy OPENAI_API_KEY."
except Exception as e:
    AI_ERROR = f"❌ Lỗi cấu hình API Key: {e}"

# --- CẤU HÌNH CỘT LINK VIDEO ---
DEFAULT_MENU_VIDEO = {
    "LINK NIỀM TIN": "https://www.youtube.com/watch?v=PoUWP--0CDU",        
    "LINK IUL": "https://www.youtube.com/watch?v=YqL7qMa1PCU&list=PLFkppJwxKoxXNFfYDwntyTQB9JT8tZ0yR",       
    "LINK BỒI THƯỜNG": "https://www.youtube.com/watch?v=XdwWH2bBvnU",      
    "LINK REVIEW KH": "https://www.youtube.com/watch?v=3KWj3A4S-RA"        
}

def load_menu_config():
    config_file = "GUS_CONFIG.TXT"
    menu = DEFAULT_MENU_VIDEO.copy()
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            if len(lines) >= 1:
                menu = {}
                for line in lines:
                    if '|' in line:
                        t, u = line.split('|', 1)
                        menu[t.strip()] = u.strip()
                if len(menu) == 0: menu = DEFAULT_MENU_VIDEO
        except: pass
    return menu

MENU_VIDEO = load_menu_config()
VIDEO_MENU_KEYS = list(MENU_VIDEO.keys()) 

STATUS_OPTIONS = ["Done (100%)", "Hot Interest (85%)", "Interest (75%)", "Follow Up (50%)", "Unidentified (10%)", "Cold (5%)", "Stop (0%)"]
STATUS_RULES = [
    ("Stop (0%)", ["từ chối", "ko mua", "dnc", "stop", "sai số", "agent", "block", "thái độ tệ", "phá đám"]),
    ("Done (100%)", ["chốt", "ký đơn", "sold", "paid", "hoàn tất", "đã chốt", "đã lấy full thông tin"]),
    ("Hot Interest (85%)", ["báo giá", "quote", "ssn", "chạy giá", "gửi form", "rất quan tâm", "hứng thú", "đã tư vấn đầy đủ", "đã run quote", "rất nhiệt huyết", "lịch hẹn lấy thông tin"]),
    ("Interest (75%)", ["quan tâm", "muốn tìm hiểu", "coi video", "xem clip", "thể hiện sự quan tâm rõ ràng", "khách quen giới thiệu", "khả năng tham gia cao"]),
    ("Follow Up (50%)", ["gọi lại", "sẽ gọi", "hẹn", "bận", "chưa rảnh", "có tiềm năng", "follow lâu dài", "1-6 tháng"]),
    ("Cold (5%)", ["nghĩ lại", "chưa vội", "ko tiền", "hết tiền", "bó tay", "mua với bên khác", "trốn tìm", "bệnh", "già"]),
    ("Unidentified (10%)", ["none", "rỗng", "chưa tương tác", "ko note", "chưa xác định được ý định", "nhu cầu của khách rõ ràng"]),
]
MAPPING_DICT = {
    "NAME": ["tên", "họ tên", "full name", "fullname", "khách hàng", "tên khách", "lead name", "lead"],
    "Cellphone": ["sđt", "số điện thoại", "phone", "mobile", "tel", "cell", "phone number", "số đt"],
    "Số Tiệm": ["số tiệm", "số phone tiệm", "shop phone", "store phone"], 
    "NOTE": ["ghi chú", "note", "nội dung", "mô tả", "comment", "notes"],
    "Status": ["trạng thái", "tình trạng", "status", "state", "STATUS"], 
    "ASSIGNED": ["sale", "người phụ trách", "nhân viên", "assign to"],
}

st.set_page_config(page_title="3M-Gus", page_icon="💎", layout="wide", initial_sidebar_state="expanded")

def save_dataframe_changes(df_to_save):
    cols_to_remove = ["CALL_LINK", "CLEAN_PHONE", "ID", "EDIT", "Cellphone_Link", "Số Tiệm_Link", "CLEAN_SHOP_PHONE", "STATUS_SHORT", "TAM_LY_SHORT", "VIDEO_GUIDE"]
    df_clean = df_to_save.copy()
    if 'LAST_CONTACT_DATE' in df_clean.columns:
         df_clean['LAST_CONTACT_DATE'] = pd.to_datetime(df_clean['LAST_CONTACT_DATE'], errors='coerce').dt.date
    if 'LAST_CALL_DATETIME' in df_clean.columns:
         df_clean['LAST_CALL_DATETIME'] = pd.to_datetime(df_clean['LAST_CALL_DATETIME'], errors='coerce')
    df_clean = df_clean.drop(columns=[col for col in cols_to_remove if col in df_clean.columns], errors='ignore')
    df_clean = df_clean.drop(columns=[col for col in VIDEO_MENU_KEYS if col in df_clean.columns], errors='ignore')
    TEMP_FILE = "temp_data.xlsx"
    TARGET_FILE = "data.xlsx"
    try:
        df_clean.to_excel(TEMP_FILE, index=False, engine="openpyxl")
        if os.path.exists(TARGET_FILE): os.remove(TARGET_FILE)
        os.rename(TEMP_FILE, TARGET_FILE)
    except Exception as e: st.error(f"Lỗi lưu file: {e}")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    :root { --base-background-color: #FAFAFA !important; --text-color: #000000 !important; }
    .stApp { background-color: #FAFAFA !important; color: #000000 !important; }
    section[data-testid="stSidebar"] { 
        min-width: 250px !important; background: linear-gradient(180deg, #D35400 0%, #E67E22 100%) !important; 
    }
    section[data-testid="stSidebar"] * { color: #FFFFFF !important; }
</style>
""", unsafe_allow_html=True)
# =============================================================================
# 2. LOGIC XỬ LÝ (AI & DATA) - GIỮ NGUYÊN 100% LOGIC CỦA SẾP
# =============================================================================

@retry(wait=wait_random_exponential(min=4, max=30), stop=stop_after_attempt(5), 
       retry=retry_if_exception_type(Exception))
def call_gpt_analysis(note_content, current_status):
    if AI_CLIENT_STATUS is not True: raise Exception("AI_CLIENT_NOT_READY") 
    note_content = str(note_content).strip()
    if not note_content: return "KHÔNG GHI CHÚ", "KHÔNG GỢI Ý", "KHÔNG KỊCH BẢN" 

    json_schema_prompt = """{ "PHAN_TICH_TAM_LY": "...", "GOI_Y_HANH_DONG": "...", "NOI_DUNG_TU_VAN": "..." }"""
    system_prompt = f"Bạn là trợ lý AI tên GUS... Status hiện tại: {current_status}"
    
    try:
        response = completion(model=AI_MODEL, messages=[{"role": "system", "content": system_prompt},{"role": "user", "content": f"Ghi chú: {note_content}"}], response_format={"type": "json_object"})
        result = json.loads(response.choices[0].message.content)
        return result.get("PHAN_TICH_TAM_LY", "Lỗi"), result.get("GOI_Y_HANH_DONG", "Lỗi"), result.get("NOI_DUNG_TU_VAN", "Lỗi")
    except Exception as e: raise e

def run_gus_analysis_fallback(note, current_status):
    current_status_updated = current_status
    note_lower = note.lower()
    for status_name, keywords in STATUS_RULES:
        for kw in keywords:
            if kw.lower() in note_lower:
                current_status_updated = status_name
                break
    return [current_status_updated, "🔘 KHÔNG RÕ (AUTO)", "💬 Gửi thông tin (AUTO)", "📝 Chào Anh/Chị... (AUTO)"]

def run_gus_ai_analysis(df, force_ai_run=False):
    if df.empty: return df
    for col in ["PHÂN TÍCH TÂM LÝ (GUS)", "GỢI Ý HÀNH ĐỘNG (GUS)", "NỘI DUNG TƯ VẤN (COPY)"]:
        if col not in df.columns: df[col] = "🔘 CHƯA PHÂN TÍCH"
    
    results = []
    status_placeholder = st.empty()
    for index, row in df.iterrows():
        note = str(row.get('NOTE', '')).strip()
        current_status = str(row.get('Status', 'Unidentified (10%)')).strip()
        
        if AI_CLIENT_STATUS and (force_ai_run or "CHƯA PHÂN TÍCH" in str(row['PHÂN TÍCH TÂM LÝ (GUS)']).upper()):
            try:
                tam_ly, hanh_dong, script = call_gpt_analysis(note, current_status)
                results.append([current_status, f"🧠 {tam_ly} (AI)", f"🎯 {hanh_dong} (AI)", script])
            except:
                results.append(run_gus_analysis_fallback(note, current_status))
        else:
            results.append([row['Status'], row['PHÂN TÍCH TÂM LÝ (GUS)'], row['GỢI Ý HÀNH ĐỘNG (GUS)'], row['NỘI DUNG TƯ VẤN (COPY)']])
    
    df[['Status', "PHÂN TÍCH TÂM LÝ (GUS)", "GỢI Ý HÀNH ĐỘNG (GUS)", "NỘI DUNG TƯ VẤN (COPY)"]] = pd.DataFrame(results, index=df.index)
    return df

def clean_phone(phone_str):
    if pd.isna(phone_str) or phone_str == 'nan' or phone_str == '': return None
    return re.sub(r'[^0-9]+', '', str(phone_str))

def load_data():
    try:
        df = pd.read_excel("data.xlsx", engine="openpyxl")
        df.columns = df.columns.str.strip()
        if 'LAST_CONTACT_DATE' not in df.columns: df['LAST_CONTACT_DATE'] = date.today()
        df['CLEAN_PHONE'] = df['Cellphone'].apply(clean_phone)
        return df
    except: return pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE', 'ASSIGNED'])

# =============================================================================
# 3. GIAO DIỆN CHÍNH & PROFILE (YÊU CẦU MỚI)
# =============================================================================
def main():
    if 'original_df' not in st.session_state: st.session_state.original_df = load_data()
    df = st.session_state.original_df

    with st.sidebar:
        # HIỂN THỊ AVATAR TRÊN SIDEBAR
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=100)
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        
        menu = st.radio("MENU CHÍNH", ["📊 Báo Cáo Tổng Quan", "📇 Pipeline Khách Hàng", "📥 Import Data", "⚙️ Profile & Chữ Ký"])
        
        st.markdown("---")
        st.subheader("▶️ VIDEO TÀI LIỆU")
        for k, v in MENU_VIDEO.items():
            st.link_button(k, v, use_container_width=True)
            
        if st.button("🚪 Đăng Xuất"):
            st.session_state.logged_in = False
            st.rerun()

    # --- MODULE: PROFILE (MỚI) ---
    if menu == "⚙️ Profile & Chữ Ký":
        st.title("⚙️ THIẾT LẬP PROFILE CÁ NHÂN")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("Avatar")
            up_file = st.file_uploader("Tải ảnh đại diện", type=['png', 'jpg', 'jpeg'])
            if up_file: 
                st.session_state.user_profile["avatar"] = Image.open(up_file)
                st.success("Đã nạp ảnh!")
        with c2:
            st.session_state.user_profile["name"] = st.text_input("Tên hiển thị", st.session_state.user_profile["name"])
            st.session_state.user_profile["email"] = st.text_input("Email", st.session_state.user_profile["email"])
            st.session_state.user_profile["sig"] = st.text_area("Chữ ký tư vấn", st.session_state.user_profile["sig"], height=150)
            if st.button("💾 Lưu Profile"): st.success("Đã cập nhật!")

    # --- MODULE: PIPELINE (GIỮ NGUYÊN NÚT GỌI & THÊM BACKUP) ---
    elif menu == "📇 Pipeline Khách Hàng":
        st.title("📇 PIPELINE KHÁCH HÀNG")
        
        # Checkbox tiết kiệm AI
        run_ai = st.checkbox("🔍 Kích hoạt Cố vấn AI cho khách hàng chọn bên dưới")
        
        sel_name = st.selectbox("Chọn khách hàng", ["-- Chọn --"] + df['NAME'].tolist())
        if sel_name != "-- Chọn --":
            row = df[df['NAME'] == sel_name].iloc[0]
            # NÚT GỌI RINGCENTRAL CỦA SẾP
            phone = clean_phone(row['Cellphone'])
            if phone:
                rc_link = f"rcmobile://call?number={phone}"
                st.markdown(f'<a href="{rc_link}"><button class="call-btn">📞 GỌI RINGCENTRAL: {row["Cellphone"]}</button></a>', unsafe_allow_html=True)
            
            if run_ai and st.button("🧠 Chạy AI Phân Tích"):
                with st.spinner("Đang phân tích..."):
                    t, h, s = call_gpt_analysis(row['NOTE'], row['Status'])
                    st.info(f"**GUS gợi ý:** {s}")
            
            st.markdown("**📋 Chữ ký của bạn:**")
            st.code(st.session_state.user_profile["sig"])

        st.markdown("---")
        edited_df = st.data_editor(df, use_container_width=True, height=600, num_rows="dynamic")
        
        if st.button("✅ CẬP NHẬT & ĐỒNG BỘ HỆ THỐNG"):
            save_dataframe_changes(edited_df)
            if system_sync_backup(edited_df):
                st.success("✅ Đã lưu và Sao lưu Google Sheets thành công!")
            else:
                st.warning("⚠️ Đã lưu nhưng lỗi đồng bộ Google Sheets.")
            st.session_state.original_df = edited_df

    # --- MODULE: DASHBOARD (THÊM BỘ LỌC 14 NGÀY) ---
    elif menu == "📊 Báo Cáo Tổng Quan":
        st.title("📊 DASHBOARD TỔNG QUAN")
        k1, k2, k3 = st.columns(3)
        k1.metric("Tổng Leads", len(df))
        
        # Biểu đồ của Sếp
        fig = px.pie(df, names='Status', hole=0.4, title="Tỷ lệ Pipeline")
        st.plotly_chart(fig, use_container_width=True)
        
        # Bộ lọc quên gọi (Yêu cầu của Sếp)
        st.subheader("🚨 CẢNH BÁO QUÊN GỌI (QUÁ 14 NGÀY)")
        df['LAST_CONTACT_DATE'] = pd.to_datetime(df['LAST_CONTACT_DATE']).dt.date
        late_leads = df[(date.today() - df['LAST_CONTACT_DATE']) > timedelta(days=14)]
        if not late_leads.empty:
            st.error(f"Phát hiện {len(late_leads)} khách hàng quá 14 ngày chưa tương tác!")
            st.dataframe(late_leads[['NAME', 'Cellphone', 'LAST_CONTACT_DATE']])

    # --- MODULE: IMPORT ---
    elif menu == "📥 Import Data":
        st.title("📥 NẠP DỮ LIỆU")
        up = st.file_uploader("Chọn file Excel", type=['xlsx'])
        if up:
            new_df = pd.read_excel(up)
            if st.button("Xác nhận Import"):
                st.session_state.original_df = new_df
                system_sync_backup(new_df)
                st.success("Đã nạp và sao lưu dữ liệu!")

if __name__ == "__main__":
    main()
