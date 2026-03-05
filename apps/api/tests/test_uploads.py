from __future__ import annotations

import io

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_upload_csv_file(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "Upload Corp"},
    )
    session_id = create_resp.json()["id"]

    csv_content = b"name,value\nAlpha,100\nBeta,200\nGamma,300\n"
    files = {"file": ("test.csv", io.BytesIO(csv_content), "text/csv")}

    response = await client.post(f"/sessions/{session_id}/upload", files=files)
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "test.csv"
    assert data["file_type"] == "csv"
    assert data["size_bytes"] == len(csv_content)


@pytest.mark.asyncio
async def test_upload_invalid_extension(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "Bad Upload Corp"},
    )
    session_id = create_resp.json()["id"]

    files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
    response = await client.post(f"/sessions/{session_id}/upload", files=files)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_files(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/sessions",
        json={"company_name": "List Corp"},
    )
    session_id = create_resp.json()["id"]

    csv_content = b"col1,col2\n1,2\n"
    files = {"file": ("data.csv", io.BytesIO(csv_content), "text/csv")}
    await client.post(f"/sessions/{session_id}/upload", files=files)

    response = await client.get(f"/sessions/{session_id}/files")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["files"]) >= 1
