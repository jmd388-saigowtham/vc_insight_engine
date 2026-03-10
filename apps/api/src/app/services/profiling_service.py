from __future__ import annotations

import math
import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.column_profile import ColumnProfile
from app.models.uploaded_file import UploadedFile

LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100MB
SAMPLE_ROWS = 100_000


class ProfilingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def profile_file(self, file_id: uuid.UUID) -> list[ColumnProfile]:
        uploaded = await self.db.get(UploadedFile, file_id)
        if uploaded is None:
            raise ValueError(f"File {file_id} not found")

        # For XLSX files with multiple sheets, profile the first sheet
        # and log available sheets for user awareness
        sheet_name: int | str = 0
        if uploaded.file_type == "xlsx":
            sheet_names = self.get_xlsx_sheet_names(uploaded.storage_path)
            if len(sheet_names) > 1:
                # Store sheet names metadata on the uploaded file
                if hasattr(uploaded, "metadata_") and uploaded.metadata_ is not None:
                    uploaded.metadata_["sheet_names"] = sheet_names
                    uploaded.metadata_["profiled_sheet"] = sheet_names[0]

        df = self._read_file(
            uploaded.storage_path, uploaded.file_type, uploaded.size_bytes,
            sheet_name=sheet_name,
        )

        uploaded.row_count = len(df)
        uploaded.column_count = len(df.columns)

        profiles: list[ColumnProfile] = []
        for col_name in df.columns:
            series = df[col_name]
            profile = self._profile_column(file_id, col_name, series, len(df))
            profiles.append(profile)
            self.db.add(profile)

        await self.db.commit()
        for p in profiles:
            await self.db.refresh(p)
        return profiles

    def _read_file(
        self, storage_path: str, file_type: str, size_bytes: int, sheet_name: int | str = 0
    ) -> pd.DataFrame:
        path = Path(storage_path)
        if file_type == "csv":
            if size_bytes > LARGE_FILE_THRESHOLD:
                return pd.read_csv(path, nrows=SAMPLE_ROWS)
            return pd.read_csv(path)
        elif file_type == "xlsx":
            if size_bytes > LARGE_FILE_THRESHOLD:
                return pd.read_excel(path, nrows=SAMPLE_ROWS, sheet_name=sheet_name)
            return pd.read_excel(path, sheet_name=sheet_name)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    def get_xlsx_sheet_names(self, storage_path: str) -> list[str]:
        """Return the list of sheet names in an XLSX file."""
        path = Path(storage_path)
        if not path.exists():
            return []
        try:
            xls = pd.ExcelFile(path)
            return xls.sheet_names
        except Exception:
            return []

    def _profile_column(
        self,
        file_id: uuid.UUID,
        col_name: str,
        series: pd.Series,
        total_rows: int,
    ) -> ColumnProfile:
        null_count = int(series.isna().sum())
        null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0.0
        unique_count = int(series.nunique())

        min_value = None
        max_value = None
        mean_value = None

        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                min_val = clean.min()
                max_val = clean.max()
                mean_val = clean.mean()
                min_value = str(min_val) if not (isinstance(min_val, float) and math.isnan(min_val)) else None
                max_value = str(max_val) if not (isinstance(max_val, float) and math.isnan(max_val)) else None
                mean_value = float(mean_val) if not math.isnan(mean_val) else None
        else:
            clean = series.dropna().astype(str)
            if len(clean) > 0:
                min_value = str(clean.min())
                max_value = str(clean.max())

        sample_values = series.dropna().head(5).tolist()
        sample_values = [
            str(v) if not isinstance(v, (int, float, bool)) else v
            for v in sample_values
        ]

        return ColumnProfile(
            id=uuid.uuid4(),
            file_id=file_id,
            column_name=str(col_name),
            dtype=str(series.dtype),
            null_count=null_count,
            null_pct=round(null_pct, 2),
            unique_count=unique_count,
            min_value=min_value,
            max_value=max_value,
            mean_value=mean_value,
            sample_values=sample_values,
        )

    async def get_profiles(self, file_id: uuid.UUID) -> list[ColumnProfile]:
        stmt = (
            select(ColumnProfile)
            .where(ColumnProfile.file_id == file_id)
            .order_by(ColumnProfile.column_name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_description(
        self, column_id: uuid.UUID, description: str
    ) -> ColumnProfile | None:
        profile = await self.db.get(ColumnProfile, column_id)
        if profile is None:
            return None
        profile.description = description
        await self.db.commit()
        await self.db.refresh(profile)
        return profile

    async def get_session_tables(
        self, session_id: uuid.UUID
    ) -> list[dict]:
        stmt = select(UploadedFile).where(UploadedFile.session_id == session_id)
        result = await self.db.execute(stmt)
        files = list(result.scalars().all())

        tables = []
        for f in files:
            profiles = await self.get_profiles(f.id)
            tables.append({
                "file_id": f.id,
                "filename": f.filename,
                "row_count": f.row_count,
                "column_count": f.column_count,
                "columns": profiles,
            })
        return tables
