import streamlit as st
import subprocess
import os
import tempfile
import base64
from io import BytesIO
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🖼️ 画像ドラッグ＆ドロップ・編集スタジオ")
st.write("プレビュー画像をそのままドラッグして順番をいれかえよう！")

# --- 魔法のメモ帳（セッションステート） ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 200

# --- 画像を文字列に変換する魔法（HTML表示用） ---
def get_image_base64(img, rotation, active):
    # 回転を適用
    img = img.rotate(-rotation, expand=True)
    if not active:
        img = img.convert("L") # 削除済みは白黒に
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# --- 拡大鏡（ダイアログ） ---
@st.dialog("ページを確認")
def zoom_modal(img, rotation):
    st.image(img.rotate(-rotation, expand=True), use_container_width=True)

# --- サイドバーの設定 ---
with st.sidebar:
    st.header("⚙️ 全体の設定")
    st.session_state.global_zoom = st.slider("🔍 表示サイズ", 100, 400, st.session_state.global_zoom)
    st.divider()
    use_ocr = st.checkbox("OCRをかける")
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
                    
                    # 高画質で読み取って保持
                    images = convert_from_path(pdf_path, size=(600, None))
                    for i, img in enumerate(images):
                        st.session_state.all_pages_data.append({
                            "id": f"{uploaded_file.name}_{i}_{os.urandom(4).hex()}",
                            "filename": uploaded_file.name,
                            "page_num": i + 1,
                            "img": img,
                            "pdf_path": str(pdf_path),
                            "active": True,
                            "rotate": 0
                        })
                st.rerun()

# --- メインエリア：ドラッグ＆ドロップと編集 ---
if st.session_state.all_pages_data:
    st.subheader("🤚 画像をドラッグして順番をいれかえる")
    
    # 🌟 ドラッグ用のアイテムを作成（画像を含める）
    sort_items_list = []
    for p in st.session_state.all_pages_data:
        img_b64 = get_image_base64(p["img"], p["rotate"], p["active"])
        # HTMLを使って、ドラッグできる塊の中に画像を入れる
        html_content = f"""
            <div style="text-align:center;">
                <img src="data:image/png;base64,{img_b64}" width="{st.session_state.global_zoom}px" style="border-radius:5px; border:1px solid #ddd;"><br>
                <small>{p['page_num']}ページ目</small>
            </div>
        """
        sort_items_list.append({"id": p["id"], "content": html_content})

    # 🌟 ドラッグ＆ドロップ実行
    # 複数行に並ぶように設定
    new_order_ids = sort_items(sort_items_list, direction="horizontal")

    # 並び順を反映
    if new_order_ids != [p["id"] for p in st.session_state.all_pages_data]:
        id_to_data = {p["id"]: p for p in st.session_state.all_pages_data}
        st.session_state.all_pages_data = [id_to_data[oid] for oid in new_order_ids]
        st.rerun()

    st.divider()
    st.subheader("📝 削除・回転・拡大ボタン")
    
    # 編集用ボタンの並び（並べ替えた後の順番で表示）
    # 4つずつ並べる
    rows = [st.session_state.all_pages_data[i:i+4] for i in range(0, len(st.session_state.all_pages_data), 4)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(4)
        for i, page in enumerate(row_pages):
            global_idx = row_idx * 4 + i
            with cols[i]:
                # ボタン
                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("🗑️", key=f"del_{page['id']}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄", key=f"rot_{page['id']}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()
                with b3:
                    if st.button("🔍", key=f"zoom_{page['id']}"):
                        zoom_modal(page["img"], page["rotate"])
                st.caption(f"No.{global_idx+1}: {page['filename']}")

    # --- 最終保存 ---
    st.divider()
    if st.button("🚀 この順番でPDFを作成して保存", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        with tempfile.TemporaryDirectory() as save_dir:
            save_dir_path = Path(save_dir)
            for page in st.session_state.all_pages_data:
                if page["active"]:
                    reader = PdfReader(page["pdf_path"])
                    temp_writer = PdfWriter()
                    page_obj = reader.pages[page["page_num"] - 1]
                    page_obj.rotate(page["rotate"])
                    temp_writer.add_page(page_obj)
                    temp_p = save_dir_path / f"temp_{page['id']}.pdf"
                    with open(temp_p, "wb") as f:
                        temp_writer.write(f)
                    
                    final_path = temp_p
                    if use_ocr:
                        ocr_p = save_dir_path / f"ocr_{page['id']}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_p)])
                        final_path = ocr_p
                    final_merger.append(str(final_path))
            
            result_file = save_dir_path / "final.pdf"
            with open(result_file, "wb") as f:
                final_merger.write(f)
            
            st.success("🎉 完成！")
            with open(result_file, "rb") as f:
                st.download_button("📥 編集済みPDFをダウンロード", f.read(), "merged.pdf")
