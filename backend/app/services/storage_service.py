"""
File storage for voice messages (Task 4.3). Same pattern as push / SMS: one small class now (local disk),
a cloud bucket later is one new class. Files are named by a random key, never by what the user sent.
"""

import os
import uuid
from pathlib import Path

from app.core.config import get_settings


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def save(self, data: bytes, ext: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        key = f"{uuid.uuid4().hex}{ext}"
        tmp = self.root / (key + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, self.root / key)  # a half-written file is never visible under its real name
        return key

    def path(self, key: str) -> Path | None:
        if not key or "/" in key or "\\" in key or ".." in key:
            return None
        p = self.root / key
        return p if p.is_file() else None

    def delete(self, key: str) -> None:
        p = self.path(key)
        if p:
            p.unlink(missing_ok=True)


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().VOICE_STORAGE_DIR or str(Path.home() / "humsafar_uploads" / "voice"))
