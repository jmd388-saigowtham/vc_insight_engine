from __future__ import annotations

import uuid
from pathlib import Path


class StorageService:
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, content: bytes, filename: str) -> str:
        ext = Path(filename).suffix
        storage_name = f"{uuid.uuid4().hex}{ext}"
        storage_path = self.upload_dir / storage_name
        storage_path.write_bytes(content)
        return str(storage_path)

    def get_file(self, storage_path: str) -> bytes:
        path = Path(storage_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return path.read_bytes()

    def delete_file(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            path.unlink()
