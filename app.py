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

# =============================================================================
# 0. BẢO MẬT & ĐĂNG NHẬP (LỚP VỎ MỚI)
# =============================================================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user_profile' not in st.session_state: 
    st.session_state.user_profile = {
        "name": "Sếp Gus", 
        "email": "gus@3m.com", 
        "sig": "Trân trọng, 3M-Gus Team", 
        "avatar": None
    }

try:
    USER_CREDENTIALS = json.loads(st.secrets['USER_ACCOUNTS'])
except:
    st.error("❌ Secrets Error: Kiểm tra USER_ACCOUNTS!")
    st.stop()

if not st.session_state.logged_in:
    st.set_page_config(page_title="3M-Gus CRM Login", page_icon="🔐")
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align: center; border:none; color: #D35400;'>3M-GUS CRM</h1>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("XÁC THỰC", use_container_width=True):
                if u in USER_CREDENTIALS and str(USER_CREDENTIALS[u]) == str(p):
                    st.session_state.logged_in = True
                    st.rerun()
                else: 
                    st.error("Sai thông tin!")
    st.stop()

# --- HÀM BACKUP & RECOVERY ---
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
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except: return None

# =============================================================================
# 1. LOGIC GỐC CỦA SẾP (V7.33.4) - KHỞI TẠO AI
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
        os.environ["OPENAI_API_KEY"] = api_key
        AI_CLIENT_STATUS = True
except Exception as e:
    AI_ERROR = f"❌ Lỗi: {e}"
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
    TARGET_FILE = "data.xlsx"
    try:
        df_clean.to_excel(TARGET_FILE, index=False, engine="openpyxl")
    except Exception as e: 
        st.error(f"Lỗi lưu file: {e}")
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
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 8px; }
    .call-btn {
        display: inline-block; width: 100%; padding: 10px;
        background-color: #27ae60; color: white;
        text-align: center; border-radius: 5px;
        text-decoration: none; font-weight: bold; margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

@retry(wait=wait_random_exponential(min=4, max=30), stop=stop_after_attempt(5), 
       retry=retry_if_exception_type(Exception))
def call_gpt_analysis(note_content, current_status):
    if AI_CLIENT_STATUS is not True:
        raise Exception("AI_CLIENT_NOT_READY")
    
    note_content = str(note_content).strip()
    if not note_content or note_content.lower() in ["nan", "none", ""]:
        return "KHÔNG CÓ GHI CHÚ", "KHÔNG CÓ GỢI Ý", "Vui lòng nhập ghi chú để AI phân tích."

    json_schema_prompt = """
    {
      "PHAN_TICH_TAM_LY": "Phân tích ngắn gọn tâm lý khách",
      "GOI_Y_HANH_DONG": "Hành động cụ thể tiếp theo",
      "NOI_DUNG_TU_VAN": "Script hoặc nội dung cần nói"
    }
    """
    system_prompt = f"""
    Bạn là trợ lý AI chuyên nghiệp tên GUS, chuyên hỗ trợ Sale trong lĩnh vực tài chính/bảo hiểm.
    Nhiệm vụ: Phân tích ghi chú khách hàng và đưa ra lời khuyên thực chiến.
    Trạng thái hiện tại của khách: {current_status}
    Yêu cầu trả về định dạng JSON duy nhất như sau: {json_schema_prompt}
    Ngôn ngữ: Tiếng Việt chuyên nghiệp, tinh tế.
    """
    try:
        response = completion(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Ghi chú khách hàng: {note_content}"}
            ],
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content)
        return (
            result.get("PHAN_TICH_TAM_LY", "N/A"),
            result.get("GOI_Y_HANH_DONG", "N/A"),
            result.get("NOI_DUNG_TU_VAN", "N/A")
        )
    except Exception as e:
        raise e

