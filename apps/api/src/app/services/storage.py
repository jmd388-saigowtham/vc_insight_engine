from __future__ import annotations

import uuid
from pathlib import Path


class StorageService:
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_file(
        self,
        content: bytes,
        filename: str,
        session_id: str | None = None,
    ) -> str:
        """Save a file to storage.

        If session_id is provided, stores in <upload_dir>/<session_id>/raw/.
        Otherwise falls back to flat storage for backward compatibility.
        """
        if session_id:
            session_dir = self.upload_dir / session_id / "raw"
            session_dir.mkdir(parents=True, exist_ok=True)
            # Use original filename (dedup with uuid prefix if collision)
            storage_path = session_dir / filename
            if storage_path.exists():
                ext = Path(filename).suffix
                stem = Path(filename).stem
                storage_path = session_dir / f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
            storage_path.write_bytes(content)
            return str(storage_path)

        # Backward compatibility: flat storage
        ext = Path(filename).suffix
        storage_name = f"{uuid.uuid4().hex}{ext}"
        storage_path = self.upload_dir / storage_name
        storage_path.write_bytes(content)
        return str(storage_path)

    def _validate_path(self, storage_path: str) -> Path:
        """Ensure the resolved path is within the upload directory."""
        path = Path(storage_path).resolve()
        if not path.is_relative_to(self.upload_dir.resolve()):
            raise ValueError("Access denied: path traversal detected")
        return path

    def get_file(self, storage_path: str) -> bytes:
        path = self._validate_path(storage_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return path.read_bytes()

    def delete_file(self, storage_path: str) -> None:
        path = self._validate_path(storage_path)
        if path.exists():
            path.unlink()
