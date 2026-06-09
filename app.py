import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter
from pathlib import Path

# アプリのタイトル
st.title("📄 なかよしPDF合体マシン")
st.write("ワード、エクセル、パワポをえらんでね！ぜんぶPDFにして合体するよ！")

# ファイルを選ぶ場所
uploaded_files = st.file_uploader(
    "合体させたいファイルをえらんでね", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

# 合体ボタンが押されたときの動き
if uploaded_files:
    if st.button("まほうをかける（PDFにして合体！）"):
        merger = PdfWriter()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            for uploaded_file in uploaded_files:
                input_path = temp_dir_path / uploaded_file.name
                with open(input_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                # PDFじゃないファイルはPDFにへんかんする
                if input_path.suffix.lower() == ".pdf":
                    merger.append(str(input_path))
                else:
                    # LibreOfficeという道具を使ってへんかん！
                    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                    converted_pdf = temp_dir_path / (input_path.stem + ".pdf")
                    if converted_pdf.exists():
                        merger.append(str(converted_pdf))

            # できたPDFを保存
            output_pdf_path = temp_dir_path / "result.pdf"
            with open(output_pdf_path, "wb") as f:
                merger.write(f)
            
            # ダウンロードボタンを出す
            with open(output_pdf_path, "rb") as f:
                st.download_button(label="できたPDFをもらう", data=f.read(), file_name="gattas-pdf.pdf")
            st.success("かんせい！")