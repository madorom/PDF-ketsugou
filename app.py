import streamlit as st
import subprocess
import os
import tempfile
import io
import gc # 🌟 お掃除係（メモリ解放）
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🛡️ PDFプロ・編集スタジオ（究極安定版）")
st.write("大量のページでも壊れないように、画像を特殊な方法で圧縮して保存するよ！")

# --- 1. 魔法のメモ帳（セッションステート） ---
if "page_list" not in st.session_state:
    st.session_state.page_list = []
if "file_vault" not in st.session_state:
    st.session_state.file_vault = {}
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 180
if "active_zoom_index" not in st.session_state:
    st.session_state.active_zoom_index = None

# --- 2. 拡大編集画面（ダイアログ） ---
@st.dialog("ページを編集・確認", width="large")
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
            if st.button(icon, key="m_del"):
                page["active"] = not page["active"]
                st.rerun()
        with c2:
            if st.button("🔄 回転", key="m_rot"):
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
    # 🌟 拡大時だけ高画質で読み込み
    try:
        pdf_data = st.session_state.file_vault[page["filename"]]
        img = convert_from_path(io.BytesIO(pdf_data), first_page=page["page_num"], last_page=page["page_num"], size=(1200, None))[0]
        display_img = img.rotate(-page["rotate"], expand=True)
        if not page["active"]:
            display_img = display_img.convert("L")
        st.image(display_img, use_container_width=True)
    except:
        st.error("画像の読み込みに失敗しました。")

if st.session_state.active_zoom_index is not None:
    zoom_edit_modal()

# --- 3. サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    st.session_state.global_zoom = st.slider("🔍 一覧サイズ", 80, 400, st.session_state.global_zoom)
    st.divider()
    use_ocr = st.checkbox("OCRをかける")
    if st.button("♻️ 最初からやり直す"):
        for key in ["page_list", "file_vault", "active_zoom_index"]:
            st.session_state[key] = [] if key=="page_list" else ({} if key=="file_vault" else None)
        gc.collect() # 掃除
        st.rerun()

# --- 4. ファイル読み込みと「圧縮」画像化 ---
uploaded_files = st.file_uploader("ファイルをえらんでね", type=["pdf", "docx", "xlsx", "pptx", "xlsm"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        if uploaded_file.name not in st.session_state.file_vault:
            with st.spinner(f"{uploaded_file.name} を準備中..."):
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_dir_path = Path(temp_dir)
                    input_path = temp_dir_path / uploaded_file.name
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    pdf_path = input_path
                    if input_path.suffix.lower() != ".pdf":
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)], timeout=60)
                        pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                    
                    if pdf_path.exists():
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()
                        st.session_state.file_vault[uploaded_file.name] = pdf_bytes
                        
                        # 🌟 1ページずつ画像にして「圧縮JPEG」として保存（これがメモリ節約の要！）
                        reader = PdfReader(io.BytesIO(pdf_bytes))
                        for i in range(len(reader.pages)):
                            page_num = i + 1
                            # 1ページだけ画像化
                            img = convert_from_path(io.BytesIO(pdf_bytes), first_page=page_num, last_page=page_num, size=(300, None))[0]
                            
                            # 画像をJPEG形式のバイナリに圧縮
                            buf = io.BytesIO()
                            img.save(buf, format="JPEG", quality=60) # 画質を少し落として軽量化
                            thumb_bytes = buf.getvalue()
                            
                            st.session_state.page_list.append({
                                "id": f"{uploaded_file.name}_{i}_{os.urandom(2).hex()}",
                                "filename": uploaded_file.name,
                                "page_num": page_num,
                                "thumb_bytes": thumb_bytes, # 🌟 圧縮データで持つ
                                "active": True,
                                "rotate": 0
                            })
                            del img, buf # 使い終わったら即消去
                        gc.collect() # ページごとに掃除
                st.rerun()

# --- 5. メイン画面 ---
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

    st.divider()
    st.subheader("📝 ページごとの編集")
    
    rows = [st.session_state.page_list[i:i+6] for i in range(0, len(st.session_state.page_list), 6)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(6)
        for i, page in enumerate(row_pages):
            with cols[i]:
                # 🌟 圧縮データから画像に戻して表示
                img = io.BytesIO(page["thumb_bytes"])
                d_img = convert_from_path(img)[0] if isinstance(page["thumb_bytes"], bytes) else page["thumb_bytes"]
                # 実際にはもっと単純に
                from PIL import Image
                d_img = Image.open(io.BytesIO(page["thumb_bytes"]))
                
                d_img = d_img.rotate(-page["rotate"], expand=True)
                if not page["active"]: d_img = d_img.convert("L")
                st.image(d_img, width=st.session_state.global_zoom)
                
                b1, b2, b3 = st.columns(3)
                with b1:
                    icon = "🗑️" if page["active"] else "✅"
                    if st.button(icon, key=f"a_{page['id']}"):
                        page["active"] = not page["active"]; st.rerun()
                with b2:
                    if st.button("🔄", key=f"r_{page['id']}"):
                        page["rotate"] = (page["rotate"] + 90) % 360; st.rerun()
                with b3:
                    if st.button("🔍", key=f"z_{page['id']}"):
                        st.session_state.active_zoom_index = st.session_state.page_list.index(page)
                        st.rerun()

    # --- 6. 最終合体 ---
    st.divider()
    custom_filename = st.text_input("💾 保存するファイルの名前", value="merged_document")
    if st.button("🚀 PDFを作成して保存", type="primary", use_container_width=True):
        active_pages = [p for p in st.session_state.page_list if p["active"]]
        if active_pages:
            final_merger = PdfWriter()
            with tempfile.TemporaryDirectory() as save_dir:
                save_dir_path = Path(save_dir)
                for i, page in enumerate(active_pages):
                    pdf_bytes = st.session_state.file_vault[page["filename"]]
                    reader = PdfReader(io.BytesIO(pdf_bytes))
                    writer = PdfWriter()
                    page_obj = reader.pages[page["page_num"] - 1]
                    page_obj.rotate(page["rotate"])
                    writer.add_page(page_obj)
                    
                    temp_p = save_dir_path / f"t_{i}.pdf"
                    with open(temp_p, "wb") as f:
                        writer.write(f)
                    
                    if use_ocr:
                        ocr_p = save_dir_path / f"o_{i}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(temp_p), str(ocr_p)])
                        temp_p = ocr_p
                    final_merger.append(str(temp_p))
                    gc.collect() # 合体中も掃除
                
                out_io = io.BytesIO()
                final_merger.write(out_io)
                f_name = custom_filename if custom_filename.endswith(".pdf") else f"{custom_filename}.pdf"
                st.success("🎉 完成！")
                st.download_button("📥 ダウンロード", out_io.getvalue(), f_name)
