import gc
import math
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

import streamlit as st
from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader, PdfWriter
from streamlit_sortables import sort_items

st.set_page_config(page_title="PDF結合", page_icon="📄", layout="wide")
st.markdown("""
<style>
.stApp {background: #f7f8fc;}
.block-container {max-width: 1150px; padding-top: 2.5rem;}
h1 {letter-spacing: -.04em;}
div[data-testid="stVerticalBlockBorderWrapper"] {background: white; border-radius: 14px;}
div[data-testid="stFileUploader"] {background: white; border-radius: 14px; padding: 12px;}
div.stButton > button[kind="primary"] {background: #e44747; border-color: #e44747;}
</style>
""", unsafe_allow_html=True)

# TemporaryDirectory cleans up when the session releases this object.
if "pdf_workspace_v2" not in st.session_state:
    st.session_state.pdf_workspace_v2 = tempfile.TemporaryDirectory(prefix="pdf-merge-")
    st.session_state.documents = []
    st.session_state.upload_seen = set()
    st.session_state.upload_epoch = 0
    st.session_state.order_epoch = 0
    st.session_state.result_path = None
    st.session_state.result_signature = None

root = Path(st.session_state.pdf_workspace_v2.name)


def invalidate():
    st.session_state.result_signature = None
    st.session_state.order_epoch += 1


def run_command(command, timeout):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(f"必要なツールが見つかりません: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("処理が制限時間を超えました。ファイルを小さくしてお試しください。") from exc
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "外部ツールの処理に失敗しました。")[-1200:])


def import_document(upload):
    folder = root / uuid4().hex
    folder.mkdir()
    try:
        source = folder / ("source" + Path(upload.name).suffix.lower())
        upload.seek(0)
        with source.open("wb") as output:
            shutil.copyfileobj(upload, output, length=1024 * 1024)
        pdf = source
        if source.suffix != ".pdf":
            profile = (folder / "lo-profile").as_uri()
            run_command(["soffice", f"-env:UserInstallation={profile}", "--headless",
                         "--convert-to", "pdf", "--outdir", str(folder), str(source)], 120)
            pdf = folder / "source.pdf"
        if not pdf.is_file():
            raise RuntimeError("PDFへの変換結果を確認できませんでした。")
        with pdf.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted and not reader.decrypt(""):
                raise RuntimeError("パスワード付きPDFは、解除してから追加してください。")
            count = len(reader.pages)
        if not count:
            raise RuntimeError("ページがありません。")
        return {"id": folder.name, "name": upload.name, "path": str(pdf),
                "pages": [{"number": n, "rotation": 0, "active": True} for n in range(1, count + 1)]}
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def preview(document, page, size=240):
    # Cache JPEGs on disk rather than retaining every page as a PIL image.
    target = Path(document["path"]).parent / f"preview-{page['number']}-{page['rotation']}-{size}.jpg"
    if not target.exists():
        paths = convert_from_path(document["path"], first_page=page["number"],
                                  last_page=page["number"], size=size, fmt="jpeg",
                                  output_folder=str(target.parent), paths_only=True,
                                  thread_count=1, timeout=45)
        try:
            with Image.open(paths[0]) as source:
                rotated = source.rotate(-page["rotation"], expand=True)
                try:
                    rotated.save(target, "JPEG", quality=80)
                finally:
                    rotated.close()
        finally:
            for path in paths:
                Path(path).unlink(missing_ok=True)
    return str(target)


def show_preview(document, page, size=240):
    try:
        st.image(preview(document, page, size), use_container_width=True)
    except Exception:
        st.caption("📄 プレビューを作成できません。結合は引き続きお試しいただけます。")


