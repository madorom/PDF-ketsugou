import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items # 🌟 新しい魔法

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🧙‍♂️ PDFプロ編集スタジオ")
st.write("ページを動かして順番をかえたり、大きくしたりできるよ！")

# --- 魔法のメモ帳（セッションステート） ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250

# --- 拡大鏡（ダイアログ）の魔法 ---
@st.dialog("ページを拡大して確認")
def zoom_modal(img, rotation):
    # 拡大画面の中でさらに大きく見せる
    rotated_img = img.rotate(-rotation, expand=True)
    st.image(rotated_img, use_container_width=True)

# --- サイドバーの設定 ---
with st.sidebar:
    st.header("⚙️ 設定")
    st.session_state.global_zoom = st.slider("🔍 カードの大きさ", 100, 500, st.session_state.global_zoom)
    st.divider()
    use_ocr = st.checkbox("OCR（文字読み取り）をかける")
    if st.button("♻️ 最初からやり直す"):
        st.session_state.all_pages_data = []
        st.rerun()

# --- ファイルのアップロード ---
uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx"], accept_multiple_files=True)

if uploaded_files:
    existing_filenames = [p["filename"] for p in st.session_state.all_pages_data]
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
                    
                    images = convert_from_path(pdf_path, size=(600, None))
                    for i, img in enumerate(images):
                        st.session_state.all_pages_data.append({
                            "id": f"{uploaded_file.name}_{i}", # 並べ替え用のID
                            "filename": uploaded_file.name,
                            "page_num": i + 1,
                            "img": img,
                            "pdf_path": str(pdf_path),
                            "active": True,
                            "rotate": 0
                        })
                st.rerun()

# --- ページ一覧（ドラッグ＆ドロップと編集） ---
if st.session_state.all_pages_data:
    st.subheader("🤚 順番をいれかえる（ドラッグしてね）")
    
    # 🌟 ドラッグ＆ドロップ機能
    # IDのリストを作って並べ替えさせる
    ids_only = [p["id"] for p in st.session_state.all_pages_data]
    sorted_ids = sort_items(ids_only, direction="horizontal")
    
    # 並べ替えた結果を元のデータに反映する
    if sorted_ids != ids_only:
        new_data = []
        for sid in sorted_ids:
            for p in st.session_state.all_pages_data:
                if p["id"] == sid:
                    new_data.append(p)
                    break
        st.session_state.all_pages_data = new_data
        st.rerun()

    st.divider()
    st.subheader("📝 ページを編集する")
    cols = st.columns(4)
    for idx, page in enumerate(st.session_state.all_pages_data):
        with cols[idx % 4]:
            with st.container(border=True):
                display_img = page["img"].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    display_img = display_img.convert("L")
                
                st.image(display_img, width=st.session_state.global_zoom)
                st.caption(f"{idx+1}: {page['filename']} (P.{page['page_num']})")
                
                # ボタンを3つ並べる
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("🗑️" if page["active"] else "✅", key=f"del_{idx}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄", key=f"rot_{idx}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()
                with b3:
                    # 🌟 拡大ボタン
                    if st.button("🔍", key=f"zoom_{idx}"):
                        zoom_modal(page["img"], page["rotate"])

    # --- 最終保存 ---
    st.divider()
    if st.button("🚀 PDFを作成してダウンロード", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        with tempfile.TemporaryDirectory() as save_dir:
            save_dir_path = Path(save_dir)
            for idx, page in enumerate(st.session_state.all_pages_data):
                if page["active"]:
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
            
            st.success("🎉 合体完了！")
            with open(result_file, "rb") as f:
                st.download_button("📥 編集済みPDFを保存", f.read(), "final.pdf")
