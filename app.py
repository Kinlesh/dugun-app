# -*- coding: utf-8 -*-
"""
Himmet & Cennet düğün albümü — FastAPI.
Yüklemeler Google Drive'a gider; galeri Drive klasöründen listelenir.
Kimlik doğrulama gerektirmez; GOOGLE_CREDS ortam değişkenindeki servis hesabı JSON ile Drive erişimi.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Google Drive hedef klasör
FOLDER_ID = "17AYafv6kTUDeIK7UBgukOohTdUhJ4UNQ"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif"}
ALLOWED_VIDEO = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
ALLOWED_EXT = ALLOWED_IMAGE | ALLOWED_VIDEO


def get_drive_service():
    print("GOOGLE_CREDS LENGTH:", len(os.getenv("GOOGLE_CREDS") or ""))
    print("FOLDER_ID:", FOLDER_ID)

    creds_json = os.getenv("GOOGLE_CREDS")
    if not creds_json:
        raise Exception("GOOGLE_CREDS missing")

    creds_dict = json.loads(creds_json)

    creds = service_account.Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive"],
    )

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def build_drive_url(file_id: str, mime_type: str) -> str:
    if mime_type.startswith("image/"):
        return f"https://lh3.googleusercontent.com/d/{file_id}"
    if mime_type.startswith("video/"):
        return f"https://drive.google.com/file/d/{file_id}/preview"
    return f"https://drive.google.com/file/d/{file_id}/view"


def upload_to_drive(
    file_bytes: bytes, filename: str, drive: Any | None = None
) -> dict[str, Any]:
    """Dosyayı FOLDER_ID altına yükler, anyone reader izni verir."""
    if drive is None:
        drive = get_drive_service()

    mime, _ = mimetypes.guess_type(filename)
    mime = mime or "application/octet-stream"
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime, resumable=True)

    file_metadata = {"name": filename, "parents": [FOLDER_ID]}
    file = (
        drive.files()
        .create(
            body=file_metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )

    file_id = file["id"]
    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
        supportsAllDrives=True,
    ).execute()

    return {
        "id": file_id,
        "url": build_drive_url(file_id, mime),
        "mime": mime,
    }


def list_gallery_items() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    try:
        drive = get_drive_service()
    except Exception as e:
        print("list_gallery_items:", str(e))
        return files
    try:
        page_token = None
        while True:
            response = (
                drive.files()
                .list(
                    q=f"'{FOLDER_ID}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name, mimeType)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    pageSize=100,
                    pageToken=page_token,
                )
                .execute()
            )

            for f in response.get("files", []):
                mime = f.get("mimeType") or ""
                if mime == "application/vnd.google-apps.folder":
                    continue
                fid = f.get("id")
                if not fid:
                    continue
                files.append(
                    {
                        "id": fid,
                        "name": f.get("name") or "",
                        "url": build_drive_url(fid, mime),
                        "mime": mime,
                        "is_image": mime.startswith("image/"),
                        "is_video": mime.startswith("video/"),
                    }
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception:
        traceback.print_exc()
    return files


def ensure_project_layout() -> None:
    try:
        STATIC_DIR.mkdir(parents=True, exist_ok=True)
        TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


ensure_project_layout()

app = FastAPI(title="Himmet & Cennet Düğün Albümü")

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index(
    request: Request,
    ok: Optional[str] = None,
    error: Optional[str] = None,
):
    success = ok == "1"
    error_message: Optional[str] = None
    if error == "tip":
        error_message = "Lütfen fotoğraf veya video dosyası seçin."
    elif error == "kayit":
        error_message = "Gönderilemedi. Bir kez daha deneyin."
    elif error == "drive":
        error_message = (
            "Drive kullanılamıyor. GOOGLE_CREDS ortam değişkeninde geçerli "
            "servis hesabı JSON olduğundan ve klasör paylaşımının tanımlı olduğundan emin olun."
        )
    items = list_gallery_items()
    # Starlette 1.x: TemplateResponse(request, name, context); request is injected into context.
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "success": success,
            "error_message": error_message,
            "items": items,
        },
    )


@app.post("/upload")
async def upload(files: List[UploadFile] = File(default_factory=list)):
    try:
        drive = get_drive_service()
    except Exception as e:
        print("DRIVE ERROR:", str(e))
        traceback.print_exc()
        raise
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
            result = upload_to_drive(data, new_name, drive=drive)
            print("UPLOAD SUCCESS:", result.get("url"))
            saved += 1
        except Exception as e:
            print("UPLOAD ERROR:", str(e))
            traceback.print_exc()
            return RedirectResponse(url="/?error=kayit", status_code=303)

    if saved == 0:
        return RedirectResponse(url="/?error=tip", status_code=303)
    return RedirectResponse(url="/?ok=1", status_code=303)


@app.get("/gallery")
async def gallery(request: Request):
    items = list_gallery_items()
    return templates.TemplateResponse(
        request,
        "gallery.html",
        {"items": items},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
