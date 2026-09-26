"""Conservative NSE file acquisition helper (r5.9).

This module downloads bytes only; it never writes warehouse observations. Callers must pass the returned path,
source URL and retrieved timestamp to the normal ingestion function, which lands/hashes/receipts the file again.
The default opener warms an NSE web session and uses a browser-like User-Agent, but live acceptance remains an
external test because NSE can change anti-bot/session behaviour independently of this release.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import http.cookiejar
import os
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from .. import fsio
from .catalog import filename_for, url_for

ALLOWED_HOSTS = {"www.nseindia.com", "nseindia.com", "nsearchives.nseindia.com"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0 Safari/537.36"


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    trade_date: dt.date
    path: str
    source_url: str
    retrieved_at: dt.datetime
    file_sha256: str
    size_bytes: int


def _default_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _read(opener, url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
    with opener.open(req, timeout=30) as r:
        return r.read()


def fetch(source_id, day, dest_dir, opener=None, now=None, warm_session=True):
    url = url_for(source_id, day)
    host = (urlparse(url).hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"refusing non-NSE download host {host!r}")
    opener = opener or _default_opener()
    if warm_session:
        try:
            _read(opener, "https://www.nseindia.com/all-reports")
        except Exception:
            # Archive downloads sometimes work without the warm-up. The actual source fetch remains authoritative;
            # callers receive its exception if it fails.
            pass
    payload = _read(opener, url)
    if not payload:
        raise IOError(f"empty response from {url}")
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, filename_for(source_id, day))
    fsio.write_durable(final, payload, f".download-{os.getpid()}-{uuid.uuid4().hex}")
    retrieved = now or dt.datetime.now(dt.timezone.utc)
    if retrieved.tzinfo is None:
        raise ValueError("now/retrieved_at must be timezone-aware")
    return FetchResult(source_id, day, final, url, retrieved, hashlib.sha256(payload).hexdigest(), len(payload))
