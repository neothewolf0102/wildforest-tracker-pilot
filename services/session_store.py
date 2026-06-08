from __future__ import annotations

import copy
from dataclasses import dataclass, field


@dataclass
class SessionJsonStore:
    namespace: str
    files: dict[str, list[dict]] = field(default_factory=dict)

    def load_json(self, filename: str, default: list | None = None) -> list:
        return copy.deepcopy(self.files.get(filename, default or []))

    def save_json(self, filename: str, data: list[dict]) -> None:
        self.files[filename] = copy.deepcopy(data)

    def save_report_text(self, filename: str, content: str) -> str:
        self.files[f"reports/{filename}"] = [{"content": content}]
        return f"session://{self.namespace}/reports/{filename}"

    def save_report_bytes(self, filename: str, content: bytes, mime_type: str) -> str:
        self.files[f"reports/{filename}"] = [{"bytes": len(content), "mime_type": mime_type}]
        return f"session://{self.namespace}/reports/{filename}"
