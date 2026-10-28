import base64
import gc
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components
from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader, PdfWriter

st.set_page_config(page_title="PDFManager", page_icon="📄", layout="wide")
st.markdown("""
<style>
.stApp {background: #f7f8fc;}
.block-container {max-width: 1300px; padding-top: 4rem;}
h1 {letter-spacing: -.04em;}
div[data-testid="stFileUploader"] {display: none;}
div[data-testid="stElementContainer"]:has(div[data-testid="stFileUploader"]) {display: none;}
div.stButton > button[kind="primary"] {background: #e44747; border-color: #e44747;}
</style>
""", unsafe_allow_html=True)

if "pdf_workspace_v2" not in st.session_state:
    st.session_state.pdf_workspace_v2 = tempfile.TemporaryDirectory(prefix="pdf-merge-")
    st.session_state.documents = []
    st.session_state.upload_seen = set()
    st.session_state.upload_epoch = 0
    st.session_state.order_epoch = 0
    st.session_state.result_path = None
    st.session_state.result_signature = None

root = Path(st.session_state.pdf_workspace_v2.name)

# Preserve uploaded documents when upgrading an existing session.
if "manager_pages" not in st.session_state:
    st.session_state.manager_pages = []
    for document in st.session_state.documents:
        for page in document["pages"]:
            st.session_state.manager_pages.append(dict(page, document_id=document["id"],
                                                       id=f"{document['id']}:{page['number']}"))


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


def preview(document, page, size=900):
    # Cache lossless previews on disk; render only the requested pages.
    target = Path(document["path"]).parent / f"preview-{page['number']}-{page['rotation']}-{size}.png"
    if not target.exists():
        paths = convert_from_path(document["path"], first_page=page["number"],
                                  last_page=page["number"], size=size, fmt="png",
                                  output_folder=str(target.parent), paths_only=True,
                                  thread_count=1, timeout=45)
        try:
            with Image.open(paths[0]) as source:
                rotated = source.rotate(-page["rotation"], expand=True)
                try:
                    rotated.save(target, "PNG")
                finally:
                    rotated.close()
        finally:
            for path in paths:
                Path(path).unlink(missing_ok=True)
    return str(target)


def show_preview(document, page, size=900):
    try:
        st.image(preview(document, page, size), use_container_width=True)
    except Exception:
        st.caption("📄 プレビューを作成できません。結合は引き続きお試しいただけます。")

