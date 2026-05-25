"""
blob_utils.py
-----
Utilities for reading from and writing to Vercel Blob storage.

Uses the Vercel Blob HTTP REST API to:
  - List files stored in Blob (list_blob_files)
  - Download files from Blob (download_blob_file)
  - Upload files to Blob (upload_blob_file)
"""

import os
import re
import requests
from typing import Optional, List, Dict


def _get_token() -> str:
    """Get BLOB_READ_WRITE_TOKEN from environment."""
    token = os.getenv("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise ValueError("BLOB_READ_WRITE_TOKEN not set in environment")
    return token.strip()


def _get_store_url(token: str) -> str:
    """
    Derive the store-specific base URL from the token.
    Token format: vercel_blob_rw_STOREID_...
    Store URL: https://STOREID.private.blob.vercel-storage.com
    """
    m = re.match(r"vercel_blob_rw_([A-Za-z0-9]+)", token)
    if not m:
        raise ValueError(f"Cannot extract store ID from token")
    store_id = m.group(1).lower()
    return f"https://{store_id}.private.blob.vercel-storage.com"


def list_blob_files(prefix: str = "") -> List[Dict[str, str]]:
    """
    List all files in Vercel Blob storage, optionally filtered by prefix.
    Returns list of dicts with keys: pathname, url, size, uploadedAt.
    """
    try:
        token = _get_token()
        all_blobs = []
        cursor = None
        while True:
            params: Dict[str, str] = {"limit": "1000"}
            if prefix:
                params["prefix"] = prefix
            if cursor:
                params["cursor"] = cursor
            response = requests.get(
                "https://blob.vercel-storage.com",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()
            all_blobs.extend(data.get("blobs", []))
            if data.get("hasMore") and data.get("cursor"):
                cursor = data["cursor"]
            else:
                break
        return all_blobs
    except Exception as e:
        print(f"Error listing Blob files: {e}")
        return []


def download_blob_file(pathname: str) -> Optional[bytes]:
    """
    Download a private file from Vercel Blob by pathname.
    Uses Authorization header for private blob access.
    """
    try:
        token = _get_token()
        store_url = _get_store_url(token)
        url = f"{store_url}/{pathname}"
        response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error downloading {pathname} from Blob: {e}")
        return None
