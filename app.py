import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDF超編集スタジオ", layout="wide")

st.title("📖 PDFページ確認・編集スタジオ")
st.write("スライダーを動かして、全ページの中身を確認できるよ！")

# 1. ファイルをアップロード
uploaded_files = st.file_uploader(
    "ファイルをえらんでね", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

if uploaded_files:
    ready_pdfs = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for uploaded_file in uploaded_files:
            f_key = uploaded_file.name
            st.divider() # 区切り線
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

            # --- ステップB: ページの選択・回転・プレビュー ---
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.write(f"全部で **{num_pages}ページ** あります。")
                
                # 🌟 新機能：見たいページをえらぶスライダー
                preview_page = st.slider(
                    "プレビューするページをめくる", 
                    min_value=1, 
                    max_value=num_pages, 
                    value=1, 
                    key=f"slide_{f_key}"
                )
                
                # 使うページをえらぶ
                selected_pages = st.multiselect(
                    "合体させるページをえらんでね",
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
                # 🌟 スライダーで選んだページを画像にして見せる
                try:
                    with st.spinner("ページを表示中..."):
                        images = convert_from_path(
                            current_pdf, 
                            first_page=preview_page, # スライダーの数字を使う
                            last_page=preview_page,  # スライダーの数字を使う
                            size=(400, None)
                        )
                        if images:
                            img = images[0].rotate(-rotate_val, expand=True)
                            st.image(img, caption=f"{f_key} の {preview_page} ページ目")
                except Exception as e:
                    st.error("プレビューが出せませんでした。ファイルが重すぎるかもしれません。")

            ready_pdfs.append({
                "path": current_pdf,
                "name": f_key,
                "keep_pages": selected_pages,
                "rotation": rotate_val
            })

        # --- ステップC: 最終合体 ---
        st.divider()
        use_ocr = st.checkbox("OCR（文字をよみとる）を全ページにかける")
        
        if st.button("🚀 この内容でPDFを作成する", type="primary", use_container_width=True):
            merger = PdfWriter()
            
            for item in ready_pdfs:
                reader = PdfReader(item["path"])
                writer = PdfWriter()
                
                pages_to_add = [p - 1 for p in item["keep_pages"]]
                for idx in pages_to_add:
                    page = reader.pages[idx]
                    page.rotate(item["rotation"])
                    writer.add_page(page)
                
                temp_output = temp_dir_path / f"mod_{item['name']}.pdf"
                with open(temp_output, "wb") as f:
                    writer.write(f)
                
                final_path = temp_output

                if use_ocr:
                    st.write(f"👁️ {item['name']} を読み取り中...")
                    ocr_pdf = temp_dir_path / f"ocr_{item['name']}.pdf"
                    subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_pdf)])
                    if ocr_pdf.exists():
                        final_path = ocr_pdf
                
                merger.append(str(final_path))

            result_path = temp_dir_path / "final.pdf"
            with open(result_path, "wb") as f:
                merger.write(f)
            
            st.success("🎉 完ぺきなPDFができあがりました！")
            with open(result_path, "rb") as f:
                st.download_button("完成したPDFをダウンロード", f.read(), "my_edited_pdf.pdf")
