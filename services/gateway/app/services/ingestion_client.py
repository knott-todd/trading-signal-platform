"""
Thin HTTP client for calling Module 01 internal API.
The gateway never calls module APIs from the frontend directly.
"""
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from services.gateway.app.config import settings

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


async def get(path: str, params: Optional[Dict] = None) -> Any:
    url = f"{settings.ingestion_api_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        log.error("Cannot reach Module 01 at %s", url)
        raise HTTPException(status_code=503, detail="Module 01 (ingestion) is unreachable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


async def post(path: str, body: Dict) -> Any:
    url = f"{settings.ingestion_api_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Module 01 (ingestion) is unreachable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


async def patch(path: str, body: Dict) -> Any:
    url = f"{settings.ingestion_api_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.patch(url, json=body)
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Module 01 (ingestion) is unreachable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)


async def delete(path: str) -> Any:
    url = f"{settings.ingestion_api_url}{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.delete(url)
            if r.status_code == 204:
                return None
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Module 01 (ingestion) is unreachable.")
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