PAGE_HTML = r'''
<!doctype html><html lang="ja"><meta charset="utf-8">
<style>
*{box-sizing:border-box}body{margin:0;padding:6px;font:14px system-ui,sans-serif;color:#202331}
.toolbar{display:flex;justify-content:flex-end;margin:0 0 12px}
#cards{display:grid;grid-template-columns:repeat(auto-fill,198px);gap:10px;align-items:start;min-height:360px}
.card{position:relative;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:50px 8px 8px;cursor:grab;min-width:0;width:198px;height:244px;box-shadow:0 2px 8px #1a203008}
.card:hover,.card:focus-within{border-color:#9ca3af}
.card:active{cursor:grabbing}.card.dragging{opacity:.35}.card.over{outline:3px solid #e44747}
.card.excluded .preview{opacity:.4;filter:grayscale(1)}
.preview{display:block;width:100%;height:140px;object-fit:contain;cursor:zoom-in}
.name{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:5px 0 0;color:#4b5563}
.meta{font-size:11px;color:#667085;margin:8px 0 0;white-space:nowrap}
.actions{position:absolute;top:9px;right:8px;display:flex;gap:4px;opacity:0;visibility:hidden;pointer-events:none;transition:opacity .12s}
.card:hover .actions,.card:focus-within .actions{opacity:1;visibility:visible;pointer-events:auto}
.actions button{width:26px;height:26px;display:grid;place-items:center;padding:4px;border-radius:50%;background:#f0f1f5;border-color:#e5e7eb}
.actions button:hover{background:#e5e7eb}.actions svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
#filename-tip{position:fixed;z-index:1000;display:none;max-width:min(360px,calc(100vw - 16px));padding:8px 10px;border-radius:6px;background:#42454d;color:white;font-size:12px;line-height:1.5;overflow-wrap:anywhere;pointer-events:none;box-shadow:0 3px 10px #0002}
button{font:inherit;background:white;border:1px solid #dce0ea;border-radius:7px;padding:7px;cursor:pointer;color:inherit}
button:hover{border-color:#e44747}button:focus-visible,.card:focus-visible{outline:3px solid #e44747}
#empty{display:none;min-height:360px;place-items:center;color:#667085;border:2px dashed #dce0ea;border-radius:16px;cursor:pointer}
#status{color:#b42318;font-size:13px}
@media(max-width:440px){#cards{grid-template-columns:repeat(2,minmax(0,198px));gap:8px}.card{width:100%}}
@media(hover:none),(pointer:coarse){.actions{opacity:1;visibility:visible;pointer-events:auto}}
</style>
<div class="toolbar"><button id="add">＋ ファイル追加</button></div>
<div id="empty" role="button" tabindex="0">ファイルをドロップ</div>
<div id="cards"></div><div id="status" role="status" aria-live="polite"></div><div id="filename-tip" role="tooltip"></div>
<script>
const grid=document.getElementById("cards"),status=document.getElementById("status"),empty=document.getElementById("empty");
const filenameTip=document.getElementById("filename-tip");
function hideFilename(){filenameTip.style.display="none"}
function showFilename(card,item){
 filenameTip.textContent=item.name;filenameTip.style.display="block";
 const box=card.getBoundingClientRect(),tip=filenameTip.getBoundingClientRect();
 filenameTip.style.left=Math.max(8,Math.min(box.left,window.innerWidth-tip.width-8))+"px";
 filenameTip.style.top=Math.max(4,box.top-tip.height-8)+"px";
}
let items=[],revision=0,dragged=null,disabled=false;
function send(type,data){window.parent.postMessage({isStreamlitMessage:true,type,...data},"*")}
let lastHeight=0;
function height(){const value=document.body.scrollHeight+12;if(value!==lastHeight){lastHeight=value;send("streamlit:setFrameHeight",{height:value})}}
function emit(action,id,order){if(disabled)return;send("streamlit:setComponentValue",{dataType:"json",value:{action,id,order,revision,event_id:crypto.randomUUID()}})}
function reorder(from,to){if(from===to||from<0||to<0||to>=items.length)return;const next=items.slice();next.splice(to,0,next.splice(from,1)[0]);items=next;render();emit("reorder",null,items.map(x=>x.id))}
function button(label,fn,title){const b=document.createElement("button");b.textContent=label;b.title=title||label;b.disabled=disabled;b.onclick=e=>{e.stopPropagation();fn()};return b}
function iconButton(kind,fn,label){
 const b=button("",fn,label);b.setAttribute("aria-label",label);
 const paths={zoom:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5M10 7v6M7 10h6"/>',rotate:'<path d="M19 7V2l-4 4a8 8 0 1 0 4 6M19 2h-5"/>',remove:'<path d="m6 6 12 12M18 6 6 18"/>',restore:'<path d="m5 12 4 4L19 6"/>'};
 b.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true">'+paths[kind]+'</svg>';return b;
}
function uploadInput(){return window.parent.document.querySelector('[data-testid="stFileUploader"] input[type="file"]')}
function chooseFiles(){try{const input=uploadInput();if(!input)throw Error("upload input missing");input.click()}catch(e){status.textContent="追加ボタンを読み込めません。画面を再読み込みしてください。";height()}}
document.getElementById("add").onclick=chooseFiles;empty.onclick=chooseFiles;
empty.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();chooseFiles()}};
function render(){
 hideFilename();
 grid.replaceChildren();grid.style.display=items.length?"grid":"none";empty.style.display=items.length?"none":"grid";
 items.forEach((item,index)=>{
  const card=document.createElement("article");card.className="card"+(item.active?"":" excluded");card.draggable=!disabled;card.dataset.id=item.id;
  card.tabIndex=0;card.setAttribute("aria-label",(index+1)+". "+item.name+" P."+item.number);
  card.setAttribute("aria-describedby","filename-tip");
  card.onmouseenter=()=>showFilename(card,item);card.onmouseleave=hideFilename;
  card.onfocus=()=>showFilename(card,item);card.onblur=hideFilename;
  card.onkeydown=e=>{if(e.target!==card||!e.altKey)return;if(e.key==="ArrowLeft"){e.preventDefault();reorder(index,index-1)}if(e.key==="ArrowRight"){e.preventDefault();reorder(index,index+1)}};
  card.ondragstart=e=>{if(e.target.closest("button")){e.preventDefault();return}hideFilename();dragged=item.id;e.dataTransfer.effectAllowed="move";e.dataTransfer.setData("text/plain",item.id);card.classList.add("dragging")};
  card.ondragover=e=>{if(dragged&&dragged!==item.id){e.preventDefault();e.dataTransfer.dropEffect="move";card.classList.add("over")}};
  card.ondragleave=()=>card.classList.remove("over");
  card.ondrop=e=>{if(Array.from(e.dataTransfer.types||[]).includes("Files"))return;e.preventDefault();card.classList.remove("over");const from=items.findIndex(x=>x.id===dragged),to=items.findIndex(x=>x.id===item.id);if(from>=0&&to>=0)reorder(from,to);dragged=null};
  card.ondragend=()=>{dragged=null;document.querySelectorAll(".card").forEach(x=>x.classList.remove("over","dragging"))};
  const img=document.createElement(item.image?"img":"div");img.className="preview";img.draggable=false;
  if(item.image){img.src=item.image;img.alt=item.name+" P."+item.number;img.onload=height;img.onclick=()=>emit("preview",item.id)}
  else{img.textContent="プレビューなし"}card.append(img);
  const meta=document.createElement("div");meta.className="meta";meta.textContent=(index+1)+" · 元 P."+item.number+" / "+item.total+(item.active?"":" · 除外中");card.append(meta);
  const name=document.createElement("div");name.className="name";name.textContent=item.name;card.append(name);
  const actions=document.createElement("div");actions.className="actions";
  actions.append(iconButton("zoom",()=>emit("preview",item.id),"拡大"),iconButton("rotate",()=>emit("rotate",item.id),"90度回転"),iconButton(item.active?"remove":"restore",()=>emit("toggle",item.id),item.active?"削除":"戻す"));
  card.append(actions);grid.append(card);
 });height();
}
function installFileDrop(){
 try{
  const host=window.parent,hostDoc=host.document;
  if(host.__pdfManagerDropCleanup)host.__pdfManagerDropCleanup();
  const overlay=hostDoc.createElement("div");overlay.textContent="ファイルを追加";
  overlay.style.cssText="display:none;position:fixed;inset:10px;z-index:999999;pointer-events:none;border:3px dashed #e44747;border-radius:18px;background:#fffC;align-items:center;justify-content:center;color:#e44747;font:600 24px system-ui";
  hostDoc.body.append(overlay);
  let timer;const targets=[document,hostDoc];try{if(window.top.document!==hostDoc)targets.push(window.top.document)}catch(e){}
  const isFiles=e=>Array.from(e.dataTransfer?.types||[]).includes("Files");
  const over=e=>{if(!isFiles(e))return;e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect="copy";overlay.style.display="flex";clearTimeout(timer);timer=setTimeout(()=>overlay.style.display="none",250)};
  const drop=e=>{
   if(!isFiles(e))return;e.preventDefault();e.stopPropagation();clearTimeout(timer);overlay.style.display="none";
   const files=Array.from(e.dataTransfer.files||[]);if(!files.length)return;
   const input=uploadInput();if(!input){status.textContent="追加欄を読み込めません。再読み込みしてください。";height();return}
   // Preserve Streamlit's native upload endpoint, limits and progress handling.
   const transfer=new host.DataTransfer();for(const file of files)transfer.items.add(file);
   input.files=transfer.files;input.dispatchEvent(new host.Event("change",{bubbles:true}));
  };
  for(const target of targets){target.addEventListener("dragover",over,true);target.addEventListener("drop",drop,true)}
  const cleanup=()=>{clearTimeout(timer);for(const target of targets){target.removeEventListener("dragover",over,true);target.removeEventListener("drop",drop,true)}overlay.remove()};
  host.__pdfManagerDropCleanup=cleanup;window.addEventListener("pagehide",cleanup,{once:true});
 }catch(e){status.textContent="全画面ドロップを初期化できませんでした。再読み込みしてください。";height()}
}
window.addEventListener("message",e=>{if(e.source!==window.parent||e.data.type!=="streamlit:render")return;
 items=e.data.args.items;revision=e.data.args.revision;disabled=!!e.data.disabled;render();
});
new ResizeObserver(height).observe(grid);
installFileDrop();send("streamlit:componentReady",{apiVersion:1});height();
</script></html>

'''


