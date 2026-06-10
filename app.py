import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path

st.set_page_config(page_title="進化版！PDF合体マシン", layout="centered")

st.title("🚀 進化版！PDFなかよし合体マシン")
st.write("向きを変えたり、文字を読み取れるようになったよ！")

# --- 設定コーナー ---
st.sidebar.header("🛠 まほうの設定")
rotation = st.sidebar.selectbox("向きをかえる", [0, 90, 180, 270], index=0, help="右に何回まわすか選んでね")
use_ocr = st.sidebar.checkbox("OCR（文字をよみとる）", value=False, help="チェックを入れると、画像の中の文字がさがせるようになるよ！少し時間がかかるからね。")

# --- ファイル選び ---
uploaded_files = st.file_uploader(
    "合体させたいファイルをえらんでね", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("まほうを実行！"):
        merger = PdfWriter()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            progress_bar = st.progress(0)
            
            for i, uploaded_file in enumerate(uploaded_files):
                input_path = temp_dir_path / uploaded_file.name
                with open(input_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # 1. OfficeファイルをPDFにする
                current_pdf = input_path
                if input_path.suffix.lower() != ".pdf":
                    st.write(f"🔧 {uploaded_file.name} をPDFにしています...")
                    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                    current_pdf = temp_dir_path / (input_path.stem + ".pdf")

                # 2. 向きをかえる（回転）
                if rotation != 0:
                    st.write(f"🔄 {uploaded_file.name} を回転させています...")
                    reader = PdfReader(current_pdf)
                    writer = PdfWriter()
                    for page in reader.pages:
                        page.rotate(rotation)
                        writer.add_page(page)
                    rotated_pdf = temp_dir_path / f"rotated_{current_pdf.name}"
                    with open(rotated_pdf, "wb") as f:
                        writer.write(f)
                    current_pdf = rotated_pdf

                # 3. OCR（文字を読み取る）
                if use_ocr:
                    st.write(f"👁️ {uploaded_file.name} の文字を読み取っています（時間がかかるよ）...")
                    ocr_pdf = temp_dir_path / f"ocr_{current_pdf.name}"
                    # ocrmypdfコマンドを実行
                    subprocess.run([
                        "ocrmypdf", 
                        "-l", "jpn+eng", # 日本語と英語
                        "--force-ocr",   # 画像だったら読み取る
                        str(current_pdf), 
                        str(ocr_pdf)
                    ])
                    if ocr_pdf.exists():
                        current_pdf = ocr_pdf

                merger.append(str(current_pdf))
                progress_bar.progress((i + 1) / len(uploaded_files))

            # 最後のごうたい
            output_pdf_path = temp_dir_path / "final_result.pdf"
            with open(output_pdf_path, "wb") as f:
                merger.write(f)
            
            st.success("✨ かんせい！")
            with open(output_pdf_path, "rb") as f:
                st.download_button(label="できあがったPDFをもらう", data=f.read(), file_name="super-pdf.pdf")
