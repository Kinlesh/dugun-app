# -*- coding: utf-8 -*-
"""
Himmet & Cennet düğün albümü — FastAPI (Jinja yok, HTML doğrudan Python ile).
Yüklemeler Google Drive'a gider; galeri Drive klasöründen listelenir.
"""
from __future__ import annotations

import html
import io
import json
import mimetypes
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Google Drive: paylaşılan klasör ID'si (Google Drive URL'den veya API'den)
FOLDER_ID = "17AYafv6kTUDeIK7UBgukOohTdUhJ4UNQ"

_SCOPES = ("https://www.googleapis.com/auth/drive",)

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
ALLOWED_VIDEO = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
ALLOWED_EXT = ALLOWED_IMAGE | ALLOWED_VIDEO
VIDEO_EXT = ALLOWED_VIDEO

_drive_service = None


def get_drive_service():
    """GOOGLE_CREDS ortam değişkeninden (JSON string) servis hesabı ile Drive v3."""
    global _drive_service
    if _drive_service is not None:
        return _drive_service
    raw = os.environ.get("GOOGLE_CREDS")
    if not raw:
        return None
    info = json.loads(raw)
    credentials = Credentials.from_service_account_info(info, scopes=_SCOPES)
    _drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    return _drive_service


def upload_to_drive(file_bytes: bytes, filename: str) -> str:
    """
    Dosyayı Google Drive'a yükler, herkese okuma izni verir.
    Dönüş: https://drive.google.com/uc?id=FILE_ID
    """
    drive = get_drive_service()
    if drive is None:
        raise RuntimeError("Drive yapılandırması yok (GOOGLE_CREDS).")

    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    media = MediaIoBaseUpload(
        io.BytesIO(file_bytes),
        mimetype=mime,
        resumable=True,
    )
    body = {"name": filename, "parents": [FOLDER_ID]}
    created = (
        drive.files()
        .create(body=body, media_body=media, fields="id")
        .execute()
    )
    fid = created["id"]
    drive.permissions().create(
        fileId=fid,
        body={"type": "anyone", "role": "reader"},
        fields="id",
    ).execute()
    return f"https://drive.google.com/uc?id={fid}"


