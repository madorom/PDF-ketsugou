import streamlit as st
import subprocess
import os
import tempfile
import io
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🚀 PDFプロ・編集スタジオ（安定版）")
st.write("ファイルが消えるエラーを修正したよ！これで安心して合体できるよ。")

# --- 1. 魔法のメモ帳（セッションステート） ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250
if "active_zoom_index" not in st.session_state:
    st.session_state.active_zoom_index = None

# --- 2. 拡大編集ダイアログ ---
@st.dialog("ページを編集・確認", width="large")
def zoom_edit_modal():
    index = st.session_state.active_zoom_index
    page_info = st.session_state.all_pages_data[index]
    
    col_nav1, col_edit, col_nav2, col_close = st.columns([1, 2, 1, 1])
    with col_nav1:
        if st.button("⬅️ 前へ", use_container_width=True, key="m_prev"):
            if index > 0:
                st.session_state.active_zoom_index = index - 1
                st.rerun()
    with col_edit:
        c1, c2 = st.columns(2)
        with c1:
            icon = "🗑️ 削除" if page_info["active"] else "✅ 復活"
            if st.button(icon, use_container_width=True, key="m_del"):
                page_info["active"] = not page_info["active"]
                st.rerun()
        with c2:
            if st.button("🔄 回転", use_container_width=True, key="m_rot"):
                page_info["rotate"] = (page_info["rotate"] + 90) % 360
                st.rerun()
    with col_nav2:
        if st.button("次へ ➡️", use_container_width=True, key="m_next"):
            if index < len(st.session_state.all_pages_data) - 1:
                st.session_state.active_zoom_index = index + 1
                st.rerun()
    with col_close:
        if st.button("✖️ 閉じる", use_container_width=True, key="m_close", type="primary"):
            st.session_state.active_zoom_index = None
            st.rerun()

    st.divider()
    display_img = page_info["img"].rotate(-page_info["rotate"], expand=True)
    if not page_info["active"]:
        display_img = display_img.convert("L")
        st.warning("⚠️ このページは削除設定中です")
    st.image(display_img, use_container_width=True)

# 拡大画面の表示チェック
if st.session_state.active_zoom_index is not None:
    zoom_edit_modal()

# --- 3. サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    st.session_state.global_zoom = st.slider("🔍 一覧サイズ", 100, 500, st.session_state.global_zoom)
    st.divider()
    use_ocr = st.checkbox("OCRをかける")
    if st.button("♻️ 最初からやり直す"):
        st.session_state.all_pages_data = []
        st.session_state.active_zoom_index = None
        st.rerun()

# --- 4. ファイルアップロードとデータ保存 ---
uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx"], accept_multiple_files=True)

if uploaded_files:
    existing_filenames = {p["filename"] for p in st.session_state.all_pages_data}
    
    for uploaded_file in uploaded_files:
        if uploaded_file.name not in existing_filenames:
            with st.spinner(f"{uploaded_file.name} を準備中..."):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dir_path = Path(temp_dir)
                    input_path = temp_dir_path / uploaded_file.name
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    pdf_path = input_path
                    if input_path.suffix.lower() != ".pdf":
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                        pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                    
                    # 🌟 PDFデータを読み込んで「メモリ（バイト）」として保存！
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    
                    images