def run_gus_ai_analysis(df, force_ai_run=False):
    if df.empty: return df
    for col in ["PHÂN TÍCH TÂM LÝ (GUS)", "GỢI Ý HÀNH ĐỘNG (GUS)", "NỘI DUNG TƯ VẤN (COPY)"]:
        if col not in df.columns: df[col] = "🔘 CHƯA PHÂN TÍCH"
            results = []
    for index, row in df.iterrows():
        note = str(row.get('NOTE', '')).strip()
        current_status = str(row.get('Status', 'Unidentified (10%)')).strip()
        
        if AI_CLIENT_STATUS and (force_ai_run or "CHƯA PHÂN TÍCH" in str(row['PHÂN TÍCH TÂM LÝ (GUS)']).upper()):
            try:
                tam_ly, hanh_dong, script = call_gpt_analysis(note, current_status)
                results.append([current_status, f"🧠 {tam_ly}", f"🎯 {hanh_dong}", script])
            except:
                results.append([current_status, "🔘 LỖI AI", "⚠️ THỬ LẠI SAU", "N/A"])
        else:
            results.append([
                row.get('Status', 'Unidentified (10%)'),
                row.get('PHÂN TÍCH TÂM LÝ (GUS)', '🔘 CHƯA PHÂN TÍCH'),
                row.get('GỢI Ý HÀNH ĐỘNG (GUS)', '🔘 CHƯA PHÂN TÍCH'),
                row.get('NỘI DUNG TƯ VẤN (COPY)', 'N/A')
            ])
            
    df[['Status', "PHÂN TÍCH TÂM LÝ (GUS)", "GỢI Ý HÀNH ĐỘNG (GUS)", "NỘI DUNG TƯ VẤN (COPY)"]] = pd.DataFrame(results, index=df.index)
    return df

def get_status_from_note(note_text):
    if pd.isna(note_text): return "Unidentified (10%)"
    note_lower = str(note_text).lower()
    for status_name, keywords in STATUS_RULES:
        if any(kw in note_lower for kw in keywords):
            return status_name
    return "Unidentified (10%)"
    def unmerge_excel_file(file_path):
    wb = load_workbook(file_path)
    if not wb.sheetnames: return None
    sheet = wb.active
    merged_cells = list(sheet.merged_cells.ranges)
    for merged_cell in merged_cells:
        min_col, min_row, max_col, max_row = merged_cell.min_col, merged_cell.min_row, merged_cell.max_col, merged_cell.max_row
        top_left_value = sheet.cell(row=min_row, column=min_col).value
        sheet.unmerge_cells(start_row=min_row, start_column=min_col, end_row=max_row, end_column=max_col)
        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                sheet.cell(row=row, column=col).value = top_left_value
    temp_unmerged = "temp_unmerged.xlsx"
    wb.save(temp_unmerged)
    return temp_unmerged

def load_data():
    if not os.path.exists("data.xlsx"):
        return pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
    try:
        df = pd.read_excel("data.xlsx", engine="openpyxl")
        df.columns = df.columns.str.strip()
        if 'LAST_CONTACT_DATE' not in df.columns:
            df['LAST_CONTACT_DATE'] = date.today()
        return df
    except:
        return pd.DataFrame(columns=['NAME', 'Cellphone', 'Status', 'NOTE'])
        def clean_phone(p):
    if pd.isna(p) or p == 'nan' or p == '': return ""
    p_str = str(p)
    if p_str.endswith(".0"): p_str = p_str[:-2]
    return re.sub(r'[^0-9]+', '', p_str)

def format_display_phone(p):
    p = clean_phone(p)
    if not p: return ""
    if len(p) == 10: return f"({p[:3]}) {p[3:6]}-{p[6:]}"
    if len(p) == 11: return f"+{p[0]} ({p[1:4]}) {p[4:7]}-{p[7:]}"
    return p

def find_mapping(cols):
    mapping = {}
    for target, patterns in MAPPING_DICT.items():
        for col in cols:
            if any(p.lower() in str(col).lower() for p in patterns):
                mapping[target] = col
                break
    return mapping

