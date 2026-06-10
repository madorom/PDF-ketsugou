import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDF編集スタジオ", layout="wide")

st.title("🎨 PDF編集・合体スタジオ")
st.write("ファイルごとに中身を確認して、向きを変えられるよ！")

# 1. ファイルをアップロード
uploaded_files = st.file_uploader(
    "ファイルをえらんでね（Word, Excel, PPT, PDF）", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

# 状態を保存するための変数（セッションステート）
if "rotations" not in st.session_state:
    st.session_state.rotations = {}

if uploaded_files:
    # 準備ができたPDFたちを保存する場所
    ready_pdfs = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        # 各ファイルの処理
        for uploaded_file in uploaded_files:
            file_key = uploaded_file.name
            st.subheader(f"📂 ファイル: {file_key}")
            
            # --- ステップA: PDFに変換する ---
            input_path = temp_dir_path / uploaded_file.name
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            current_pdf = input_path
            if input_path.suffix.lower() != ".pdf":
                with st.spinner(f"{file_key} をPDFに変換中..."):
                    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                    current_pdf = temp_dir_path / (input_path.stem + ".pdf")

            # --- ステップB: プレビューと回転設定 ---
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 何度回すか選ぶボタン
                rotate_val = st.radio(
                    f"向きをかえる ({file_key})",
                    [0, 90, 180, 270],
                    index=0,
                    key=f"rot_{file_key}",
                    horizontal=True
                )
                st.session_state.rotations[file_key] = rotate_val
            
            with col2:
                # PDFの1ページ目を画像にして見せる
                try:
                    images = convert_from_path(current_pdf, first_page=1, last_page=1, size=(300, None))
                    if images:
                        img = images[0].rotate(-rotate_val, expand=True) # プレビューも回す
                        st.image(img, caption="1ページ目のプレビュー")
                except:
                    st.warning("プレビューが表示できませんでした")

            ready_pdfs.append((current_pdf, file_key))

        st.divider()
        
        # --- ステップC: OCR設定と最終合体 ---
        use_ocr = st.checkbox("OCR（文字をよみとる）を全ページにかける")
        
        if st.button("✨ ぜんぶ合体して保存する", type="primary"):
            merger = PdfWriter()
            progress_bar = st.progress(0)

            for i, (pdf_path, f_key) in enumerate(ready_pdfs):
                # 回転を適用
                reader = PdfReader(pdf_path)
                writer = PdfWriter()
                rot = st.session_state.rotations.get(f_key, 0)

                for page in reader.pages:
                    page.rotate(rot)
                    writer.add_page(page)
                
                rotated_pdf = temp_dir_path / f"final_{f_key}.pdf"
                with open(rotated_pdf, "wb") as f:
                    writer.write(f)
                
                final_path = rotated_pdf

                # OCRが必要な場合
                if use_ocr:
                    st.write(f"👁️ {f_key} を読み取り中...")
                    ocr_pdf = temp_dir_path / f"ocr_{f_key}.pdf"
                    subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_pdf)])
                    if ocr_pdf.exists():
                        final_path = ocr_pdf
                
                merger.append(str(final_path))
                progress_bar.progress((i + 1) / len(ready_pdfs))

            # 合体完了
            output_pdf_path = temp_dir_path / "studio_result.pdf"
            with open(output_pdf_path, "wb") as f:
                merger.write(f)
            
            st.success("🎉 すべての作業が完了しました！")
            with open(output_pdf_path, "rb") as f:
                st.download_button("完成したPDFをダウンロード", f.read(), "final_document.pdf")