def merge_documents(documents, destination):
    # One reader per document; keep its stream open until the writer finishes.
    writer = PdfWriter()
    try:
        with ExitStack() as stack:
            for document in documents:
                stream = stack.enter_context(open(document["path"], "rb"))
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    reader.decrypt("")
                for page in document["pages"]:
                    if page["active"]:
                        original = reader.pages[page["number"] - 1]
                        added = writer.add_page(original)
                        if page["rotation"]:
                            added.rotate(page["rotation"])
            with open(destination, "wb") as output:
                writer.write(output)
    finally:
        writer.close()


@st.dialog("ページを編集", width="large")
def edit_document(document_id):
    document = next((d for d in st.session_state.documents if d["id"] == document_id), None)
    if document is None:
        return
    st.write(document["name"])
    st.caption("ページをドラッグして並べ替えられます。除外したページはもう一度押すと戻せます。")
    labels = [f"P.{p['number']}" for p in document["pages"]]
    ordered = sort_items(labels, direction="horizontal",
                         key=f"pages-{document_id}-{st.session_state.order_epoch}")
    if ordered != labels and sorted(ordered) == sorted(labels):
        by_label = dict(zip(labels, document["pages"]))
        document["pages"] = [by_label[label] for label in ordered]
        invalidate()
        st.rerun()
    total = len(document["pages"])
    batch = int(st.number_input("表示範囲（1画面12ページ）", min_value=1,
                               max_value=max(1, math.ceil(total / 12)), value=1,
                               key=f"batch-{document_id}"))
    start = (batch - 1) * 12
    for offset in range(start, min(start + 12, total), 3):
        columns = st.columns(3)
        for column, page in zip(columns, document["pages"][offset:offset + 3]):
            with column:
                with st.container(border=True):
                    show_preview(document, page)
                    st.caption(f"P.{page['number']} · {page['rotation']}°" +
                               ("" if page["active"] else " · 除外中"))
                    left, right = st.columns(2)
                    if left.button("除外" if page["active"] else "戻す",
                                   key=f"toggle-{document_id}-{page['number']}"):
                        page["active"] = not page["active"]
                        invalidate()
                        st.rerun()
                    if right.button("↻ 回転", key=f"rotate-{document_id}-{page['number']}"):
                        page["rotation"] = (page["rotation"] + 90) % 360
                        invalidate()
                        st.rerun()
    if st.button("編集を完了", type="primary", use_container_width=True):
        st.session_state.editor_id = None
        st.rerun()


st.title("PDFを結合")
st.write("ファイルを追加して、順番を変えて、ひとつのPDFに。")
top_left, top_right = st.columns([4, 1])
with top_left:
    st.caption("① ファイルを追加　 →　 ② 順番を調整　 →　 ③ 結合して保存")
with top_right:
    if st.button("すべてクリア", use_container_width=True):
        st.session_state.pdf_workspace_v2.cleanup()
        for key in list(st.session_state):
            del st.session_state[key]
        gc.collect()
        st.rerun()

uploads = st.file_uploader("PDF・Word・Excel・PowerPointを追加",
                          type=["pdf", "docx", "xlsx", "xlsm", "pptx"],
                          accept_multiple_files=True,
                          key=f"uploads-{st.session_state.upload_epoch}",
                          help="Officeファイルは自動でPDFに変換します。マクロは実行しません。")
for upload in uploads or []:
    # Streamlit assigns a separate file_id even to files with the same name.
    identity = upload.file_id
    if identity not in st.session_state.upload_seen:
        st.session_state.upload_seen.add(identity)
        with st.spinner(f"{upload.name} を準備しています…"):
            try:
                st.session_state.documents.append(import_document(upload))
                invalidate()
            except Exception as exc:
                st.error(f"{upload.name}: {exc}")
                st.caption("再試行する場合は、一度選択を外してから追加してください。")

documents = st.session_state.documents
if not documents:
    st.info("上のエリアにファイルをドロップするか、ファイルを選択してください。")
