import streamlit as st
import subprocess
import os
import tempfile
import io
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

# ページの基本設定
st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🚀 PDFプロ・編集スタジオ（エラー修正版）")
st.write("変数のエラーを直したよ！これでスムーズに動くはずだよ。")

# --- 1. 魔法のメモ帳（セッションステート）の準備 ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250
if "active_zoom_index" not in st.session_state:
    st.session_state.active_zoom_index = None

# --- 2. 拡大編集画面（ダイアログ） ---
@st.dialog("ページを編集・確認", width="large")
def zoom_edit_modal():
    index = st.session_state.active_zoom_index
    # インデックスが正常かチェック
    if index is None or index >= len(st.session_state.all_pages_data):
        st.session_state.active_zoom_index = None
        st.rerun()
        return

    page_info = st.session_state.all_pages_data[index]
    
    # 操作ボタン
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
    # 画像の表示
    display_img = page_info["img"].rotate(-page_info["rotate"], expand=True)
    if not page_info["active"]:
        display_img = display_img.convert("L")
        st.warning("⚠️ このページは削除設定中です")
    st.image(display_img, use_container_width=True)

# 拡大画面を表示中なら呼び出す
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

# --- 4. ファイルの読み込みとデータ化 ---
uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx"], accept_multiple_files=True)

if uploaded_files:
    # すでに読み込んだファイル名をリストにする
    current_files = [p["filename"] for p in st.session_state.all_pages_data]
    
    for uploaded_file in uploaded_files:
        # まだ読み込んでいない新しいファイルだけを処理する
        if uploaded_file.name not in current_files:
            with st.spinner(f"{uploaded_file.name} を準備中..."):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dir_path = Path(temp_dir)
                    input_path = temp_dir_path / uploaded_file.name
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    pdf_path = input_path
                    # OfficeファイルをPDFに変換
                    if input_path.suffix.lower() != ".pdf":
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                        pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                    
                    # PDFデータを読み込んで保持
                    if pdf_path.exists():
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()
                        
                        # プレビュー画像を作成
                        try:
                            images = convert_from_path(pdf_path, size=(1200, None))
                            for i, img in enumerate(images):
                                st.session_state.all_pages_data.append({
                                    "id": f"{uploaded_file.name}_{i}_{os.urandom(4).hex()}", 
                                    "filename": uploaded_file.name,
                                    "page_num": i + 1,
                                    "img": img,
                                    "pdf_bytes": pdf_bytes,
                                    "active": True,
                                    "rotate": 0
                                })
                        except Exception as e:
                            st.error(f"画像の作成に失敗しました: {e}")
                
                # 新しいファイルを読み込んだら、一度画面を更新する
                st.rerun()

# --- 5. メイン画面：並び替えと編集 ---
if st.session_state.all_pages_data:
    st.subheader("🤚 順番をいれかえる")
    # 使うページだけを表示
    active_labels = [p["id"] for p in st.session_state.all_pages_data if p["active"]]
    
    if active_labels:
        sorted_ids = sort_items(active_labels, direction="horizontal")
        if sorted_ids != active_labels:
            # 並び順を整理する
            id_map = {p["id"]: p for p in st.session_state.all_pages_data}
            inactive_list = [p for p in st.session_state.all_pages_data if not p["active"]]
            st.session_state.all_pages_data = [id_map[sid] for sid in sorted_ids] + inactive_list
            st.rerun()

    st.divider()
    st.subheader("📝 ページごとの編集")
    
    # 4列のグリッドで表示
    rows = [st.session_state.all_pages_data[i:i+4] for i in range(0, len(st.session_state.all_pages_data), 4)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(4)
        for i, page in enumerate(row_pages):
            idx = row_idx * 4 + i
            with cols[i]:
                # プレビュー画像
                d_img = page["img"].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    d_img = d_img.convert("L")
                st.image(d_img, width=st.session_state.global_zoom)
                
                # 操作ボタン
                b1, b2, b3 = st.columns(3)
                with b1:
                    icon = "🗑️" if page["active"] else "✅"
                    if st.button(icon, key=f"a_{page['id']}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄", key=f"r_{page['id']}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()
                with b3:
                    if st.button("🔍", key=f"z_{page['id']}"):
                        st.session_state.active_zoom_index = idx
                        st.rerun()

    # --- 6. 最終合体処理 ---
    st.divider()
    if st.button("🚀 PDFを作成して保存", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        active_pages = [p for p in st.session_state.all_pages_data
