#!/usr/bin/env python3
"""r5.9 source-catalogue, coverage and conservative acquisition self-tests."""
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


class _Opener:
    def __init__(self, payload): self.payload = payload; self.urls = []
    def open(self, req, timeout=30):
        self.urls.append(req.full_url)
        return _Resp(self.payload)


def _check_fetch():
    root = tempfile.mkdtemp()
    try:
        payload = b"exchange bytes"
        op = _Opener(payload)
        now = dt.datetime(2026, 9, 25, 2, 3, tzinfo=dt.timezone.utc)
        r = acquire.fetch("nse_cm_delivery", D, root, opener=op, now=now, warm_session=False)
        assert os.path.basename(r.path) == "MTO_24092026.DAT"
        assert open(r.path, "rb").read() == payload
        assert r.file_sha256 == hashlib.sha256(payload).hexdigest() and r.retrieved_at == now
        assert op.urls == [catalog.url_for("nse_cm_delivery", D)]
        try:
            acquire.fetch("unknown", D, root, opener=op, now=now, warm_session=False)
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
    print("3/3 source-catalogue/acquisition checks passed")


def test_catalogue_suite():
    main()


if __name__ == "__main__":
    main()