@st.cache_resource
def page_canvas():
    folder = Path(tempfile.mkdtemp(prefix="pdf-page-canvas-"))
    (folder / "index.html").write_text(PAGE_HTML, encoding="utf-8")
    return components.declare_component("pdf_page_canvas_v4", path=str(folder))


def valid_order(order, pages):
    expected = {p["id"] for p in pages}
    return (isinstance(order, list) and len(order) == len(pages)
            and all(isinstance(item, str) for item in order) and set(order) == expected)


def merge_pages(documents, pages, destination):
    by_document = {d["id"]: d for d in documents}
    writer = PdfWriter()
    try:
        with ExitStack() as stack:
            readers = {}
            for page in pages:
                if not page["active"]:
                    continue
                document_id = page["document_id"]
                if document_id not in readers:
                    stream = stack.enter_context(open(by_document[document_id]["path"], "rb"))
                    reader = PdfReader(stream)
                    if reader.is_encrypted:
                        reader.decrypt("")
                    readers[document_id] = reader
                # Each page is cloned by the writer; source pages stay untouched.
                added = writer.add_page(readers[document_id].pages[page["number"] - 1])
                if page["rotation"]:
                    added.rotate(page["rotation"])
            with open(destination, "wb") as output:
                writer.write(output)
    finally:
        writer.close()