_EMBED_CSS = """/* Himmet & Cennet */
:root{--bg:#fffafb;--card:#fff;--pink-soft:#fce4ec;--pink-mid:#f8bbd9;--pink-deep:#ec407a;--text:#4a3f44;--muted:#8d7a82;--shadow:0 8px 32px rgba(236,64,122,.12);--r:20px;--pill:999px;--f:system-ui,-apple-system,sans-serif}
*,*::before,*::after{box-sizing:border-box}
body{margin:0;min-height:100vh;font-family:var(--f);color:var(--text);background:var(--bg);
background-image:radial-gradient(ellipse 120% 80% at 50% -20%,var(--pink-soft),transparent 55%),radial-gradient(ellipse 80% 50% at 100% 100%,rgba(252,228,236,.5),transparent 45%);line-height:1.5}
.wrap{max-width:520px;margin:0 auto;padding:1.5rem 1.25rem 3rem}
.wrap.wide{max-width:900px}
header.hero{text-align:center;padding:2rem 0 1.75rem}
.hero h1{margin:0 0 .5rem;font-size:clamp(1.45rem,5vw,1.85rem);font-weight:600}
.subtitle{margin:0;font-size:1rem;color:var(--muted)}
.card{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);padding:1.5rem 1.35rem;border:1px solid rgba(248,187,217,.35)}
.card h2{margin:0 0 1rem;font-size:1.05rem;font-weight:600}
.upload-form{display:flex;flex-direction:column;gap:1rem}
.file-row{position:relative}
.file-row input{position:absolute;width:.1px;height:.1px;opacity:0;overflow:hidden;z-index:-1}
.file-label{display:flex;align-items:center;justify-content:center;min-height:52px;padding:.75rem 1rem;border:2px dashed var(--pink-mid);border-radius:var(--pill);background:var(--pink-soft);cursor:pointer;font-size:.95rem}
.file-label:hover{border-color:var(--pink-deep);background:#fff0f5}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:.65rem 1.5rem;border:none;border-radius:var(--pill);font:inherit;font-size:.95rem;font-weight:600;cursor:pointer;text-decoration:none}
.btn-primary{background:linear-gradient(135deg,var(--pink-deep),#d81b60);color:#fff;box-shadow:0 4px 16px rgba(236,64,122,.35)}
.btn-secondary{background:#fff;color:var(--pink-deep);border:2px solid var(--pink-mid)}
.btn-block{width:100%}
.hint{margin:0;font-size:.78rem;color:var(--muted);text-align:center}
.alert{margin-bottom:1.25rem;padding:1rem;border-radius:var(--r);font-size:.92rem;text-align:center}
.alert-success{background:linear-gradient(135deg,#e8f5e9,#f1f8e9);border:1px solid #c8e6c9;color:#2e7d32}
.alert-error{background:#ffebee;border:1px solid #ffcdd2;color:#c62828}
.alert-actions{display:flex;flex-direction:column;gap:.65rem;margin-top:1rem}
.nav-footer{margin-top:2rem;text-align:center}
.gallery-header{text-align:center;padding:1.5rem 0 1.25rem}
.gallery-header h1{margin:0 0 .35rem;font-size:clamp(1.35rem,4.5vw,1.75rem);font-weight:600}
.gallery-header p{margin:0;font-size:.9rem;color:var(--muted)}
.gallery-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.65rem}
@media(min-width:480px){.gallery-grid{grid-template-columns:repeat(3,1fr);gap:.85rem}}
@media(min-width:720px){.gallery-grid{grid-template-columns:repeat(4,1fr)}}
.gallery-item{aspect-ratio:1;border-radius:14px;overflow:hidden;background:var(--pink-soft);border:1px solid rgba(248,187,217,.4)}
.gallery-item img,.gallery-item video{width:100%;height:100%;object-fit:cover;display:block}
.gallery-item video{background:#000}
.empty-gallery{text-align:center;padding:2.5rem 1rem;color:var(--muted)}
.empty-gallery p{margin:0 0 1rem}
.top-nav{margin-bottom:1rem}
.hero-simple{padding:1.25rem 0 1rem}
.hero-simple h1{font-size:clamp(1.35rem,5.5vw,1.75rem)}
.subtitle-short{font-size:1.05rem;line-height:1.45}
.upload-simple{padding:1.35rem 1.1rem}
.upload-simple .upload-form{gap:1.15rem}
.file-label-big{min-height:64px;font-size:1.1rem;padding:1rem 1.15rem;font-weight:600}
.btn-send{min-height:56px;font-size:1.12rem;padding:0.85rem 1.25rem}
.hint-link{margin:1.25rem 0 0;text-align:center;font-size:1rem}
.hint-link a{color:var(--pink-deep);font-weight:600;text-decoration:none}
.hint-link a:hover{text-decoration:underline}
.alert-success strong{display:block;margin-bottom:0.25rem;font-size:1.05rem}
.alert-success .btn-send{margin-top:0.85rem}
"""


def html_page(content_type: str, body: str) -> Response:
    return Response(
        content=body.encode("utf-8"),
        media_type=content_type,
    )


def build_index_html(success: bool, error_message: Optional[str]) -> str:
    alert_ok = ""
    if success:
        alert_ok = """
        <div class="alert alert-success" role="status">
          <strong>Teşekkürler!</strong>
          Dosyalarınız alındı.
          <a class="btn btn-primary btn-block btn-send" href="/gallery">Paylaşılanlara bak</a>
        </div>"""
    alert_err = ""
    if error_message:
        alert_err = (
            f'<div class="alert alert-error" role="alert">'
            f"{html.escape(error_message)}</div>"
        )
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Himmet &amp; Cennet — Yükle</title>
<link rel="stylesheet" href="/static/style.css" />
</head>
<body>
<div class="wrap">
<header class="hero hero-simple">
<h1>Himmet &amp; Cennet</h1>
<p class="subtitle subtitle-short">Bugün çektiğiniz fotoğraf ve videoları seçin — aynı anda birden fazla dosya yükleyebilirsiniz.</p>
</header>
<main>
{alert_ok}
{alert_err}
<section class="card upload-simple">
<form class="upload-form" action="/upload" method="post" enctype="multipart/form-data">
<div class="file-row">
<input type="file" id="file" name="files" accept="image/*,video/*" multiple required />
<label class="file-label file-label-big" for="file">📷 Dokun — bir veya birden fazla fotoğraf / video seç</label>
</div>
<button type="submit" class="btn btn-primary btn-block btn-send">Gönder</button>
</form>
</section>
<p class="hint-link"><a href="/gallery">Paylaşılanları görüntüle →</a></p>
</main>
</div>
</body>
</html>"""


def build_gallery_html(items: list[dict[str, Any]]) -> str:
    if not items:
        main_inner = """
        <div class="empty-gallery card">
          <p>Henüz paylaşım yok.<br />İlk siz ekleyin.</p>
          <a class="btn btn-primary btn-send btn-block" href="/">Yükleme sayfası</a>
        </div>"""
    else:
        parts: list[str] = []
        for item in items:
            url = html.escape(str(item["url"]), quote=True)
            if item.get("is_video"):
                parts.append(
                    f'<div class="gallery-item"><video controls playsinline preload="metadata" src="{url}">'
                    f"Tarayıcınız bu videoyu oynatamıyor.</video></div>"
                )
            else:
                parts.append(
                    f'<div class="gallery-item"><img src="{url}" alt="Fotoğraf" '
                    f'loading="lazy" decoding="async" /></div>'
                )
        main_inner = f'<div class="gallery-grid">{"".join(parts)}</div>'
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Paylaşılanlar — Himmet &amp; Cennet</title>
<link rel="stylesheet" href="/static/style.css" />
</head>
<body>
<div class="wrap wide">
<nav class="top-nav" aria-label="Sayfa">
<a class="btn btn-secondary" href="/">← Yükleme sayfası</a>
</nav>
<header class="gallery-header">
<h1>Paylaşılanlar</h1>
<p>Bugün eklenen fotoğraf ve videolar</p>
</header>
<main>
{main_inner}
</main>
</div>
</body>
</html>"""


