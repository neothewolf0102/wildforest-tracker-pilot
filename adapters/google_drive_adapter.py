from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from services.google_drive_service import DRIVE_FOLDER_MIME_TYPE

GOOGLE_DRIVE_API = "https://www.googleapis.com/drive/v3"
GOOGLE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"


@dataclass
class GoogleDriveRestClient:
    access_token: str
    timeout_seconds: int = 20

    def find_folder(self, folder_name: str, parent_id: str | None = None) -> str | None:
        query = f"mimeType='{DRIVE_FOLDER_MIME_TYPE}' and name='{folder_name}' and trashed=false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
        payload = self._request_json("GET", f"{GOOGLE_DRIVE_API}/files?{urlencode({'q': query, 'fields': 'files(id,name)'})}")
        files = payload.get("files", [])
        return str(files[0]["id"]) if files else None

    def create_folder(self, folder_name: str, parent_id: str | None = None) -> str:
        metadata = {"name": folder_name, "mimeType": DRIVE_FOLDER_MIME_TYPE}
        if parent_id:
            metadata["parents"] = [parent_id]
        payload = self._request_json("POST", f"{GOOGLE_DRIVE_API}/files", metadata)
        return str(payload["id"])

    def read_text_file(self, folder_id: str, filename: str) -> str:
        file_id = self._find_file_in_folder(folder_id, filename)
        if not file_id:
            return ""
        return self._request_text("GET", f"{GOOGLE_DRIVE_API}/files/{quote(file_id)}?alt=media")

    def upsert_text_file(self, folder_id: str, filename: str, content: str) -> str:
        return self.upsert_bytes_file(folder_id, filename, content.encode("utf-8"), "application/json; charset=utf-8")

    def upsert_bytes_file(self, folder_id: str, filename: str, content: bytes, mime_type: str) -> str:
        file_id = self._find_file_in_folder(folder_id, filename)
        if file_id:
            self._request_text("PATCH", f"{GOOGLE_UPLOAD_API}/files/{quote(file_id)}?uploadType=media", body=content, content_type=mime_type)
            return file_id
        payload = self._request_json("POST", f"{GOOGLE_DRIVE_API}/files", {"name": filename, "parents": [folder_id], "mimeType": mime_type.split(";")[0]})
        new_file_id = str(payload["id"])
        self._request_text("PATCH", f"{GOOGLE_UPLOAD_API}/files/{quote(new_file_id)}?uploadType=media", body=content, content_type=mime_type)
        return new_file_id

    def _find_file_in_folder(self, folder_id: str, filename: str) -> str | None:
        query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
        payload = self._request_json("GET", f"{GOOGLE_DRIVE_API}/files?{urlencode({'q': query, 'fields': 'files(id,name)'})}")
        files = payload.get("files", [])
        return str(files[0]["id"]) if files else None

    def _request_json(self, method: str, url: str, payload: dict | None = None) -> dict:
        text = self._request_text(method, url, body=json.dumps(payload).encode("utf-8") if payload is not None else None)
        return json.loads(text) if text else {}

    def _request_text(self, method: str, url: str, body: bytes | None = None, content_type: str = "application/json; charset=utf-8") -> str:
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": content_type}
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Google Drive API error {error.code}: {detail}") from error
