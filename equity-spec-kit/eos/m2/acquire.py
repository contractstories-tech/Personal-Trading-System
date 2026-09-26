"""Conservative NSE file acquisition helper (r5.9; hardened in r5.10).

This module downloads bytes only; it never writes warehouse observations. Callers pass the returned path, source
URL and retrieval time to the normal ingestion or capture function, which lands, hashes and receipts the file.

Controls (r5.10, review of r5.9):
  * https only, and every host - including every REDIRECT target - must be an NSE host (r5.9 checked only the
    first URL; urllib followed redirects anywhere);
  * the payload must look like the source's real file: zip or gzip magic bytes, or text that is not an HTML page.
    NSE's anti-bot layer can answer HTTP 200 with an HTML page, which r5.9 saved as the data file;
  * a size cap, and a minimum interval between requests so a multi-year loop does not hammer NSE;
  * a live-URL source (the price-band list) can only be captured for the retrieval date in IST, because the URL
    always serves the current list; r5.9 would label today's list with any past date it was given;
  * an existing download is never overwritten: identical bytes are reused, different bytes (a reissue) are saved
    beside it as <stem>.reissue-<sha12><ext>;
  * retrieved_at is taken when the response has been read, before anything is written.
Live NSE behaviour (session warm-up, anti-bot changes) remains external acceptance.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import http.cookiejar
import os
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

from .. import fsio
from ..timeutil import IST
from .catalog import source_spec

ALLOWED_HOSTS = {"www.nseindia.com", "nseindia.com", "nsearchives.nseindia.com"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/153.0 Safari/537.36"
MAX_BYTES = 256 * 1024 * 1024
MIN_INTERVAL_SECONDS = 2.0
_last_request = [0.0]
_pace_lock = threading.Lock()


class AcquisitionError(IOError):
    """The response was not a genuine source file, or the request broke an acquisition control."""


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    trade_date: dt.date
    path: str
    source_url: str
    retrieved_at: dt.datetime
    file_sha256: str
    size_bytes: int
    reused_existing: bool = False


def check_url(url):
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        raise AcquisitionError(f"refusing non-https URL {url!r}")
    if host not in ALLOWED_HOSTS:
        raise AcquisitionError(f"refusing non-NSE host {host!r}")
    return url


class _NSEOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), _NSEOnlyRedirects())


def _pace(min_interval):
    with _pace_lock:
        wait = _last_request[0] + min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _read(opener, url, min_interval):
    check_url(url)
    _pace(min_interval)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
    with opener.open(req, timeout=30) as r:
        final = getattr(r, "geturl", lambda: url)() or url
        check_url(final)
        ctype = ""
        headers = getattr(r, "headers", None)
        if headers is not None:
            ctype = (headers.get("Content-Type") or "").lower()
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise AcquisitionError(f"{url}: response exceeds {MAX_BYTES} bytes")
    return data, ctype


def check_payload(content, data, ctype, url):
    """Refuse a response that is not the source's real file (an HTML block page, a truncated or empty body)."""
    if not data:
        raise AcquisitionError(f"empty response from {url}")
    head = data[:2048].lstrip().lower()
    if "text/html" in ctype or head.startswith(b"<") or b"<html" in head:
        raise AcquisitionError(f"{url}: the server returned an HTML page, not the file (blocked or not published?)")
    if content == "zip" and not data.startswith(b"PK\x03\x04"):
        raise AcquisitionError(f"{url}: expected a zip archive; got {data[:8]!r}")
    if content == "gzip" and not data.startswith(b"\x1f\x8b"):
        raise AcquisitionError(f"{url}: expected a gzip file; got {data[:8]!r}")
    if content == "text" and b"\x00" in data[:4096]:
        raise AcquisitionError(f"{url}: expected a text file; got binary bytes")


def _save(dest_dir, name, payload):
    """Write payload as dest_dir/name without ever replacing different existing bytes."""
    os.makedirs(dest_dir, exist_ok=True)
    final = os.path.join(dest_dir, name)
    sha = hashlib.sha256(payload).hexdigest()
    if os.path.exists(final):
        if hashlib.sha256(fsio.read_bytes(final)).hexdigest() == sha:
            return final, True
        stem, ext = name.split(".", 1) if "." in name else (name, "")
        final = os.path.join(dest_dir, f"{stem}.reissue-{sha[:12]}" + (f".{ext}" if ext else ""))
        if os.path.exists(final):
            return final, True
    fsio.write_durable(final, payload, f".download-{os.getpid()}-{uuid.uuid4().hex}")
    return final, False


def fetch(source_id, day, dest_dir, opener=None, now=None, warm_session=True, variant=None,
          min_interval=MIN_INTERVAL_SECONDS):
    spec = source_spec(source_id, day, variant)
    url = check_url(spec.url(day))
    if spec.static_live_url:
        today = (now or dt.datetime.now(dt.timezone.utc)).astimezone(IST).date()
        if day != today:
            raise AcquisitionError(f"{source_id} is served from a live URL that always returns the current file; it can "
                                   f"only be captured for today's date {today} (IST), not {day}")
    opener = opener or _default_opener()
    if warm_session:
        try:
            _read(opener, "https://www.nseindia.com/all-reports", min_interval)
        except Exception:
            # Archive downloads sometimes work without the warm-up; the source fetch below remains authoritative.
            pass
    payload, ctype = _read(opener, url, min_interval)
    retrieved = now or dt.datetime.now(dt.timezone.utc)
    if retrieved.tzinfo is None:
        raise ValueError("now/retrieved_at must be timezone-aware")
    check_payload(spec.content, payload, ctype, url)
    final, reused = _save(dest_dir, spec.filename(day), payload)
    return FetchResult(source_id, day, final, url, retrieved, hashlib.sha256(payload).hexdigest(), len(payload), reused)
