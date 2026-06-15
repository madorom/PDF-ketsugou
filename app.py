import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🚀 PDFプロ・編集スタジオ（拡大操作・安定版）")
st.write("ボタンを押しても拡大画面が閉じないように改造したよ！")

# --- 1. 魔法のメモ帳（セッションステート）の初期化 ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250
# 🌟「いま拡大中か、どのページか」を覚えておくためのメモ
if "active_zoom_index" not in st.session_state:
    st.session_state.active_zoom_index = None

# --- 2. 操作ができる拡大ダイアログの定義 ---
@st.dialog("ページを編集・確認", width="large")
def zoom_edit_modal():
    index = st.session_state.active_zoom_index
    page_info = st.session_state.all_pages_data[index]
    
    # リモコン（ボタン）
    col_nav1, col_edit, col_nav2, col_close = st.columns([1, 2, 1, 1])
    
    with col_nav1:
        if st.button("⬅️ 前へ", use_container_width=True, key="modal_prev"):
            if index > 0:
                st.session_state.active_zoom_index = index - 1
                st.rerun()
    
    with col_edit:
        c1, c2 = st.columns(2)
        with c1:
            icon = "🗑️ 削除" if page_info["active"] else "✅ 復活"
            if st.button(icon, use_container_width=True, key="modal_del"):
                page_info["active"] = not page_info["active"]
                st.rerun()
        with c2:
            if st.button("🔄 回転", use_container_width=True, key="modal_rot"):
                page_info["rotate"] = (page_info["rotate"] + 90) % 360
                st.rerun()

    with col_nav2:
        if st.button("次へ ➡️", use_container_width=True, key="modal_next"):
            if index < len(st.session_state.all_pages_data) - 1:
                st.session_state.active_zoom_index = index + 1
                st.rerun()

    with col_close:
        # 🌟【重要】閉じるときはメモを空にする
        if st.button("✖️ 閉じる", use_container_width=True, key="modal_close", type="primary"):
            st.session_state.active_zoom_index = None
            st.rerun()

    st.divider()

    # 画像の表示
    display_img = page_info["img"].rotate(-page_info["rotate"], expand=True)
    if not page_info["active"]:
        display_img = display_img.convert("L")
        st.warning("⚠️ このページは削除設定中です")
    
    st.image(display_img, use_container_width=True)
    st.write(f"ファイル: {page_info['filename']} (P.{page_info['page_num']})")

# --- 🌟 3.【重要】もし拡大中のメモがあれば、ダイアログを自動で呼び出す ---
if st.session_state.active_zoom_index is not None:
    zoom_edit_modal()

# --- 4. サイドバーとファイルのアップロード ---
with st.sidebar:
    st.header("⚙️ 設定")
    st.session_state.global_zoom = st.slider("🔍 一覧でのカードサイズ", 100, 500, st.session_state.global_zoom)
    st.divider()
    use_ocr = st.checkbox("OCRをかける")
    if st.button("♻️ 最初からやり直す"):
        st.session_state.all_pages_data = []
        st.session_state.active_zoom_index = None
        st.rerun()

uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx"], accept_multiple_files=True)

if uploaded_files:
    existing_filenames = {p["filename"] for p in st.session_state.all_pages_data}
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in existing_filenames:
                with st.spinner(f"{uploaded_file.name} を準備中..."):
                    input_path = temp_dir_path / uploaded_file.name
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    pdf_path = input_path
                    if input_path.suffix.lower() != ".pdf":
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                        pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                    
                    images = convert_from_path(pdf_path, size=(1200, None))
                    for i, img in enumerate(images):
                        label = f"📄 {uploaded_file.name} - P.{i+1}"
                        st.session_state.all_pages_data.append({
                            "id": label, 
                            "filename": uploaded_file.name,
                            "page_num": i + 1,
                            "img": img,
                            "pdf_path": str(pdf_path),
                            "active": True,
                            "rotate": 0
                        })
                st.rerun()

# --- 5. メイン画面：並び替えと一覧表示 ---
if st.session_state.all_pages_data:
    st.subheader("🤚 順番をいれかえる")
    active_labels = [p["id"] for p in st.session_state.all_pages_data if p["active"]]
    
    if active_labels:
        sorted_active_labels = sort_items(active_labels, direction="horizontal")
        if sorted_active_labels != active_labels:
            active_data_map = {p["id"]: p for p in st.session_state.all_pages_data if p["active"]}
            inactive_data = [p for p in st.session_state.all_pages_data if not p["active"]]
            new_all_data = [active_data_map[lbl] for lbl in sorted_active_labels] + inactive_data
            st.session_state.all_pages_data = new_all_data
            st.rerun()

    st.divider()
    st.subheader("📝 ページごとの編集")
    
    rows = [st.session_state.all_pages_data[i:i+4] for i in range(0, len(st.session_state.all_pages_data), 4)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(4)
        for i, page in enumerate(row_pages):
            idx = row_idx * 4 + i
            with cols[i]:
                display_img = page["img"].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    display_img = display_img.convert("L")
                
                st.image(display_img, width=st.session_state.global_zoom)
                
                b1, b2, b3 = st.columns(3)
                with b1:
                    icon = "🗑️" if page["active"] else "✅"
                    if st.button(icon, key=f"act_{page['id']}_{idx}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄", key=f"rot_{page['id']}_{idx}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()
                with b3:
                    # 🌟 拡大ボタン：メモにインデックスを書き込んで再起動！
                    if st.button("🔍", key=f"zom_{page['id']}_{idx}"):
                        st.session_state.active_zoom_index = idx
                        st.rerun()
                
                st.caption(f"{'削除済' if not page['active'] else 'No.' + str(idx+1)}")

    # --- 最終保存 ---
    st.divider()
    if st.button("🚀 この内容でPDFを作成して保存", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        active_pages = [p for p in st.session_state.all_pages_data if p["active"]]
        if active_pages:
            with tempfile.TemporaryDirectory() as save_dir:
                save_dir_path = Path(save_dir)
                for idx, page in enumerate(active_pages):
                    reader = PdfReader(page["pdf_path"])
                    temp_writer = PdfWriter()
                    page_obj = reader.pages[page["page_num"] - 1]
                    page_obj.rotate(page["rotate"])
                    temp_writer.add_page(page_obj)
                    temp_p = save_dir_path / f"temp_{idx}.pdf"
                    with open(temp_p, "wb") as f:
                        temp_writer.write(f)
                    
                    final_path = temp_p
                    if use_ocr:
                        ocr_p = save_dir_path / f"ocr_{idx}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_p)])
                        final_path = ocr_p
                    final_merger.append(str(final_path))
                
                result_file = save_dir_path / "final.pdf"
                with open(result_file, "wb") as f:
                    final_merger.write(f)
                st.success("🎉 完成！")
                with open(result_file, "rb") as f:
                    st.download_button("📥 ダウンロード", f.read(), "final.pdf")
