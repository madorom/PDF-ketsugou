import streamlit as st
import subprocess
import os
import tempfile
from pypdf import PdfWriter, PdfReader
from pathlib import Path
from pdf2image import convert_from_path

st.set_page_config(page_title="PDFページ編集プロ", layout="wide")

st.title("✂️ PDFページ別・編集スタジオ")
st.write("ページごとに「削除」や「回転」がポチポチできるよ！")

# --- 魔法の「ページ管理帳」を準備する ---
if "pdf_data" not in st.session_state:
    st.session_state.pdf_data = {} # ファイルごとの情報を入れる
if "global_zoom" not in st.session_state:
    st.session_state.global_zoom = 600

uploaded_files = st.file_uploader(
    "ファイルをえらんでね", 
    type=["pdf", "docx", "xlsx", "pptx"], 
    accept_multiple_files=True
)

if uploaded_files:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)

        for uploaded_file in uploaded_files:
            f_key = uploaded_file.name
            st.divider()
            st.subheader(f"📂 ファイル: {f_key}")
            
            # --- 1. PDFに変換する（初回だけ） ---
            input_path = temp_dir_path / f_key
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            pdf_path = input_path
            if input_path.suffix.lower() != ".pdf":
                pdf_path = temp_dir_path / (input_path.stem + ".pdf")
                if not pdf_path.exists():
                    with st.spinner("PDFに変換中..."):
                        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir_path), str(input_path)])

            # --- 2. ページ情報を管理帳に登録する（初回だけ） ---
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            
            if f_key not in st.session_state.pdf_data:
                # ページごとの設定（回転0度、削除なし）を初期化
                st.session_state.pdf_data[f_key] = {
                    "path": str(pdf_path),
                    "current_page": 1,
                    "pages": {p: {"rotate": 0, "active": True} for p in range(1, num_pages + 1)}
                }

            file_info = st.session_state.pdf_data[f_key]
            curr_p = file_info["current_page"]
            page_settings = file_info["pages"][curr_p]

            # --- 3. 画面のレイアウト ---
            col_ctrl, col_view = st.columns([1, 2])

            with col_ctrl:
                st.write(f"ページ: **{curr_p} / {num_pages}**")
                
                # ページめくりボタン
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("⬅️ 前へ", key=f"prev_{f_key}"):
                        if curr_p > 1:
                            file_info["current_page"] -= 1
                            st.rerun()
                with c2:
                    if st.button("次へ ➡️", key=f"next_{f_key}"):
                        if curr_p < num_pages:
                            file_info["current_page"] += 1
                            st.rerun()

                st.divider()

                # 🌟 このページ専用の操作ボタン
                status = "✅ 使う" if page_settings["active"] else "❌ 削除済み"
                st.write(f"このページの状態: **{status}**")
                
                if st.button("🗑️ このページを 削除/復活" , key=f"del_{f_key}"):
                    page_settings["active"] = not page_settings["active"]
                    st.rerun()

                if st.button("🔄 右に90度まわす", key=f"rot_{f_key}"):
                    page_settings["rotate"] = (page_settings["rotate"] + 90) % 360
                    st.rerun()

                st.divider()
                # 拡大率（全体共通）
                st.session_state.global_zoom = st.slider("🔍 ズーム", 300, 1500, st.session_state.global_zoom, key=f"zoom_{f_key}")

            with col_view:
                # プレビュー表示
                try:
                    images = convert_from_path(pdf_path, first_page=curr_p, last_page=curr_p)
                    if images:
                        # ページごとの回転を反映して表示
                        img = images[0].rotate(-page_settings["rotate"], expand=True)
                        # 削除済みの場合は白黒っぽくする（薄くする）
                        if not page_settings["active"]:
                            img = img.convert("L").convert("RGB") 
                            st.image(img, width=st.session_state.global_zoom, caption="⚠️ このページは削除されます")
                        else:
                            st.image(img, width=st.session_state.global_zoom)
                except:
                    st.error("プレビューエラー")

        # --- 4. 最終的な合体ボタン ---
        st.divider()
        st.subheader("🏁 仕上げ")
        use_ocr = st.checkbox("OCR（文字を読み取る）をかける")
        
        if st.button("🚀 編集をすべて反映してPDFを作る", type="primary", use_container_width=True):
            final_merger = PdfWriter()
            
            for f_name, info in st.session_state.pdf_data.items():
                temp_reader = PdfReader(info["path"])
                temp_writer = PdfWriter()
                
                added_count = 0
                for p_num, settings in info["pages"].items():
                    if settings["active"]:
                        # 使うページだけを取り出して、そのページの設定で回す
                        page_obj = temp_reader.pages[p_num - 1]
                        page_obj.rotate(settings["rotate"])
                        temp_writer.add_page(page_obj)
                        added_count += 1
                
                if added_count > 0:
                    # 一時ファイルに保存
                    p_out = temp_dir_path / f"final_{f_name}.pdf"
                    with open(p_out, "wb") as f:
                        temp_writer.write(f)
                    
                    final_path = p_out
                    if use_ocr:
                        st.write(f"👁️ {f_name} を読み取り中...")
                        ocr_p = temp_dir_path / f"ocr_{f_name}.pdf"
                        subprocess.run(["ocrmypdf", "-l", "jpn+eng", "--force-ocr", str(final_path), str(ocr_p)])
                        if ocr_p.exists():
                            final_path = ocr_p
                    
                    final_merger.append(str(final_path))
            
            # まとめて保存
            result_file = temp_dir_path / "studio_final.pdf"
            with open(result_file, "wb") as f:
                final_merger.write(f)
            
            st.success("🎉 完璧です！あなたの指示通りにPDFを組み立てました！")
            with open(result_file, "rb") as f:
                st.download_button("完成したPDFをダウンロード", f.read(), "my_edited_pdf.pdf")
