"""
EMFOX OMS v2.1 - PDF Export via iLovePDF API
===============================================
Converts generated Excel files to PDF using the iLovePDF REST API.
Requires a free API public key from https://developer.ilovepdf.com/
Set ILOVEPDF_PUBLIC_KEY in .env or environment.
"""

import io
import httpx
from app.config import settings


ILOVEPDF_BASE = "https://api.ilovepdf.com/v1"


async def excel_to_pdf(excel_buffer: io.BytesIO) -> bytes:
    """
    Convert an Excel file (BytesIO) to PDF using the iLovePDF API.

    Steps:
        1. Authenticate with public key → JWT token
        2. Start an 'officepdf' task → task_id + server
        3. Upload the Excel file
        4. Process (convert)
        5. Download the resulting PDF

    Returns:
        PDF file content as bytes

    Raises:
        ValueError: If API key is not configured
        Exception: On API errors
    """
    public_key = settings.ilovepdf_public_key
    if not public_key:
        raise ValueError(
            "ILOVEPDF_PUBLIC_KEY no configurada. "
            "Obtén una gratis en https://developer.ilovepdf.com/"
        )

    async with httpx.AsyncClient(timeout=120.0) as client:
        # Step 1: Authenticate → get JWT token
        auth_resp = await client.post(
            f"{ILOVEPDF_BASE}/auth",
            json={"public_key": public_key},
        )
        auth_resp.raise_for_status()
        token = auth_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Step 2: Start officepdf task
        start_resp = await client.get(
            f"{ILOVEPDF_BASE}/start/officepdf",
            headers=headers,
        )
        start_resp.raise_for_status()
        task_data = start_resp.json()
        server = task_data["server"]
        task_id = task_data["task"]

        server_base = f"https://{server}/v1"

        # Step 3: Upload the Excel file
        excel_buffer.seek(0)
        upload_resp = await client.post(
            f"{server_base}/upload",
            headers=headers,
            data={"task": task_id},
            files={
                "file": (
                    "export.xlsx",
                    excel_buffer.read(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        upload_resp.raise_for_status()
        server_filename = upload_resp.json()["server_filename"]

        # Step 4: Process (convert to PDF)
        process_resp = await client.post(
            f"{server_base}/process",
            headers=headers,
            json={
                "task": task_id,
                "tool": "officepdf",
                "files": [
                    {
                        "server_filename": server_filename,
                        "filename": "export.xlsx",
                    }
                ],
            },
        )
        process_resp.raise_for_status()

        # Step 5: Download the PDF
        download_resp = await client.get(
            f"{server_base}/download/{task_id}",
            headers=headers,
        )
        download_resp.raise_for_status()

        return download_resp.content
