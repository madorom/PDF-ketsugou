import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🖼️ PDF並び替え・編集スタジオ")
st.write("ゴミ箱に入れると、上の並び替えメニューからも消えるよ！")

# --- 魔法のメモ帳（セッションステート） ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = []
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250

# --- 拡大鏡（ダイアログ） ---
@st.dialog("ページを確認")
def zoom_modal(img, rotation):
    st.image(img.rotate(-rotation, expand=True), use_container_width=True)

# --- サイドバーの設定 ---
with st.sidebar:
    st.header("⚙️ 設定")
    st.session_state.global_zoom = st.slider("🔍 画像サイズ", 100, 500, st.session_state.global_zoom)
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
                    
                    images = convert_from_path(pdf_path, size=(600, None))
                    for i, img in enumerate(images):
                        # ユニークなラベルを作る
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

# --- メインエリア：ドラッグ＆ドロップと編集 ---
if st.session_state.all_pages_data:
    st.subheader("🤚 順番をいれかえる（使うページだけ表示）")
    
    # 🌟 使うページ（active=True）のラベルだけを取り出す
    active_labels = [p["id"] for p in st.session_state.all_pages_data if p["active"]]
    
    if active_labels:
        # 並び替えを実行
        sorted_active_labels = sort_items(active_labels, direction="horizontal")

        # 並び順を反映させる（activeなものだけ順番を変え、inactiveなものは後ろにキープ）
        if sorted_active_labels != active_labels:
            active_data_map = {p["id"]: p for p in st.session_state.all_pages_data if p["active"]}
            inactive_data = [p for p in st.session_state.all_pages_data if not p["active"]]
            
            # 新しい順番のactiveデータ + そのままのinactiveデータ
            new_all_data = [active_data_map[lbl] for lbl in sorted_active_labels] + inactive_data
            st.session_state.all_pages_data = new_all_data
            st.rerun()
    else:
        st.write("（使うページがありません。下の「復活」ボタンで戻せるよ！）")

    st.divider()
    st.subheader("📝 ページごとの編集")
    
    # ページを表示する
    rows = [st.session_state.all_pages_data[i:i+4] for i in range(0, len(st.session_state.all_pages_data), 4)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(4)
        for i, page in enumerate(row_pages):
            with cols[i]:
                # 画像の表示
                display_img = page["img"].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    display_img = display_img.convert("L") # 消したページは白黒
                
                st.image(display_img, width=st.session_state.global_zoom)
                
                # ボタンの配置
                b1, b2, b3 = st.columns(3)
                with b1:
                    # ゴミ箱または復活ボタン
                    icon = "🗑️" if page["active"] else "✅"
                    if st.button(icon, key=f"btn_act_{page['id']}_{row_idx}_{i}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄", key=f"btn_rot_{page['id']}_{row_idx}_{i}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()
                with b3:
                    if st.button("🔍", key=f"btn_zom_{page['id']}_{row_idx}_{i}"):
                        zoom_modal(page["img"], page["rotate"])
                
                st.caption(f"{'削除済み' if not page['active'] else 'No.' + str(row_idx*4+i+1)}: {page['id']}")

    # --- 最終保存 ---
    st.divider()
    if st.button("🚀 この内容でPDFを作成して保存", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        active_pages = [p for p in st.session_state.all_pages_data if p["active"]]
        
        if not active_pages:
            st.error("使うページを1つ以上選んでね！")
        else:
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
                        st.write(f"👁️ OCR中: {page['id']}")
                        ocr_p = save_dir_path / f"ocr_{idx}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_p)])
                        final_path = ocr_p
                    final_merger.append(str(final_path))
                
                result_file = save_dir_path / "final.pdf"
                with open(result_file, "wb") as f:
                    final_merger.write(f)
                
                st.success("🎉 完成！")
                with open(result_file, "rb") as f:
                    st.download_button("📥 編集済みPDFをダウンロード", f.read(), "final_document.pdf")
