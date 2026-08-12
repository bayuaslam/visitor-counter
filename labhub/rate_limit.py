import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


_LOCK = threading.Lock()
_HITS: dict[str, deque[float]] = defaultdict(deque)


def _client_key(request: Request) -> str:
    if os.getenv("LABHUB_TRUST_PROXY", "0").strip() == "1":
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:100]
    if request.client and request.client.host:
        return request.client.host[:100]
    return "unknown"


def enforce_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    key = f"{bucket}:{_client_key(request)}"

    with _LOCK:
        hits = _HITS[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0])))
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak permintaan. Coba lagi beberapa saat.",
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)
