#!/usr/bin/env python3
"""Source-catalogue, coverage and acquisition self-tests (r5.9; acquisition controls added in r5.10)."""
import datetime as dt
import hashlib
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)

from eos import store  # noqa: E402
from eos.m2 import acquire, catalog, ingest  # noqa: E402

D = dt.date(2026, 9, 24)


def _check_catalogue():
    assert catalog.filename_for("nse_cm_bhavcopy", D) == "BhavCopy_NSE_CM_0_0_0_20260924_F_0000.csv.zip"
    assert catalog.filename_for("nse_cm_delivery", D) == "MTO_24092026.DAT"
    assert catalog.filename_for("nse_cm_security_master", D) == "NSE_CM_security_24092026.csv.gz"
    assert catalog.filename_for("nse_cm_full_bhav_delivery", D) == "sec_bhavdata_full_24092026.csv"
    assert catalog.filename_for("nse_cm_price_band", D) == "sec_list_24092026.csv"
    assert catalog.url_for("nse_cm_price_band", D).endswith("/content/equities/sec_list.csv")
    plans = catalog.planned_downloads([D])
    assert len(plans) == len(catalog.SOURCES)
    assert [p for p in plans if p["source_id"] == "nse_cm_price_band"][0]["parsed"] is False


def _check_capture_coverage():
    root = tempfile.mkdtemp()
    try:
        wh = store.Warehouse(os.path.join(root, "wh"), "jsonl")
        p = os.path.join(root, catalog.filename_for("nse_cm_price_band", D))
        open(p, "wb").write(b"SYMBOL,SERIES,BAND\nAAA,EQ,20\n")
        received = dt.datetime(2026, 9, 25, 1, 0, tzinfo=dt.timezone.utc)
        ingest.capture_unparsed_reference(wh, "nse_cm_price_band", p, received)
        rows = catalog.coverage_matrix(wh, [D], ["nse_cm_price_band", "nse_cm_delivery"])
        got = {(r["trade_date"], r["source_id"]): r for r in rows}
        assert got[(D, "nse_cm_price_band")]["status"] == "captured_unparsed"
        assert got[(D, "nse_cm_delivery")]["status"] == "missing"
        assert catalog.coverage_summary(rows)["by_status"] == {"captured_unparsed": 1, "missing": 1}
    finally:
        def retry(func, path, _exc):
            os.chmod(path, 0o700); func(path)
        if sys.version_info >= (3, 12): shutil.rmtree(root, onexc=retry)
        else: shutil.rmtree(root, onerror=retry)


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class _Headers(dict):
    def get(self, k, default=None): return super().get(k, default)


class _Opener:
    def __init__(self, payload, content_type=None, final_url=None):
        self.payload, self.urls, self.ctype, self.final = payload, [], content_type, final_url

    def open(self, req, timeout=30):
        self.urls.append(req.full_url)
        r = _Resp(self.payload)
        r.headers = _Headers({"Content-Type": self.ctype} if self.ctype else {})
        r.geturl = lambda: self.final or req.full_url
        return r


def _refused(fn, fragment):
    try:
        fn()
    except acquire.AcquisitionError as e:
        assert fragment in str(e), (fragment, str(e))
        return True
    raise AssertionError(f"not refused: expected {fragment!r}")


ZIP = b"PK\x03\x04" + b"\x00" * 20
GZ = b"\x1f\x8b\x08" + b"\x00" * 20
NOW = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)          # 17:30 IST on 24 Sep 2026


