import streamlit as st
import subprocess
import os
import tempfile
import io
import gc
import shutil
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items
from PIL import Image

# ページの基本設定
st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🛡️ PDFプロ・編集スタジオ（絶対安定版）")
st.write("データを「ハードディスク」に逃がすことで、メモリ不足（Oh no!）を完全に克服したよ！")

# --- 1. 魔法のフォルダを準備（RAMを節約するためディスクを使う） ---
# アプリが起動している間、ファイルを置いておく専用の場所
if "work_dir" not in st.session_state:
    st.session_state.work_dir = tempfile.mkdtemp()
    st.session_state.page_list = []
    st.session_state.file_registry = {} # ファイル名と保存先の対応表

work_dir = Path(st.session_state.work_dir)

# --- 2. 拡大編集画面（ダイアログ） ---
@st.dialog("ページを確認・編集", width="large")
def zoom_edit_modal():
    idx = st.session_state.active_zoom_index
    if idx is None or idx >= len(st.session_state.page_list):
        st.session_state.active_zoom_index = None
        st.rerun()
        return

    page = st.session_state.page_list[idx]
    
    col1, col2, col3, col4 = st.columns([1, 2, 1, 1])
    with col1:
        if st.button("⬅️ 前へ", key="m_prev") and idx > 0:
            st.session_state.active_zoom_index = idx - 1
            st.rerun()
    with col2:
        c1, c2 = st.columns(2)
        with c1:
            icon = "🗑️ 削除" if page["active"] else "✅ 復活"
            if st.button(icon, use_container_width=True, key="m_del"):
                page["active"] = not page["active"]
                st.rerun()
        with c2:
            if st.button("🔄 回転", use_container_width=True, key="m_rot"):
                page["rotate"] = (page["rotate"] + 90) % 360
                st.rerun()
    with col3:
        if st.button("次へ ➡️", key="m_next") and idx < len(st.session_state.page_list) - 1:
            st.session_state.active_zoom_index = idx + 1
            st.rerun()
    with col4:
        if st.button("✖️ 閉じる", key="m_close", type="primary"):
            st.session_state.active_zoom_index = None
            st.rerun()

    st.divider()
    
    # 🌟 ディスクから読み込んで、この瞬間だけ画像を作る
    with st.spinner("画像を読み込み中..."):
        try:
            pdf_path = st.session_state.file_registry[page["filename"]]
            imgs = convert_from_path(pdf_path, first_page=page["page_num"], last_page=page["page_num"], size=(1200, None))
            if imgs:
                display_img = imgs[0].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    display_img = display_img.convert("L")
                    st.warning("⚠️ 削除設定中")
                st.image(display_img, use_container_width=True)
        except:
            st.error("プレビューの作成に失敗しました。")

if "active_zoom_index" in st.session_state and st.session_state.active_zoom_index is not None:
    zoom_edit_modal()

# --- 3. サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    if st.button("♻️ 最初からやり直す"):
        # 古いフォルダを消して新しく作る
        shutil.rmtree(st.session_state.work_dir, ignore_errors=True)
        st.session_state.work_dir = tempfile.mkdtemp()
        st.session_state.page_list = []
        st.session_state.file_registry = {}
        st.session_state.active_zoom_index = None
        gc.collect()
        st.rerun()
    st.divider()
    use_ocr = st.checkbox("OCR（文字読み取り）をかける")

# --- 4. ファイル読み込み（ディスク保存方式） ---
uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx", "xlsm"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        if uploaded_file.name not in st.session_state.file_registry:
            with st.spinner(f"{uploaded_file.name} を準備中..."):
                # 元ファイルをディスクに保存
                input_path = work_dir / uploaded_file.name
                with open(input_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                pdf_path = input_path
                # PDF以外は変換
                if input_path.suffix.lower() != ".pdf":
                    try:
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(work_dir), str(input_path)], timeout=90)
                        pdf_path = work_dir / (input_path.stem + ".pdf")
                    except:
                        st.error(f"{uploaded_file.name} の変換に失敗しました。")
                        continue
                
                if pdf_path.exists():
                    # 🌟 RAMにデータを置かず、パス（場所）だけを登録する
                    st.session_state.file_registry[uploaded_file.name] = str(pdf_path)
                    
                    reader = PdfReader(str(pdf_path))
                    page_count = len(reader.pages)
                    for i in range(page_count):
                        st.session_state.page_list.append({
                            "id": f"{uploaded_file.name}_P{i+1}_{os.urandom(2).hex()}",
                            "filename": uploaded_file.name,
                            "page_num": i + 1,
                            "active": True,
                            "rotate": 0
                        })
            st.rerun()

# --- 5. メイン画面：並び替えと編集 ---
if st.session_state.page_list:
    st.subheader("🤚 順番をいれかえる")
    active_ids = [p["id"] for p in st.session_state.page_list if p["active"]]
    
    if active_ids:
        new_ids = sort_items(active_ids, direction="horizontal")
        if new_ids != active_ids:
            id_map = {p["id"]: p for p in st.session_state.page_list}
            inactive = [p for p in st.session_state.page_list if not p["active"]]
            st.session_state.page_list = [id_map[nid] for nid in new_ids] + inactive
            st.rerun()
    else:
        st.info("使うページをえらんでね")

    st.divider()
    st.subheader("📝 ページごとの編集（🔍ボタンで中身を確認してね！）")
    
    # グリッド表示
    rows = [st.session_state.page_list[i:i+6] for i in range(0, len(st.session_state.page_list), 6)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(6)
        for i, page in enumerate(row_pages):
            idx = st.session_state.page_list.index(page)
            with cols[i]:
                with st.container(border=True):
                    st.write(f"**P.{page['page_num']}**")
                    st.caption(f"{page['filename'][:12]}...")
                    if not page["active"]: st.write("❌ 削除中")
                    if page["rotate"] != 0: st.write(f"🔄 {page['rotate']}°")
                    
                    if st.button("🔍 編集", key=f"z_btn_{page['id']}", use_container_width=True):
                        st.session_state.active_zoom_index = idx
                        st.rerun()

    # --- 6. 最終合体処理 ---
    st.divider()
    st.subheader("🏁 仕上げ")
    custom_filename = st.text_input("💾 保存するファイルの名前", value="merged_document")
    
    if st.button("🚀 PDFを作成してダウンロード", type="primary", use_container_width=True):
        active_pages = [p for p in st.session_state.page_list if p["active"]]
        if not active_pages:
            st.warning("使うページをえらんでね。")
        else:
            with st.spinner("最終合体中... 少々お待ちを"):
                final_merger = PdfWriter()
                for i, page in enumerate(active_pages):
                    pdf_path = st.session_state.file_registry[page["filename"]]
                    reader = PdfReader(pdf_path)
                    writer = PdfWriter()
                    page_obj = reader.pages[page["page_num"] - 1]
                    page_obj.rotate(page["rotate"])
                    writer.add_page(page_obj)
                    
                    temp_p = work_dir / f"output_temp_{i}.pdf"
                    with open(temp_p, "wb") as f:
                        writer.write(f)
                    
                    if use_ocr:
                        ocr_p = work_dir / f"ocr_temp_{i}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(temp_p), str(ocr_p)])
                        temp_p = ocr_p
                    
                    final_merger.append(str(temp_p))
                
                out_io = io.BytesIO()
                final_merger.write(out_io)
                f_name = custom_filename if custom_filename.endswith(".pdf") else f"{custom_filename}.pdf"
                st.success("🎉 完成しました！")
                st.download_button("📥 ダウンロード", out_io.getvalue(), f_name)
