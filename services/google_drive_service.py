from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from services.auth_service import WILDFOREST_DRIVE_FOLDER_NAME, AuthenticatedUser

DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class DriveUserContext:
    user: AuthenticatedUser
    access_token: str
    root_folder_id: str
    folder_name: str = WILDFOREST_DRIVE_FOLDER_NAME

    @property
    def user_id(self) -> str:
        return self.user.user_id


class DriveClient(Protocol):
    def find_folder(self, folder_name: str, parent_id: str | None = None) -> str | None: ...
    def create_folder(self, folder_name: str, parent_id: str | None = None) -> str: ...
    def read_text_file(self, folder_id: str, filename: str) -> str: ...
    def upsert_text_file(self, folder_id: str, filename: str, content: str) -> str: ...
    def upsert_bytes_file(self, folder_id: str, filename: str, content: bytes, mime_type: str) -> str: ...


def ensure_wildforest_drive_folder(client: DriveClient, folder_name: str = WILDFOREST_DRIVE_FOLDER_NAME) -> str:
    existing_id = client.find_folder(folder_name)
    if existing_id:
        return existing_id
    return client.create_folder(folder_name)


def build_drive_user_context(user: AuthenticatedUser, access_token: str, client: DriveClient, folder_name: str = WILDFOREST_DRIVE_FOLDER_NAME) -> DriveUserContext:
    if not access_token:
        raise ValueError("Google Drive access token is required.")
    folder_id = ensure_wildforest_drive_folder(client, folder_name)
    return DriveUserContext(user=user, access_token=access_token, root_folder_id=folder_id, folder_name=folder_name)


@dataclass
class DriveJsonStore:
    client: DriveClient
    context: DriveUserContext

    def load_json(self, filename: str, default=None):
        text = self.client.read_text_file(self.context.root_folder_id, filename)
        if not text.strip():
            return default if default is not None else []
        return json.loads(text)

    def save_json(self, filename: str, data) -> str:
        return self.client.upsert_text_file(self.context.root_folder_id, filename, json.dumps(data, ensure_ascii=False, indent=2))

    def save_report_text(self, filename: str, content: str) -> str:
        return self.client.upsert_bytes_file(self.context.root_folder_id, f"reports/{filename}", content.encode("utf-8"), "text/csv; charset=utf-8")

    def save_report_bytes(self, filename: str, content: bytes, mime_type: str) -> str:
        return self.client.upsert_bytes_file(self.context.root_folder_id, f"reports/{filename}", content, mime_type)
