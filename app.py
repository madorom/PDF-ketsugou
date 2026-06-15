import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDF超編集スタジオ", layout="wide")

st.title("🔍 PDF拡大・ページめくりスタジオ")
st.write("ボタンでページをめくったり、虫めがねで大きくしたりできるよ！")

# --- 魔法の「しおり」を準備する（何ページ目か覚えておくため） ---
if "page_numbers" not in st.session_state:
    st.session_state.page_numbers = {}

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
            st.divider()
            st.subheader(f"📂 ファイル: {f_key}")
            
            # PDFに変換する処理
            input_path = temp_dir_path / uploaded_file.name
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            current_pdf = input_path
            if input_path.suffix.lower() != ".pdf":
                with st.spinner("PDFに変換中..."):
                    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])
                    current_pdf = temp_dir_path / (input_path.stem + ".pdf")

            reader = PdfReader(current_pdf)
            num_pages = len(reader.pages)

            # このファイルの現在のページを「しおり」から取り出す
            if f_key not in st.session_state.page_numbers:
                st.session_state.page_numbers[f_key] = 1
            
            current_p = st.session_state.page_numbers[f_key]

            # --- 左側の設定メニュー ---
            col_settings, col_viewer = st.columns([1, 2])
            
            with col_settings:
                st.write(f"全 **{num_pages}** ページ")
                
                # 🌟 【新機能】ページめくりボタン
                c1, c2, c3 = st.columns([1, 2, 1])
                with c1:
                    if st.button("⬅️ 前へ", key=f"prev_{f_key}"):
                        if st.session_state.page_numbers[f_key] > 1:
                            st.session_state.page_numbers[f_key] -= 1
                            st.rerun() # 画面を更新してページをめくる
                with c2:
                    st.write(f"**{st.session_state.page_numbers[f_key]} / {num_pages}**")
                with c3:
                    if st.button("次へ ➡️", key=f"next_{f_key}"):
                        if st.session_state.page_numbers[f_key] < num_pages:
                            st.session_state.page_numbers[f_key] += 1
                            st.rerun() # 画面を更新してページをめくる

                # 🌟 スライダーでも動かせるようにする
                if num_pages > 1:
                    st.session_state.page_numbers[f_key] = st.slider(
                        "スライダーでめくる", 1, num_pages, 
                        value=st.session_state.page_numbers[f_key],
                        key=f"slide_{f_key}"
                    )

                # 🌟 【新機能】虫めがね（拡大）スライダー
                zoom_size = st.slider("🔍 大きさをかえる（拡大）", 300, 1200, 500, step=50, key=f"zoom_{f_key}")

                # ページ選びと向き
                selected_pages = st.multiselect(
                    "合体させるページ", range(1, num_pages + 1),
                    default=range(1, num_pages + 1), key=f"sel_{f_key}"
                )
                rotate_val = st.radio(
                    "向き", [0, 90, 180, 270], index=0, key=f"rot_{f_key}", horizontal=True
                )
            
            # --- 右側のプレビュー表示 ---
            with col_viewer:
                try:
                    with st.spinner("ページを表示中..."):
                        p_to_show = st.session_state.page_numbers[f_key]
                        # PDFを画像にする
                        images = convert_from_path(current_pdf, first_page=p_to_show, last_page=p_to_show)
                        if images:
                            img = images[0].rotate(-rotate_val, expand=True)
                            # 🌟 指定したズームサイズで表示する
                            st.image(img, width=zoom_size)
                except:
                    st.error("プレビューが見られませんでした。")

            ready_pdfs.append({
                "path": current_pdf, "name": f_key,
                "keep_pages": selected_pages, "rotation": rotate_val
            })

        # --- 合体ボタン ---
        st.divider()
        use_ocr = st.checkbox("OCR（文字を読み取る）をかける")
        if st.button("🚀 この内容でPDFを合体する", type="primary", use_container_width=True):
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
            st.success("🎉 完璧なPDFが完成しました！")
            with open(result_path, "rb") as f:
                st.download_button("完成したPDFをダウンロード", f.read(), "ultra_pdf.pdf")
