"""NSE end-of-day file parsers.

Written from the documented layouts, NOT yet checked against real files: each parser fingerprints the
header exactly and raises FormatError on anything it does not recognise. Hardening against Harsh's
sample files is the first task once they are uploaded.

  nse_bhavcopy_legacy  cmDDMONYYYYbhav.csv            SYMBOL,SERIES,OPEN,...,TIMESTAMP,TOTALTRADES,ISIN
  nse_bhavcopy_udiff   BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv   TradDt,BizDt,Sgmt,...
  nse_mto_delivery     MTO_DDMMYYYY.DAT               record type 20 rows; no ISIN (mapped via bhavcopy)
"""
import csv
import datetime as dt
import decimal
import io
import zipfile

D4 = decimal.Decimal("0.0001")


class FormatError(Exception):
    pass


LEGACY_COLS = ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE",
               "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES", "ISIN"]
UDIFF_REQUIRED = ["TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN", "TckrSymb", "SctySrs",
                  "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric",
                  "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd"]


def read_bytes(path):
    """Plain file, or a zip holding exactly one member."""
    raw = open(path, "rb").read()
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in z.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise FormatError(f"{path}: zip must hold exactly one file, found {names}")
        return z.read(names[0])
    return raw


def money(s, field, where):
    s = s.strip()
    try:
        v = decimal.Decimal(s)
    except decimal.InvalidOperation:
        raise FormatError(f"{where}: {field}={s!r} is not a number")
    q = v.quantize(D4)
    if q != v:
        raise FormatError(f"{where}: {field}={s!r} has more than 4 decimal places")
    return q


def integer(s, field, where):
    s = s.strip()
    try:
        d = decimal.Decimal(s)
    except decimal.InvalidOperation:
        raise FormatError(f"{where}: {field}={s!r} is not a number")
    if d != d.to_integral_value():
        raise FormatError(f"{where}: {field}={s!r} is not a whole number")
    return int(d)


def _rows(text):
    return list(csv.reader(io.StringIO(text)))


def parse_bhavcopy(data, name="<file>"):
    """Returns (format, trade_date, rows). Rows carry raw values only; availability is added by ingest."""
    text = data.decode("utf-8-sig")
    rows = _rows(text)
    if not rows:
        raise FormatError(f"{name}: empty file")
    header = [h.strip() for h in rows[0]]
    while header and header[-1] == "":
        header.pop()
    if header == LEGACY_COLS:
        fmt = "nse_bhavcopy_legacy"
        col = {h: i for i, h in enumerate(header)}
        get = lambda r, k: r[col[k]]  # noqa: E731
        m = dict(symbol="SYMBOL", series="SERIES", open="OPEN", high="HIGH", low="LOW", close="CLOSE",
                 prev_close="PREVCLOSE", volume="TOTTRDQTY", traded_value="TOTTRDVAL", num_trades="TOTALTRADES",
                 isin="ISIN")
        date_of = lambda r: dt.datetime.strptime(get(r, "TIMESTAMP").strip().title(), "%d-%b-%Y").date()  # noqa
    elif all(c in header for c in UDIFF_REQUIRED):
        fmt = "nse_bhavcopy_udiff"
        col = {h: i for i, h in enumerate(header)}
        get = lambda r, k: r[col[k]]  # noqa: E731
        m = dict(symbol="TckrSymb", series="SctySrs", open="OpnPric", high="HghPric", low="LwPric", close="ClsPric",
                 prev_close="PrvsClsgPric", volume="TtlTradgVol", traded_value="TtlTrfVal",
                 num_trades="TtlNbOfTxsExctd", isin="ISIN")
        date_of = lambda r: dt.date.fromisoformat(get(r, "TradDt").strip())  # noqa: E731
    else:
        raise FormatError(f"{name}: unrecognised bhavcopy header {header[:8]}...")

    out, dates = [], set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        where = f"{name} line {i}"
        if fmt == "nse_bhavcopy_udiff" and get(r, "Sgmt").strip() != "CM":
            raise FormatError(f"{where}: segment {get(r, 'Sgmt')!r} in a CM bhavcopy")
        d = date_of(r)
        dates.add(d)
        out.append({
            "isin": get(r, m["isin"]).strip(), "symbol": get(r, m["symbol"]).strip(),
            "series": get(r, m["series"]).strip(),
            **{k: money(get(r, m[k]), k, where) for k in ("open", "high", "low", "close", "prev_close", "traded_value")},
            **{k: integer(get(r, m[k]), k, where) for k in ("volume", "num_trades")},
        })
    if len(dates) != 1:
        raise FormatError(f"{name}: expected one trade date, found {sorted(dates)}")
    return fmt, dates.pop(), out


def parse_mto(data, name="<file>"):
    """Security-wise delivery position. Returns (format, trade_date, rows keyed by symbol+series)."""
    text = data.decode("utf-8-sig")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or "Security Wise Delivery Position" not in lines[0]:
        raise FormatError(f"{name}: not an MTO delivery file (first line {lines[0][:60] if lines else ''!r})")
    trade_date = None
    for l in lines[1:4]:
        f = [x.strip() for x in l.split(",")]
        if len(f) >= 3 and f[0] == "10" and f[1] == "MTO":
            trade_date = dt.datetime.strptime(f[2], "%d%m%Y").date()
    if trade_date is None:
        raise FormatError(f"{name}: no '10,MTO,DDMMYYYY' record in the header")
    out = []
    for i, l in enumerate(lines, start=1):
        f = [x.strip() for x in l.split(",")]
        if f[0] != "20":
            continue
        where = f"{name} line {i}"
        if len(f) != 7:
            raise FormatError(f"{where}: record type 20 needs 7 fields, found {len(f)}")
        out.append({"symbol": f[2], "series": f[3],
                    "traded_qty_reported": integer(f[4], "qty", where),
                    "delivery_qty": integer(f[5], "deliverable", where)})
    if not out:
        raise FormatError(f"{name}: no type-20 records")
    return "nse_mto_delivery", trade_date, out
