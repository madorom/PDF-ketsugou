import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDF超編集スタジオ", layout="wide")

st.title("✂️ PDF切り貼り・合体スタジオ")
st.write("いらないページを捨てたり、向きを変えたり、自由自在に編集しよう！")

# 1. ファイルをアップロード
uploaded_files = st.file_uploader(
    "ファイルをえらんでね（Word, Excel, PPT, PDF）", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

# 状態を保存するための変数
if "page_settings" not in st.session_state:
    st.session_state.page_settings = {}

if uploaded_files:
    ready_pdfs = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for uploaded_file in uploaded_files:
            f_key = uploaded_file.name
            st.subheader(f"📂 ファイル: {f_key}")
            
            # --- ステップA: PDFに変換する ---
            input_path = temp_dir_path / uploaded_file.name
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            current_pdf = input_path
            if input_path.suffix.lower() != ".pdf":
                with st.spinner("PDFに変換中..."):
                    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                    current_pdf = temp_dir_path / (input_path.stem + ".pdf")

            # PDFの情報を読み取る
            reader = PdfReader(current_pdf)
            num_pages = len(reader.pages)

            # --- ステップB: ページの選択と回転 ---
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.write(f"このファイルは全部で **{num_pages}ページ** あります。")
                
                # 使うページをえらぶ
                selected_pages = st.multiselect(
                    "使うページをえらんでね（空っぽにすると全部使います）",
                    range(1, num_pages + 1),
                    default=range(1, num_pages + 1),
                    key=f"pages_{f_key}"
                )
                
                # 向きをかえる
                rotate_val = st.radio(
                    "向きをかえる", [0, 90, 180, 270], index=0, 
                    key=f"rot_{f_key}", horizontal=True
                )
            
            with col2:
                # 代表して1ページ目だけプレビュー
                try:
                    images = convert_from_path(current_pdf, first_page=1, last_page=1, size=(250, None))
                    if images:
                        img = images[0].rotate(-rotate_val, expand=True)
                        st.image(img, caption="1ページ目のプレビュー")
                except:
                    st.write("（プレビューは出せませんでした）")

            ready_pdfs.append({
                "path": current_pdf,
                "name": f_key,
                "keep_pages": selected_pages,
                "rotation": rotate_val
            })

        st.divider()
        
        # --- ステップC: 最終合体 ---
        use_ocr = st.checkbox("OCR（文字をよみとる）をかける")
        
        if st.button("🚀 編集をすべて反映して合体！", type="primary"):
            merger = PdfWriter()
            
            for item in ready_pdfs:
                reader = PdfReader(item["path"])
                writer = PdfWriter()
                
                # 選んだページだけを抜き出す
                # プログラミングは0から数えるので -1 します
                pages_to_add = [p - 1 for p in item["keep_pages"]]
                
                for idx in pages_to_add:
                    page = reader.pages[idx]
                    page.rotate(item["rotation"]) # 回転させる
                    writer.add_page(page)
                
                # 一時保存
                temp_output = temp_dir_path / f"mod_{item['name']}.pdf"
                with open(temp_output, "wb") as f:
                    writer.write(f)
                
                final_path = temp_output

                # OCRが必要な場合
                if use_ocr:
                    st.write(f"👁️ {item['name']} を読み取り中...")
                    ocr_pdf = temp_dir_path / f"ocr_{item['name']}.pdf"
                    subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_pdf)])
                    if ocr_pdf.exists():
                        final_path = ocr_pdf
                
                merger.append(str(final_path))

            # 最後の保存
            result_path = temp_dir_path / "final.pdf"
            with open(result_path, "wb") as f:
                merger.write(f)
            
            st.success("🎉 完ぺきです！いらないページを捨てて合体しました！")
            with open(result_path, "rb") as f:
                st.download_button("完成したPDFをもらう", f.read(), "edited_document.pdf")
