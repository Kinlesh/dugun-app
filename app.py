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
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
TOKEN_PATH = BASE_DIR / "token.json"

# Google Drive: hedef klasör (OAuth ile giriş yapan kullanıcının Drive'ı)
FOLDER_ID = "17AYafv6kTUDeIK7UBgukOohTdUhJ4UNQ"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "https://eenginsoy.com.tr/oauth2callback"


def drive_public_media_url(file_id: str, mime_type: str) -> str:
    """Herkese açık Drive dosyası için tarayıcıda uygun URL (görüntü / video / diğer)."""
    if mime_type.startswith("image/"):
        return f"https://lh3.googleusercontent.com/d/{file_id}"
    if mime_type.startswith("video/"):
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return f"https://drive.google.com/file/d/{file_id}/view"


ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
ALLOWED_VIDEO = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
ALLOWED_EXT = ALLOWED_IMAGE | ALLOWED_VIDEO


def _load_google_client_config() -> dict | None:
    try:
        raw = os.environ["GOOGLE_CLIENT_SECRET"]
    except KeyError:
        return None
    if not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _oauth_flow_from_env() -> Flow | None:
    client_config = _load_google_client_config()
    if client_config is None:
        return None
    return Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )


def get_drive_service():
    """OAuth token.json ile Drive v3; süresi dolmuşsa yeniler."""
    if not TOKEN_PATH.is_file():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(GoogleAuthRequest())
                TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            else:
                return None
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print("get_drive_service:", str(e))
        traceback.print_exc()
        return None


def upload_to_drive(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """
    Dosyayı kişisel Google Drive klasörüne yükler, herkese okuma izni verir.
    Dönüş: url, mime_type, is_video
    """
    drive = get_drive_service()
    if drive is None:
        raise RuntimeError("Önce Google ile giriş yapın (/login).")

    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=True)

    file_metadata = {"name": filename, "parents": [FOLDER_ID]}
    file = drive.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()

    drive.permissions().create(
        fileId=file["id"],
        body={"role": "reader", "type": "anyone"},
    ).execute()

    fid = file["id"]
    return {
        "url": drive_public_media_url(fid, mime),
        "mime_type": mime,
        "is_video": mime.startswith("video/"),
    }


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
.gallery-item--file{aspect-ratio:auto;min-height:80px;display:flex;align-items:center;justify-content:center;padding:0.5rem}
.file-link{display:inline-block;padding:10px;background:#f3f3f3;border-radius:8px;text-decoration:none;color:var(--text)}
.file-link:hover{background:#e8e8e8}
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


def build_index_html(
    success: bool,
    error_message: Optional[str],
    logged_in: bool,
    login_notice: bool,
) -> str:
    alert_ok = ""
    if success:
        alert_ok = """
        <div class="alert alert-success" role="status">
          <strong>Teşekkürler!</strong>
          Dosyalarınız alındı.
          <a class="btn btn-primary btn-block btn-send" href="/gallery">Paylaşılanlara bak</a>
        </div>"""
    alert_login = ""
    if login_notice:
        alert_login = """
        <div class="alert alert-success" role="status">
          <strong>Google ile giriş başarılı</strong>
          Artık dosya yükleyebilirsiniz.
        </div>"""
    alert_err = ""
    if error_message:
        alert_err = (
            f'<div class="alert alert-error" role="alert">'
            f"{html.escape(error_message)}</div>"
        )
    if logged_in:
        upload_block = """
<section class="card upload-simple">
<form class="upload-form" action="/upload" method="post" enctype="multipart/form-data">
<div class="file-row">
<input type="file" id="file" name="files" accept="image/*,video/*" multiple required />
<label class="file-label file-label-big" for="file">📷 Dokun — bir veya birden fazla fotoğraf / video seç</label>
</div>
<button type="submit" class="btn btn-primary btn-block btn-send">Gönder</button>
</form>
</section>"""
    else:
        upload_block = """
<section class="card upload-simple">
<p class="hint" style="margin-bottom:1rem;text-align:center;font-size:1rem;">
Yüklemek için yönetici Google hesabıyla oturum açın.
</p>
<a class="btn btn-primary btn-block btn-send" href="/login">Google ile giriş yap</a>
</section>"""
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
{alert_login}
{alert_err}
{upload_block}
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
            mime_type = html.escape(str(item.get("mime_type") or ""), quote=True)
            if item.get("is_image"):
                parts.append(
                    f'<div class="gallery-item"><img src="{url}" alt="Fotoğraf" '
                    f'loading="lazy" decoding="async" /></div>'
                )
            elif item.get("is_video"):
                parts.append(
                    f'<div class="gallery-item"><video controls playsinline preload="metadata" '
                    f'style="width:100%"><source src="{url}" type="{mime_type}">'
                    f"Tarayıcınız bu videoyu oynatamıyor.</video></div>"
                )
            else:
                parts.append(
                    f'<div class="gallery-item gallery-item--file">'
                    f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="file-link">'
                    f"📄 Dosyayı görüntüle / indir</a></div>"
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
            build_index_html(False, None, False, False), encoding="utf-8"
        )
        (TEMPLATES_DIR / "gallery.html").write_text(
            build_gallery_html([]), encoding="utf-8"
        )
    except OSError:
        pass


ensure_project_layout()

app = FastAPI(title="Himmet & Cennet Düğün Albümü")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "CHANGE_THIS_TO_RANDOM_SECRET"),
    same_site="lax",
)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index(
    ok: Optional[str] = None,
    error: Optional[str] = None,
    login: Optional[str] = None,
):
    success = ok == "1"
    login_notice = login == "ok"
    logged_in = TOKEN_PATH.is_file()
    error_message: Optional[str] = None
    if error == "tip":
        error_message = "Lütfen fotoğraf veya video dosyası seçin."
    elif error == "kayit":
        error_message = "Gönderilemedi. Bir kez daha deneyin."
    elif error == "oauth":
        error_message = "Google ile giriş tamamlanamadı. Tekrar deneyin."
    elif error == "secret":
        error_message = (
            "OAuth yapılandırması eksik: ortam değişkeni GOOGLE_CLIENT_SECRET "
            "(Google Cloud Web istemcisi JSON içeriği) tanımlı değil."
        )
    body = build_index_html(success, error_message, logged_in, login_notice)
    return html_page("text/html; charset=utf-8", body)


