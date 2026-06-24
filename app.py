import streamlit as st
import subprocess
import os
import tempfile
import io
import gc
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path
from streamlit_sortables import sort_items

# ページの基本設定
st.set_page_config(page_title="PDFプロ編集スタジオ", layout="wide")

st.title("🛡️ PDFプロ・編集スタジオ（超安定・高速版）")
st.write("画像を「必要な時だけ」作るようにしたよ。これで100ページ超えのエクセルも安心！")

# --- 1. 魔法のメモ帳（セッションステート） ---
if "page_list" not in st.session_state:
    st.session_state.page_list = [] # ページの情報
if "file_vault" not in st.session_state:
    st.session_state.file_vault = {} # ファイルのデータ本体
if "active_zoom_index" not in st.session_state:
    st.session_state.active_zoom_index = None

# --- 2. 拡大編集画面（ダイアログ） ---
@st.dialog("ページを確認・編集", width="large")
def zoom_edit_modal():
    idx = st.session_state.active_zoom_index
    if idx is None or idx >= len(st.session_state.page_list):
        st.session_state.active_zoom_index = None
        st.rerun()
        return

    page = st.session_state.page_list[idx]
    
    # 操作ボタン
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
    
    # 🌟 この瞬間だけ画像を作る（メモリ節約！）
    with st.spinner("画像を読み込み中..."):
        try:
            pdf_data = st.session_state.file_vault[page["filename"]]
            # 指定した1ページだけを画像にする
            imgs = convert_from_path(io.BytesIO(pdf_data), first_page=page["page_num"], last_page=page["page_num"], size=(1200, None))
            if imgs:
                display_img = imgs[0].rotate(-page["rotate"], expand=True)
                if not page["active"]:
                    display_img = display_img.convert("L")
                    st.warning("⚠️ このページは削除設定中です")
                st.image(display_img, use_container_width=True)
                st.caption(f"ファイル: {page['filename']} (P.{page['page_num']})")
        except Exception as e:
            st.error(f"プレビューの作成に失敗しました。ファイルが壊れているか、大きすぎます。")

# 拡大画面を表示中なら呼び出す
if st.session_state.active_zoom_index is not None:
    zoom_edit_modal()

# --- 3. サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    if st.button("♻️ 最初からやり直す"):
        st.session_state.page_list = []
        st.session_state.file_vault = {}
        st.session_state.active_zoom_index = None
        gc.collect()
        st.rerun()
    st.divider()
    use_ocr = st.checkbox("OCR（文字読み取り）をかける")

# --- 4. ファイル読み込み ---
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
                        # タイムアウトを設定して固まらないようにする
                        try:
                            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)], timeout=60)
                            pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                        except:
                            st.error(f"{uploaded_file.name} の変換に失敗しました。")
                            continue
                    
                    if pdf_path.exists():
                        with open(pdf_path, "rb") as f:
                            pdf_bytes = f.read()
                        
                        st.session_state.file_vault[uploaded_file.name] = pdf_bytes
                        
                        # 🌟 画像は作らず、ページの情報（番号）だけを登録する
                        reader = PdfReader(io.BytesIO(pdf_bytes))
                        page_count = len(reader.pages)
                        for i in range(page_count):
                            st.session_state.page_list.append({
                                "id": f"{uploaded_file.name}_P{i+1}_{os.urandom(2).hex()}",
                                "filename": uploaded_file.name,
                                "page_num": i + 1,
                                "active": True,
                                "rotate": 0
                            })
                        del pdf_bytes
                gc.collect()
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
    
    # 6列のグリッド
    rows = [st.session_state.page_list[i:i+6] for i in range(0, len(st.session_state.page_list), 6)]
    for row_idx, row_pages in enumerate(rows):
        cols = st.columns(6)
        for i, page in enumerate(row_pages):
            idx = st.session_state.page_list.index(page)
            with cols[i]:
                # 🌟 画像の代わりに「カード」を表示
                with st.container(border=True):
                    st.write(f"**P.{page['page_num']}**")
                    st.caption(f"{page['filename'][:15]}...")
                    if not page["active"]:
                        st.write("❌ 削除中")
                    if page["rotate"] != 0:
                        st.write(f"🔄 {page['rotate']}°")
                    
                    # 操作ボタン
                    if st.button("🔍 表示/編集", key=f"z_btn_{page['id']}", use_container_width=True):
                        st.session_state.active_zoom_index = idx
                        st.rerun()

    # --- 6. 最終合体 ---
    st.divider()
    st.subheader("🏁 仕上げ")
    custom_filename = st.text_input("💾 保存するファイルの名前", value="merged_document")
    
    if st.button("🚀 PDFを作成してダウンロード", type="primary", use_container_width=True):
        active_pages = [p for p in st.session_state.page_list if p["active"]]
        if not active_pages:
            st.warning("使うページをえらんでね。")
        else:
            with st.spinner("PDFを作成中... しばらく待ってね"):
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
                        
                        temp_p = save_dir_path / f"temp_{i}.pdf"
                        with open(temp_p, "wb") as f:
                            writer.write(f)
                        
                        if use_ocr:
                            ocr_p = save_dir_path / f"ocr_{i}.pdf"
                            subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(temp_p), str(ocr_p)])
                            temp_p = ocr_p
                        
                        final_merger.append(str(temp_p))
                    
                    out_io = io.BytesIO()
                    final_merger.write(out_io)
                    f_name = custom_filename if custom_filename.endswith(".pdf") else f"{custom_filename}.pdf"
                    st.success("🎉 かんせい！下のボタンから受け取ってね。")
                    st.download_button("📥 ダウンロード", out_io.getvalue(), f_name)