def _check_acquisition_controls():
    """r5.10 (review of r5.9): each control below was absent in r5.9 and each refusal would have been a silent save."""
    root = tempfile.mkdtemp()
    f = lambda sid, day, op, **k: acquire.fetch(sid, day, root, opener=op, now=NOW, warm_session=False,  # noqa: E731
                                                min_interval=0, **k)
    try:
        # the live price-band URL can only be captured for today's IST date
        _refused(lambda: f("nse_cm_price_band", dt.date(2021, 3, 5), _Opener(b"SYMBOL,SERIES\nA,EQ\n")), "only be captured")
        assert os.path.basename(f("nse_cm_price_band", D, _Opener(b"SYMBOL,SERIES\nA,EQ\n")).path) == "sec_list_24092026.csv"
        # an HTML block page served with HTTP 200 is not a data file (by content, and by content type)
        _refused(lambda: f("nse_cm_delivery", D, _Opener(b"<html><body>Access Denied</body></html>")), "HTML page")
        _refused(lambda: f("nse_cm_delivery", D, _Opener(b"fine text", content_type="text/html; charset=utf-8")), "HTML page")
        # zip and gzip sources must carry their magic bytes
        _refused(lambda: f("nse_cm_bhavcopy", D, _Opener(b"TradDt,BizDt\n")), "expected a zip")
        _refused(lambda: f("nse_cm_security_master", D, _Opener(b"FinInstrmId\n")), "expected a gzip")
        assert f("nse_cm_bhavcopy", D, _Opener(ZIP)).size_bytes == len(ZIP)
        assert f("nse_cm_security_master", D, _Opener(GZ)).size_bytes == len(GZ)
        # hosts: a redirect or final URL off NSE, and plain http, are refused
        handler = acquire._NSEOnlyRedirects()
        _refused(lambda: handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x.zip"), "non-NSE host")
        _refused(lambda: acquire.check_url("http://nsearchives.nseindia.com/content/cm/x.zip"), "non-https")
        _refused(lambda: f("nse_cm_delivery", D, _Opener(b"ok", final_url="https://cdn.example.net/MTO.DAT")), "non-NSE host")
        # an existing download is never overwritten: same bytes reused, a reissue saved beside it
        first = f("nse_cm_full_bhav_delivery", D, _Opener(b"SYMBOL,SERIES\nA,EQ\n"))
        again = f("nse_cm_full_bhav_delivery", D, _Opener(b"SYMBOL,SERIES\nA,EQ\n"))
        reissue = f("nse_cm_full_bhav_delivery", D, _Opener(b"SYMBOL,SERIES\nA,EQ\nB,EQ\n"))
        assert again.path == first.path and again.reused_existing
        assert os.path.basename(reissue.path).startswith("sec_bhavdata_full_24092026.reissue-") and not reissue.reused_existing
        assert open(first.path, "rb").read() == b"SYMBOL,SERIES\nA,EQ\n"
    finally:
        shutil.rmtree(root)


def _check_bhavcopy_layout_by_date():
    """r5.9's catalogue knew only the UDiFF URL, so no pre-July-2024 bhavcopy could be downloaded."""
    old, new = dt.date(2023, 1, 2), dt.date(2024, 7, 8)
    assert catalog.filename_for("nse_cm_bhavcopy", old) == "cm02JAN2023bhav.csv.zip"
    assert catalog.url_for("nse_cm_bhavcopy", old).endswith("/content/historical/EQUITIES/2023/JAN/cm02JAN2023bhav.csv.zip")
    assert catalog.filename_for("nse_cm_bhavcopy", new).startswith("BhavCopy_NSE_CM_0_0_0_20240708")
    assert catalog.filename_for("nse_cm_bhavcopy", old, variant="udiff").startswith("BhavCopy_NSE_CM_0_0_0_20230102")
    assert catalog.filename_for("nse_cm_bhavcopy", new, variant="legacy") == "cm08JUL2024bhav.csv.zip"
    import locale
    saved = locale.setlocale(locale.LC_TIME)
    for loc in ("de_DE.UTF-8", "fr_FR.UTF-8", "German_Germany.1252"):
        try:
            locale.setlocale(locale.LC_TIME, loc)
        except locale.Error:
            continue
        try:
            assert catalog.filename_for("nse_cm_bhavcopy", dt.date(2023, 3, 1)) == "cm01MAR2023bhav.csv.zip"
        finally:
            locale.setlocale(locale.LC_TIME, saved)


def _check_coverage_report_is_read_only():
    import subprocess
    root = tempfile.mkdtemp()
    try:
        missing = os.path.join(root, "no-such-warehouse")
        r = subprocess.run([sys.executable, os.path.join(KIT, "coverage_report.py"), missing, "2026-09-21", "2026-09-27",
                            "--codec", "jsonl"], capture_output=True, text=True, encoding="utf-8")
        assert r.returncode != 0 and "not a warehouse" in r.stderr and not os.path.exists(missing)
        store.Warehouse(os.path.join(root, "wh"), "jsonl")
        r = subprocess.run([sys.executable, os.path.join(KIT, "coverage_report.py"), os.path.join(root, "wh"),
                            "2026-09-21", "2026-09-27", "--codec", "jsonl", "--source", "nse_cm_delivery"],
                           capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0 and "coverage cells: 5" in r.stdout, r.stdout + r.stderr   # Mon-Fri only
    finally:
        shutil.rmtree(root)


def _check_fetch():
    root = tempfile.mkdtemp()
    try:
        payload = b"exchange bytes"
        op = _Opener(payload)
        now = dt.datetime(2026, 9, 25, 2, 3, tzinfo=dt.timezone.utc)
        r = acquire.fetch("nse_cm_delivery", D, root, opener=op, now=now, warm_session=False, min_interval=0)
        assert os.path.basename(r.path) == "MTO_24092026.DAT"
        assert open(r.path, "rb").read() == payload
        assert r.file_sha256 == hashlib.sha256(payload).hexdigest() and r.retrieved_at == now
        assert op.urls == [catalog.url_for("nse_cm_delivery", D)]
        try:
            acquire.fetch("unknown", D, root, opener=op, now=now, warm_session=False, min_interval=0)
        except KeyError:
            pass
        else:
            raise AssertionError("unknown source accepted")
    finally:
        shutil.rmtree(root)


def main():
    _check_catalogue(); print("ok    catalogue filenames and URLs")
    _check_capture_coverage(); print("ok    capture-only coverage remains non-semantic")
    _check_fetch(); print("ok    acquisition writes exact bytes and retrieval metadata")
    _check_acquisition_controls(); print("ok    acquisition refuses live-URL back-dating, HTML pages, wrong formats, off-NSE hosts; never overwrites")
    _check_bhavcopy_layout_by_date(); print("ok    bhavcopy URL follows the layout in use on the date, locale-independent")
    _check_coverage_report_is_read_only(); print("ok    coverage report counts weekdays and never creates a warehouse")
    print("6/6 source-catalogue/acquisition checks passed")


def test_catalogue_suite():
    main()


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    main()