@st.dialog("プレビュー", width="large")
def enlarged_preview(page_id):
    page = next((p for p in st.session_state.manager_pages if p["id"] == page_id), None)
    if page:
        document = next(d for d in st.session_state.documents if d["id"] == page["document_id"])
        st.caption(f"{document['name']} · P.{page['number']}")
        show_preview(document, page, size=1800)
    if st.button("閉じる", key="close-page-preview"):
        st.session_state.manager_preview_id = None
        st.rerun()


left, right = st.columns([5, 1])
with left:
    st.title("PDFManager")
with right:
    if st.button("すべてクリア", use_container_width=True):
        st.session_state.pdf_workspace_v2.cleanup()
        for key in list(st.session_state):
            del st.session_state[key]
        gc.collect()
        st.rerun()

# Hidden native uploader is triggered by the canvas's full-window drop handler.
# It keeps upload-size validation and Streamlit's streaming upload protocol.
uploads = st.file_uploader("ファイル追加", type=["pdf", "docx", "xlsx", "xlsm", "pptx"],
                          accept_multiple_files=True, label_visibility="collapsed",
                          key=f"uploads-{st.session_state.upload_epoch}")
for upload in uploads or []:
    identity = upload.file_id
    if identity not in st.session_state.upload_seen:
        st.session_state.upload_seen.add(identity)
        with st.spinner(f"{upload.name} を準備しています…"):
            try:
                document = import_document(upload)
                st.session_state.documents.append(document)
                for page in document["pages"]:
                    st.session_state.manager_pages.append(dict(page, document_id=document["id"],
                                                               id=f"{document['id']}:{page['number']}"))
                invalidate()
            except Exception as exc:
                st.error(f"{upload.name}: {exc}")