def process_imported_df(df_new):
    cols = df_new.columns.tolist()
    mapping = find_mapping(cols)
    df_final = pd.DataFrame()
    for target, actual in mapping.items():
        df_final[target] = df_new[actual]
    
    # Fill các cột thiếu bằng giá trị mặc định
    for col in ["NAME", "Cellphone", "Status", "NOTE"]:
        if col not in df_final.columns:
            df_final[col] = ""
            
    if 'Status' in df_final.columns:
        df_final['Status'] = df_final['Status'].apply(lambda x: x if x in STATUS_OPTIONS else "Unidentified (10%)")
    
    return df_final
    def main():
    if 'original_df' not in st.session_state:
        st.session_state.original_df = load_data()
    
    df = st.session_state.original_df

    # --- SIDEBAR: PROFILE & NAVIGATION ---
    with st.sidebar:
        # HIỂN THỊ PROFILE THEO PHƯƠNG ÁN C
        if st.session_state.user_profile["avatar"]:
            st.image(st.session_state.user_profile["avatar"], width=100)
        
        st.markdown(f"### 👤 {st.session_state.user_profile['name']}")
        st.write(f"📧 {st.session_state.user_profile['email']}")
        
        st.markdown("---")
        menu = st.radio(
            "DANH MỤC QUẢN TRỊ",
            ["📊 Dashboard Tổng Quan", "📇 Pipeline Khách Hàng", "📥 Import Dữ Liệu", "⚙️ Cài Đặt Hệ Thống"]
        )
        
        st.markdown("---")
        st.markdown("### 📽️ VIDEO ĐÀO TẠO")
        for k, v in MENU_VIDEO.items():
            st.link_button(k, v, use_container_width=True)
            
        st.markdown("<br>" * 5, unsafe_allow_html=True)
        if st.button("🚪 Đăng Xuất Hệ Thống", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()

    # --- LOGIC DASHBOARD ---
    if menu == "📊 Dashboard Tổng Quan":
        st.title("📊 PHÂN TÍCH HỆ THỐNG 3M-GUS")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Tổng Leads", len(df))
        if 'Status' in df.columns:
            done_count = len(df[df['Status'] == "Done (100%)"])
            c2.metric("Chốt Đơn (100%)", done_count)
            hot_count = len(df[df['Status'] == "Hot Interest (85%)"])
            c3.metric("Khách Nóng (85%)", hot_count)
            c4.metric("Tỷ lệ Chốt", f"{(done_count/len(df)*100 if len(df)>0 else 0):.1f}%")

        col_left, col_right = st.columns([1, 1])
        with col_left:
            if 'Status' in df.columns:
                fig_status = px.pie(df, names='Status', title="Phân bổ trạng thái khách hàng", hole=0.4)
                st.plotly_chart(fig_status, use_container_width=True)
        with col_right:
            if 'ASSIGNED' in df.columns:
                fig_sale = px.bar(df['ASSIGNED'].value_counts(), title="Năng suất theo Sale")
                st.plotly_chart(fig_sale, use_container_width=True)

    # --- LOGIC PIPELINE (TRÁI TIM CRM) ---
    elif menu == "📇 Pipeline Khách Hàng":
        st.title("📇 QUẢN LÝ PIPELINE THỰC CHIẾN")
        
        # Bộ lọc nhanh
        f1, f2 = st.columns([1, 1])
        with f1:
            search_name = st.text_input("🔍 Tìm tên khách hàng...")
        with f2:
            filter_status = st.multiselect("Lọc trạng thái", STATUS_OPTIONS)

        display_df = df.copy()
        if search_name:
            display_df = display_df[display_df['NAME'].str.contains(search_name, case=False, na=False)]
        if filter_status:
            display_df = display_df[display_df['Status'].isin(filter_status)]

        st.markdown("---")
        # Khu vực Gọi & Chăm sóc nhanh
        sel_name = st.selectbox("🎯 CHỌN KHÁCH HÀNG ĐỂ TƯ VẤN NHANH", ["-- Chọn khách hàng --"] + display_df['NAME'].tolist())
        
        if sel_name != "-- Chọn khách hàng --":
            row_data = display_df[display_df['NAME'] == sel_name].iloc[0]
            phone_raw = str(row_data.get('Cellphone', ''))
            phone_clean = clean_phone(phone_raw)
            
            c_call, c_info = st.columns([1, 2])
            with c_call:
                if phone_clean:
                    st.markdown(f'''
                        <a href="rcmobile://call?number={phone_clean}" target="_blank">
                            <button class="call-btn">📞 GỌI RINGCENTRAL: {format_display_phone(phone_clean)}</button>
                        </a>
                    ''', unsafe_allow_html=True)
                else:
                    st.warning("Không có số điện thoại!")
            
            with c_info:
                st.info(f"💡 **Ghi chú hiện tại:** {row_data.get('NOTE', 'Trống')}")

        st.markdown("### 📝 BẢNG CẬP NHẬT THÔNG TIN")
        # Data Editor - Tính năng Sếp dùng để chỉnh sửa Note và Status
        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            height=500,
            num_rows="dynamic",
            key="pipeline_editor"
        )

        c_save, c_ai, c_sync = st.columns([1, 1, 1])
        with c_save:
            if st.button("💾 LƯU THAY ĐỔI", use_container_width=True):
                # Cập nhật ngược lại original_df
                for idx in edited_df.index:
                    df.loc[idx] = edited_df.loc[idx]
                save_dataframe_changes(df)
                st.success("Đã lưu vào file data.xlsx!")
                with c_ai:
            if st.button("🧠 AI GUS PHÂN TÍCH", use_container_width=True):
                with st.spinner("Gus đang đọc tâm lý khách hàng..."):
                    df = run_gus_ai_analysis(df, force_ai_run=True)
                    save_dataframe_changes(df)
                    st.session_state.original_df = df
                    st.success("AI đã phân tích xong!")
                    st.rerun()

        with c_sync:
            if st.button("☁️ BACKUP TO CLOUD", use_container_width=True):
                with st.spinner("Đang đẩy dữ liệu lên Google Sheets..."):
                    if system_sync_backup(df):
                        st.success("Đã Backup lên Cloud rực rỡ!")
                    else:
                        st.error("Lỗi Backup, kiểm tra Secrets!")

    # --- LOGIC IMPORT DỮ LIỆU ---
    elif menu == "📥 Import Dữ Liệu":
        st.title("📥 IMPORT DATA TỪ FILE EXCEL")
        st.info("Hệ thống sẽ tự động Unmerge và Map các cột: Tên, SĐT, Note, Status.")
        
        uploaded_file = st.file_uploader("Chọn file Excel khách hàng", type=["xlsx", "xls"])
        
        if uploaded_file:
            with open("temp_upload.xlsx", "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            with st.spinner("Đang xử lý Unmerge và Mapping..."):
                unmerged_path = unmerge_excel_file("temp_upload.xlsx")
                df_raw = pd.read_excel(unmerged_path)
                df_processed = process_imported_df(df_raw)
                
                st.write("🔍 **Dữ liệu đã nhận diện được:**")
                st.dataframe(df_processed.head(), use_container_width=True)
                
                if st.button("✅ XÁC NHẬN GỘP VÀO HỆ THỐNG", use_container_width=True):
                    # Gộp dữ liệu mới vào dữ liệu cũ
                    combined_df = pd.concat([df, df_processed], ignore_index=True)
                    combined_df.drop_duplicates(subset=['Cellphone'], keep='last', inplace=True)
                    save_dataframe_changes(combined_df)
                    system_sync_backup(combined_df) # Tự động backup khi import
                    st.session_state.original_df = combined_df
                    st.success("Đã Import và Backup Cloud thành công!")# --- LOGIC CÀI ĐẶT HỆ THỐNG (PHƯƠNG ÁN C) ---
    elif menu == "⚙️ Cài Đặt Hệ Thống":
        st.title("⚙️ THIẾT LẬP TÀI KHOẢN & HỆ THỐNG")
        
        # 1. KHU VỰC PROFILE CÁ NHÂN (HIỆN TRỰC DIỆN)
        st.subheader("👤 THÔNG TIN PROFILE")
        col_avt, col_info = st.columns([1, 2])
        
        with col_avt:
            if st.session_state.user_profile["avatar"]:
                st.image(st.session_state.user_profile["avatar"], width=150)
            up = st.file_uploader("Thay đổi ảnh đại diện", type=['jpg', 'png', 'jpeg'])
            if up:
                st.session_state.user_profile["avatar"] = Image.open(up)
                st.success("Đã tải ảnh lên!")

        with col_info:
            st.session_state.user_profile["name"] = st.text_input("Họ và Tên hiển thị", st.session_state.user_profile["name"])
            st.session_state.user_profile["email"] = st.text_input("Email liên hệ", st.session_state.user_profile["email"])
            st.session_state.user_profile["sig"] = st.text_area("Chữ ký mẫu cho Sale", st.session_state.user_profile["sig"])
            
            if st.button("📋 COPY CHỮ KÝ NHANH"):
                # Logic giả lập copy vào clipboard
                st.code(st.session_state.user_profile["sig"], language="text")
                st.success("Đã hiện mã chữ ký, Sale chỉ cần bôi đen và Copy!")

        st.markdown("---")

        # 2. KHU VỰC QUẢN TRỊ (GIẤU TRONG EXPANDER)
        with st.expander("🛠️ QUẢN TRỊ KỸ THUẬT & DỮ LIỆU (CHỈ DÀNH CHO SẾP)"):
            st.write(f"**Trạng thái AI:** {'✅ Hoạt động' if AI_CLIENT_STATUS else '❌ Lỗi kết nối'}")
            st.write(f"**Model đang dùng:** {AI_MODEL}")
            
            st.warning("⚠️ Khu vực khôi phục dữ liệu khẩn cấp")
            if st.button("🔄 KHÔI PHỤC DỮ LIỆU TỪ CLOUD (GOOGLE SHEETS)"):
                with st.spinner("Đang kéo dữ liệu từ Cloud về..."):
                    recovered_df = system_cloud_recovery()
                    if recovered_df is not None:
                        st.session_state.original_df = recovered_df
                        save_dataframe_changes(recovered_df)
                        st.success("Đã khôi phục dữ liệu thành công! Vui lòng F5 app.")
                        st.rerun()
                    else:
                        st.error("Không tìm thấy bản backup trên Google Sheets!")

# --- CHẠY ỨNG DỤNG ---
if __name__ == "__main__":
    main()
        