@app.get("/login")
def login(request: Request):
    flow = _oauth_flow_from_env()
    if flow is None:
        return RedirectResponse(url="/?error=secret", status_code=303)
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["state"] = state
    # PKCE: same Flow instance is not reused on callback; persist verifier with state.
    if flow.code_verifier:
        request.session["code_verifier"] = flow.code_verifier
    return RedirectResponse(url=auth_url, status_code=303)


@app.get("/oauth2callback")
def oauth2callback(request: Request):
    print("OAUTH CALLBACK URL:", request.url)
    if request.query_params.get("error"):
        return RedirectResponse(url="/?error=oauth", status_code=303)
    saved_state = request.session.get("state")
    code_verifier = request.session.get("code_verifier")
    got_state = request.query_params.get("state")
    if (
        not saved_state
        or not code_verifier
        or not got_state
        or saved_state != got_state
    ):
        return RedirectResponse(url="/?error=oauth", status_code=303)
    client_config = _load_google_client_config()
    if client_config is None:
        return RedirectResponse(url="/?error=secret", status_code=303)
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        state=saved_state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = REDIRECT_URI
    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception as e:
        print("oauth2callback:", str(e))
        traceback.print_exc()
        return RedirectResponse(url="/?error=oauth", status_code=303)
    creds = flow.credentials
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    request.session.pop("state", None)
    request.session.pop("code_verifier", None)
    return RedirectResponse(url="/?login=ok", status_code=303)


@app.post("/upload")
async def upload(files: List[UploadFile] = File(default_factory=list)):
    if get_drive_service() is None:
        return RedirectResponse(url="/login", status_code=303)
    if not files:
        return RedirectResponse(url="/?error=tip", status_code=303)

    saved = 0
    for file in files:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXT:
            continue
        try:
            data = await file.read()
        except Exception as e:
            print("UPLOAD ERROR:", str(e))
            traceback.print_exc()
            return RedirectResponse(url="/?error=kayit", status_code=303)
        new_name = f"{uuid.uuid4().hex}{ext}"
        try:
            print("UPLOAD START:", new_name)
            result = upload_to_drive(data, new_name)
            print("UPLOAD SUCCESS:", result["url"])
            saved += 1
        except Exception as e:
            print("UPLOAD ERROR:", str(e))
            traceback.print_exc()
            return RedirectResponse(url="/?error=kayit", status_code=303)

    if saved == 0:
        return RedirectResponse(url="/?error=tip", status_code=303)
    return RedirectResponse(url="/?ok=1", status_code=303)


@app.get("/gallery")
async def gallery():
    items = list_gallery_items()
    body = build_gallery_html(items)
    return html_page("text/html; charset=utf-8", body)


def list_gallery_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    drive = get_drive_service()
    if drive is None:
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
            if mime == "application/vnd.google-apps.folder":
                continue
            fid = f.get("id")
            if not fid:
                continue
            is_video = mime.startswith("video/")
            is_image = mime.startswith("image/")
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
                    "url": drive_public_media_url(fid, mime),
                    "is_video": is_video,
                    "is_image": is_image,
                    "mime_type": mime,
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