def ensure_project_layout() -> None:
    try:
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        css = STATIC_DIR / "style.css"
        if not css.exists():
            css.write_text(_EMBED_CSS, encoding="utf-8")
        (TEMPLATES_DIR / "index.html").write_text(
            build_index_html(False, None), encoding="utf-8"
        )
        (TEMPLATES_DIR / "gallery.html").write_text(
            build_gallery_html([]), encoding="utf-8"
        )
    except OSError:
        pass


ensure_project_layout()

app = FastAPI(title="Himmet & Cennet Düğün Albümü")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index(ok: Optional[str] = None, error: Optional[str] = None):
    success = ok == "1"
    error_message: Optional[str] = None
    if error == "tip":
        error_message = "Lütfen fotoğraf veya video dosyası seçin."
    elif error == "kayit":
        error_message = "Gönderilemedi. Bir kez daha deneyin."
    body = build_index_html(success, error_message)
    return html_page("text/html; charset=utf-8", body)


@app.post("/upload")
async def upload(files: List[UploadFile] = File(default_factory=list)):
    if not files:
        return RedirectResponse(url="/?error=tip", status_code=303)

    saved = 0
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        try:
            data = await file.read()
        except Exception:
            return RedirectResponse(url="/?error=kayit", status_code=303)
        new_name = f"{uuid.uuid4().hex}{ext}"
        try:
            upload_to_drive(data, new_name)
            saved += 1
        except Exception:
            return RedirectResponse(url="/?error=kayit", status_code=303)

    if saved == 0:
        return RedirectResponse(url="/?error=tip", status_code=303)
    return RedirectResponse(url="/?ok=1", status_code=303)


@app.get("/gallery")
async def gallery():
    items = list_gallery_items()
    body = build_gallery_html(items)
    return html_page("text/html; charset=utf-8", body)


def _item_is_video(name: str, mime: str) -> bool:
    ext = Path(name).suffix.lower()
    if ext in VIDEO_EXT:
        return True
    if mime.startswith("video/"):
        return True
    return False


def list_gallery_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    drive = get_drive_service()
    if drive is None or FOLDER_ID == "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE":
        return items
    try:
        resp = (
            drive.files()
            .list(
                q=f"'{FOLDER_ID}' in parents and trashed = false",
                fields="files(id, name, mimeType, modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=200,
            )
            .execute()
        )
        for f in resp.get("files", []):
            name = f.get("name") or ""
            mime = f.get("mimeType") or ""
            ext = Path(name).suffix.lower()
            if ext and ext not in ALLOWED_EXT:
                continue
            if not ext:
                if not (
                    mime.startswith("image/")
                    or mime.startswith("video/")
                ):
                    continue
            fid = f.get("id")
            if not fid:
                continue
            mt = 0.0
            try:
                raw = f.get("modifiedTime")
                if raw:
                    mt = datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                mt = 0.0
            items.append(
                {
                    "name": name,
                    "url": f"https://drive.google.com/uc?id={fid}",
                    "is_video": _item_is_video(name, mime),
                    "mtime": mt,
                }
            )
        items.sort(key=lambda x: x["mtime"], reverse=True)
    except Exception:
        pass
    return items


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