documents = st.session_state.documents
pages = st.session_state.manager_pages
by_document = {d["id"]: d for d in documents}
active_count = sum(p["active"] for p in pages)
if pages:
    st.caption(f"{len(documents)}ファイル · {active_count}ページ")

card_items = []
for page in pages:
    document = by_document[page["document_id"]]
    image = None
    try:
        image = "data:image/png;base64," + base64.b64encode(
            Path(preview(document, page, size=900)).read_bytes()).decode("ascii")
    except Exception:
        pass
    card_items.append({"id": page["id"], "name": document["name"], "number": page["number"], "total": len(document["pages"]),
                       "active": page["active"], "image": image})

event = page_canvas()(items=card_items, revision=st.session_state.order_epoch,
                      key=f"page-canvas-{st.session_state.upload_epoch}", default=None)
if (isinstance(event, dict) and event.get("event_id") != st.session_state.get("last_page_event")
        and event.get("revision") == st.session_state.order_epoch):
    st.session_state.last_page_event = event.get("event_id")
    by_id = {p["id"]: p for p in pages}
    action, page_id = event.get("action"), event.get("id")
    if action == "reorder":
        order = event.get("order")
        if valid_order(order, pages) and order != [p["id"] for p in pages]:
            st.session_state.manager_pages = [by_id[i] for i in order]
            invalidate()
            st.rerun()
    elif isinstance(page_id, str) and page_id in by_id:
        page = by_id[page_id]
        if action == "rotate":
            page["rotation"] = (page["rotation"] + 90) % 360
            invalidate()
            st.rerun()
        elif action == "toggle":
            page["active"] = not page["active"]
            invalidate()
            st.rerun()
        elif action == "preview":
            st.session_state.manager_preview_id = page_id
            st.rerun()

if pages:
    st.divider()
    with st.expander("詳細設定"):
        use_ocr = st.checkbox("文字を検索できるPDFにする（OCR）", value=False)
        st.caption("日本語・英語に対応。通常の結合より時間とメモリを使います。")
        st.caption("ファイルはサーバーで処理します。「すべてクリア」で削除できます。")
    name = st.text_input("保存するファイル名", value="結合した資料.pdf")
    filename = Path(name.replace(chr(92), "/")).name.strip() or "結合した資料.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    signature = repr(([(p["id"], p["rotation"], p["active"]) for p in pages], use_ocr))
    if st.button("PDFを結合", type="primary", use_container_width=True, disabled=active_count == 0):
        st.session_state.result_signature = None
        progress = st.progress(0, text="PDFを結合しています…")
        try:
            with tempfile.TemporaryDirectory(dir=root, prefix="output-") as output_dir:
                combined = Path(output_dir) / "merged.pdf"
                merge_pages(documents, pages, combined)
                progress.progress(60, text="文字を認識しています…" if use_ocr else "仕上げています…")
                if use_ocr:
                    ocr = Path(output_dir) / "searchable.pdf"
                    run_command(["ocrmypdf", "-l", "jpn+eng", "--skip-text",
                                 "--jobs", "1", "--optimize", "0", str(combined), str(ocr)], 600)
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
        with open(st.session_state.result_path, "rb") as result:
            st.download_button("PDFをダウンロード", result, file_name=filename,
                               mime="application/pdf", type="primary", use_container_width=True)

if st.session_state.get("manager_preview_id"):
    enlarged_preview(st.session_state.manager_preview_id)
