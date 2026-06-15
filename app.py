import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDFグリッド編集スタジオ", layout="wide")

st.title("🖼️ PDFグリッド編集スタジオ")
st.write("すべてのページを一覧で確認しながら、直感的に編集できるよ！")

# --- 魔法のメモ帳（セッションステート）の準備 ---
if "all_pages_data" not in st.session_state:
    st.session_state.all_pages_data = [] # 全ページの情報を入れるリスト
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 250 # デフォルトのカードサイズ

# --- サイドバー：全体の設定 ---
with st.sidebar:
    st.header("🛠️ 全体の設定")
    # 🌟 拡大率をここで一括管理（ページを動かしてもリセットされません）
    st.session_state.global_zoom = st.slider(
        "🔍 カードの大きさ（ズーム）", 150, 800, st.session_state.global_zoom
    )
    
    st.divider()
    use_ocr = st.checkbox("OCR（文字読み取り）をかける")
    
    if st.button("🗑️ データをリセットして最初からやり直す"):
        st.session_state.all_pages_data = []
        st.rerun()

# --- ファイルのアップロード ---
uploaded_files = st.file_uploader(
    "ファイルをえらんでね（Word, Excel, PPT, PDF）", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

# ファイルが新しく追加されたら、ページごとに分解して登録する
if uploaded_files:
    # まだ登録されていないファイルがあるかチェック
    existing_filenames = [p["filename"] for p in st.session_state.all_pages_data]
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        
        for uploaded_file in uploaded_files:
            if uploaded_file.name not in existing_filenames:
                with st.spinner(f"{uploaded_file.name} を準備中..."):
                    # 一時保存とPDF変換
                    input_path = temp_dir_path / uploaded_file.name
                    with open(input_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    pdf_path = input_path
                    if input_path.suffix.lower() != ".pdf":
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                        pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                    
                    # ページごとに画像化してメモリに保存
                    reader = PdfReader(pdf_path)
                    # 全ページを画像に変換（プレビュー用）
                    images = convert_from_path(pdf_path, size=(800, None))
                    
                    for i, img in enumerate(images):
                        page_num = i + 1
                        st.session_state.all_pages_data.append({
                            "filename": uploaded_file.name,
                            "page_num": page_num,
                            "img": img,      # 画像データそのものを保持
                            "pdf_path": str(pdf_path), # 元PDFのパス（結合用）
                            "active": True,  # 使うかどうか
                            "rotate": 0      # 向き
                        })
                st.rerun()

# --- ページ一覧の表示（グリッドレイアウト） ---
if st.session_state.all_pages_data:
    st.subheader("📄 ページ一覧（クリックで編集）")
    
    # 4列のグリッドを作る
    cols = st.columns(4) 
    
    for idx, page in enumerate(st.session_state.all_pages_data):
        with cols[idx % 4]: # 4つごとに次の行へ
            # カードのような枠を作る
            with st.container(border=True):
                # プレビュー画像（回転を反映）
                display_img = page["img"].rotate(-page["rotate"], expand=True)
                
                # 削除済みの場合は薄くする
                if not page["active"]:
                    display_img = display_img.convert("L") # 白黒にする
                    st.image(display_img, width=st.session_state.global_zoom, use_container_width=True)
                    st.caption(f"❌ 削除済み: {page['filename']} (P.{page['page_num']})")
                else:
                    st.image(display_img, width=st.session_state.global_zoom, use_container_width=True)
                    st.caption(f"📄 {page['filename']} (P.{page['page_num']})")
                
                # 操作ボタン（横並び）
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("🗑️ 削除" if page["active"] else "✅ 復活", key=f"del_{idx}"):
                        page["active"] = not page["active"]
                        st.rerun()
                with b2:
                    if st.button("🔄 回転", key=f"rot_{idx}"):
                        page["rotate"] = (page["rotate"] + 90) % 360
                        st.rerun()

    # --- 仕上げの合体 ---
    st.divider()
    if st.button("🚀 この内容でPDFを作成してダウンロード", type="primary", use_container_width=True):
        final_merger = PdfWriter()
        
        # 変換用の一時ディレクトリを再度作成
        with tempfile.TemporaryDirectory() as save_dir:
            save_dir_path = Path(save_dir)
            
            # 各ファイルのPDFを読み込んで、アクティブなページだけを結合
            # 注意：pdf_pathは一時的なものなので、必要に応じて再読み込みが必要な場合がありますが、
            # Streamlit Cloud上では実行中に保持されます。
            
            # ファイルごとにまとめて処理
            current_file = ""
            temp_reader = None
            
            for page in st.session_state.all_pages_data:
                if page["active"]:
                    # 同じファイルが続く間はreaderを使い回す
                    reader = PdfReader(page["pdf_path"])
                    temp_writer = PdfWriter()
                    
                    page_obj = reader.pages[page["page_num"] - 1]
                    page_obj.rotate(page["rotate"])
                    temp_writer.add_page(page_obj)
                    
                    # 一時的に1ページだけのPDFを作る
                    temp_p = save_dir_path / f"temp_{idx}.pdf"
                    with open(temp_p, "wb") as f:
                        temp_writer.write(f)
                    
                    final_path = temp_p
                    if use_ocr:
                        ocr_p = save_dir_path / f"ocr_{idx}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_p)])
                        final_path = ocr_p
                    
                    final_merger.append(str(final_path))
            
            # 最後の保存
            result_file = save_dir_path / "final.pdf"
            with open(result_file, "wb") as f:
                final_merger.write(f)
            
            st.success("🎉 完成しました！")
            with open(result_file, "rb") as f:
                st.download_button("📥 編集済みPDFを保存する", f.read(), "my_best_pdf.pdf")

else:
    st.info("上のボタンからファイルをアップロードしてね！")