else:
    total_pages = sum(sum(p["active"] for p in d["pages"]) for d in documents)
    st.subheader(f"{len(documents)}ファイル · {total_pages}ページ")
    st.caption("ファイル名をドラッグして結合順を変更。カードの「ページ編集」で削除・回転ができます。")
    # Stable ordinals disambiguate duplicate filenames without exposing random IDs.
    labels = [f"{d['name']} 〈{i + 1}〉" for i, d in enumerate(documents)]
    order = sort_items(labels, direction="horizontal",
                       key=f"documents-{st.session_state.order_epoch}")
    if order != labels and sorted(order) == sorted(labels):
        by_label = dict(zip(labels, documents))
        st.session_state.documents = [by_label[label] for label in order]
        invalidate()
        st.rerun()
    for offset in range(0, len(documents), 4):
        for index, (column, document) in enumerate(zip(st.columns(4), documents[offset:offset + 4]), offset):
            with column:
                with st.container(border=True):
                    pages = [p for p in document["pages"] if p["active"]]
                    if pages:
                        show_preview(document, pages[0])
                    else:
                        st.info("全ページ除外中")
                    st.write(f"**{index + 1}. {document['name']}**")
                    st.caption(f"{len(pages)} / {len(document['pages'])} ページ")
                    if st.button("ページ編集", key=f"edit-{document['id']}", use_container_width=True):
                        st.session_state.editor_id = document["id"]
                        st.rerun()
                    if st.button("ファイルを削除", key=f"remove-{document['id']}", use_container_width=True):
                        st.session_state.documents = [d for d in documents if d["id"] != document["id"]]
                        shutil.rmtree(Path(document["path"]).parent, ignore_errors=True)
                        invalidate()
                        st.rerun()

    st.divider()
    with st.expander("詳細設定"):
        use_ocr = st.checkbox("文字を検索できるPDFにする（OCR）", value=False)
        st.caption("日本語・英語に対応。通常の結合より時間とメモリを使います。")
    name = st.text_input("保存するファイル名", value="結合した資料.pdf")
    filename = Path(name.replace("\\", "/")).name.strip() or "結合した資料.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    signature = repr(([(d["id"], [(p["number"], p["rotation"], p["active"])
                       for p in d["pages"]]) for d in documents], use_ocr))
    if st.button("PDFを結合", type="primary", use_container_width=True, disabled=total_pages == 0):
        st.session_state.result_signature = None
        progress = st.progress(0, text="PDFを結合しています…")
        try:
            with tempfile.TemporaryDirectory(dir=root, prefix="output-") as output_dir:
                combined = Path(output_dir) / "merged.pdf"
                merge_documents(documents, combined)
                progress.progress(60, text="文字を認識しています…" if use_ocr else "仕上げています…")
                if use_ocr:
                    ocr = Path(output_dir) / "searchable.pdf"
                    run_command(["ocrmypdf", "-l", "jpn+eng", "--skip-text",
                                 "--jobs", "1", "--optimize", "0",
                                 str(combined), str(ocr)], 600)
                    combined = ocr
                target = root / "result.pdf"
                shutil.copyfile(combined, target)
                st.session_state.result_path = str(target)
                st.session_state.result_signature = signature
            progress.progress(100, text="完成しました")
        except Exception as exc:
            progress.empty()
            st.error(f"結合できませんでした: {exc}")
        finally:
            gc.collect()
    if st.session_state.result_signature == signature and st.session_state.result_path:
        st.success("PDFが完成しました。下のボタンから保存できます。")
        with open(st.session_state.result_path, "rb") as result:
            st.download_button("PDFをダウンロード", result, file_name=filename,
                               mime="application/pdf", type="primary", use_container_width=True)
    elif st.session_state.result_path:
        st.caption("内容や設定が変更されています。「PDFを結合」を押して更新してください。")

st.caption("ファイルはこのアプリのサーバーで処理されます。作業後は「すべてクリア」で削除できます。")

if st.session_state.get("editor_id"):
    edit_document(st.session_state.editor_id)
