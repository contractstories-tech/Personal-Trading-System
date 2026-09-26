"""NSE end-of-day and security-master parsers.

The parser layer is deliberately strict about source shape.  It recognises only the layouts the
platform has an explicit contract for and fails loudly on an unknown header.  r5.8 adds the current
NSE UDiFF source instrument identifier and the MII CM security master used to classify/reconcile
source observations without guessing from ticker/name strings.
"""
import csv
import datetime as dt
import decimal
import gzip
import io
import os
import re
import zipfile

D4 = decimal.Decimal("0.0001")


class FormatError(Exception):
    pass


LEGACY_COLS = ["SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE", "LAST", "PREVCLOSE",
               "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "TOTALTRADES", "ISIN"]
UDIFF_REQUIRED = ["TradDt", "BizDt", "Sgmt", "Src", "FinInstrmTp", "FinInstrmId", "ISIN", "TckrSymb", "SctySrs",
                  "OpnPric", "HghPric", "LwPric", "ClsPric", "LastPric", "PrvsClsgPric",
                  "TtlTradgVol", "TtlTrfVal", "TtlNbOfTxsExctd"]

# Current MII security file shape observed in NSE_CM_security_24092026.csv.gz and matched to NSE's
# MII master specification.  Exact fingerprinting is intentional: a silently shifted exchange schema
# is more dangerous than a loud parser failure.
MII_SECURITY_COLS = [
    "FinInstrmId","TckrSymb","SctySrs","FinInstrmNm","ISIN","NewBrdLotQty","ParVal","SctyTpFlg","BidIntrvl",
    "TrckgInd","CallAuctnInd","BookClsrStartDt","BookClsrEndDt","NoDlvryStartDt","NoDlvryEndDt","IssdCptl",
    "PrtdToTrad","PricRg","SctyStsNrmlMkt","ElgbltyNrmlMkt","SctyStsOddLotMkt","ElgbltyOddLotMkt",
    "SctyStsRETDBTMkt","ElgbltyClsgAuctnSsn","SctyStsAuctnMkt","ElgbltyAuctnMkt","SctyStsAddtlMkt1",
    "ElgbltyAddtlMkt1","SctyStsAddtlMkt2","ElgbltyAddtlMkt2","IsseDt","FrstPmtDt","MtrtyDt","MaxTradQtyPctg",
    "ListgDt","RmvlDt","RadmssnDt","RcrdDt","IndxPrtcptnInd","AllOrNn","MinFill","SttlmTp","Dvdd","Rghts",
    "Bns","Intrst","AGMtg","EGMtg","MktMakrSprd","MktMakrMinQty","AddtlInf","UpdDt","DelFlg","SpclExDt",
    "Xchg","UnqPdctIdr","SctyTp","TickSz","XchgExclsv","Sts","ExDvddDt","ExBnsDt","ExRghtsDt","FinInstrmTp",
    "InstrmTp","TradgPrtd","BuyBckInd","TradToTradInd","Indx","IndxInstrm","FinInstrmAttrbts","MinLot",
    "UndrlygInstrmAsstClss","UndrlygInstrm","UndrlygFinInstrmId","BlckDealAllwdFlg","InstrmNm","MktTpAndId",
    "UnitOfMeasr","PricQtQty","PricRgTp","MaxPric","MinPric","SttlmMtd","InitlMrgnTp","BuyInitlMrgnRate",
    "IssePric","MaxSnglTxnQty","MaxSnglTxnVal","AsstClss","PricNmrtr","Spcfctn","PricDnmtr","GnlNmrtr",
    "GnlDnmtr","LotNmrtr","LotDnmtr","DcmlstnPric","SrsSttlmTp","FreeFltCptl","SellInitlMrgnRate","RatgDtls",
    "FinInstrmClssfctn","SpclMrgnTp","BuySpclMrgnRat","SellSpclMrgnRat","PreOpnAllwdFlg","ClssfctnTp","MtchgCrit",
    "ValMtd","SLBMElgblty","Sgmt","Ccy","SttlmCcy","Rsvd02","Rsvd03","Rsvd04","Rsvd05","Rsvd06","Rsvd07"
]

KNOWN_SECURITY_STATUS = {1, 2, 3, 4, 5, 6}
KNOWN_INSTRUMENT_TYPES = {0, 1, 2, 3, 4}

FULL_BHAV_DELIVERY_COLS = [
    "SYMBOL", "SERIES", "DATE1", "PREV_CLOSE", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "LAST_PRICE",
    "CLOSE_PRICE", "AVG_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS", "NO_OF_TRADES", "DELIV_QTY", "DELIV_PER"
]


def read_bytes(path):
    """Plain file, gzip, or a zip holding exactly one member."""
    raw = open(path, "rb").read()
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        names = [n for n in z.namelist() if not n.endswith("/")]
        if len(names) != 1:
            raise FormatError(f"{path}: zip must hold exactly one file, found {names}")
        return z.read(names[0])
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError as e:
            raise FormatError(f"{path}: invalid gzip: {e}") from e
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


def optional_integer(s, field, where):
    s = s.strip()
    return None if s == "" else integer(s, field, where)


def optional_money(s, field, where, missing=("", "-", "NA", "N/A")):
    s = s.strip()
    return None if s.upper() in {x.upper() for x in missing} else money(s, field, where)


def _rows(text):
    return list(csv.reader(io.StringIO(text)))


def parse_bhavcopy(data, name="<file>"):
    """Returns (format, trade_date, rows).

    UDiFF rows preserve FinInstrmId as source_instrument_id.  Legacy rows have no exchange token and
    therefore store source_instrument_id=None; their source identity falls back to ISIN+series.
    """
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
        source_id_of = lambda r: None  # noqa: E731
    elif all(c in header for c in UDIFF_REQUIRED):
        fmt = "nse_bhavcopy_udiff"
        col = {h: i for i, h in enumerate(header)}
        get = lambda r, k: r[col[k]]  # noqa: E731
        m = dict(symbol="TckrSymb", series="SctySrs", open="OpnPric", high="HghPric", low="LwPric", close="ClsPric",
                 prev_close="PrvsClsgPric", volume="TtlTradgVol", traded_value="TtlTrfVal",
                 num_trades="TtlNbOfTxsExctd", isin="ISIN")
        date_of = lambda r: dt.date.fromisoformat(get(r, "TradDt").strip())  # noqa: E731
        source_id_of = lambda r: get(r, "FinInstrmId").strip()  # noqa: E731
    else:
        raise FormatError(f"{name}: unrecognised bhavcopy header {header[:8]}...")

    out, dates = [], set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        where = f"{name} line {i}"
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        if fmt == "nse_bhavcopy_udiff" and get(r, "Sgmt").strip() != "CM":
            raise FormatError(f"{where}: segment {get(r, 'Sgmt')!r} in a CM bhavcopy")
        d = date_of(r)
        dates.add(d)
        source_instrument_id = source_id_of(r)
        if fmt == "nse_bhavcopy_udiff" and not source_instrument_id:
            raise FormatError(f"{where}: blank FinInstrmId")
        out.append({
            "source_instrument_id": source_instrument_id,
            "isin": get(r, m["isin"]).strip(), "symbol": get(r, m["symbol"]).strip(),
            "series": get(r, m["series"]).strip(),
            **{k: money(get(r, m[k]), k, where) for k in ("open", "high", "low", "close", "prev_close", "traded_value")},
            **{k: integer(get(r, m[k]), k, where) for k in ("volume", "num_trades")},
        })
    if len(dates) != 1:
        raise FormatError(f"{name}: expected one trade date, found {sorted(dates)}")
    return fmt, dates.pop(), out


def _master_date_from_name(name):
    base = os.path.basename(name)
    m = re.search(r"NSE_CM_security_(\d{2})(\d{2})(\d{4})\.csv(?:\.gz)?$", base, re.I)
    if not m:
        raise FormatError(f"{name}: security-master filename must be NSE_CM_security_ddmmyyyy.csv[.gz]")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def parse_security_master(data, name="<file>"):
    """Parse the current NSE CM MII security master.

    Returns (format, master_file_date, rows).  Classification is deliberately conservative: instrument
    class is derived from exchange fields; market eligibility is only asserted when status/eligibility/delete
    codes are known.  Unknown status codes are retained but make market_eligible=None (fail closed).
    """
    text = data.decode("utf-8-sig")
    rows = _rows(text)
    if not rows:
        raise FormatError(f"{name}: empty file")
    header = [h.strip() for h in rows[0]]
    while header and header[-1] == "":
        header.pop()
    if header != MII_SECURITY_COLS:
        raise FormatError(f"{name}: unrecognised MII security-master header {header[:10]}... ({len(header)} cols)")
    master_date = _master_date_from_name(name)
    col = {h: i for i, h in enumerate(header)}
    out = []
    seen = set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        where = f"{name} line {i}"
        get = lambda k: r[col[k]].strip()  # noqa: E731
        sid = get("FinInstrmId")
        if not sid:
            raise FormatError(f"{where}: blank FinInstrmId")
        if sid in seen:
            raise FormatError(f"{where}: duplicate FinInstrmId {sid}")
        seen.add(sid)
        instrument_type = optional_integer(get("SctyTpFlg"), "SctyTpFlg", where)
        status = optional_integer(get("SctyStsNrmlMkt"), "SctyStsNrmlMkt", where)
        eligibility = optional_integer(get("ElgbltyNrmlMkt"), "ElgbltyNrmlMkt", where)
        price_range_text = get("PricRg") or None
        price_range_type = get("PricRgTp") or None
        max_price = optional_money(get("MaxPric"), "MaxPric", where)
        min_price = optional_money(get("MinPric"), "MinPric", where)
        tick_size = optional_money(get("TickSz"), "TickSz", where)
        del_flag = get("DelFlg").upper()
        status_known = status in KNOWN_SECURITY_STATUS
        inst_known = instrument_type in KNOWN_INSTRUMENT_TYPES
        eligibility_known = eligibility in {0, 1}
        delete_known = del_flag in {"N", "Y"}
        sym, isin, series = get("TckrSymb"), get("ISIN"), get("SctySrs")
        is_dummy = sym.upper().endswith("NSETEST") or isin.upper().startswith("DUMMY")
        if inst_known and series == "EQ" and instrument_type == 0 and not is_dummy:
            security_class = "company_equity"
        elif inst_known:
            security_class = "other"
        else:
            security_class = "unresolved"
        if not (status_known and eligibility_known and delete_known):
            market_eligible = None
        else:
            market_eligible = bool(eligibility == 1 and del_flag == "N" and not is_dummy)
        out.append({
            "source_instrument_id": sid,
            "symbol": sym,
            "series": series,
            "name": get("FinInstrmNm"),
            "isin": isin,
            "instrument_type": instrument_type,
            "normal_market_status": status,
            "normal_market_eligibility": eligibility,
            "price_range_text": price_range_text,
            "price_range_type": price_range_type,
            "max_price": max_price,
            "min_price": min_price,
            "tick_size": tick_size,
            "delete_flag": del_flag,
            "is_dummy": is_dummy,
            "status_code_known": status_known,
            "security_class": security_class,
            "market_eligible": market_eligible,
        })
    if not out:
        raise FormatError(f"{name}: no security rows")
    return "nse_cm_mii_security", master_date, out


def parse_mto(data, name="<file>"):
    """Parse NSE security-wise delivery (MTO) DAT.

    Returns (format, trade_date, rows). The type-10 header's declared row count is enforced and the
    exchange-reported delivery percentage is preserved for an independent arithmetic cross-check at ingest.
    """
    text = data.decode("utf-8-sig")
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines or "Security Wise Delivery Position" not in lines[0]:
        raise FormatError(f"{name}: not an MTO delivery file (first line {lines[0][:60] if lines else ''!r})")
    trade_date = None
    declared_count = None
    for l in lines[1:5]:
        f = [x.strip() for x in l.split(",")]
        if len(f) >= 5 and f[0] == "10" and f[1] == "MTO":
            trade_date = dt.datetime.strptime(f[2], "%d%m%Y").date()
            declared_count = integer(f[4], "declared row count", f"{name} type-10 header")
            break
    if trade_date is None:
        raise FormatError(f"{name}: no '10,MTO,DDMMYYYY' record in the header")
    # If the archive filename itself carries a date, it must agree with the type-10 record.
    m = re.search(r"MTO[_-]?(\d{2})(\d{2})(\d{4})\.DAT$", os.path.basename(name), re.I)
    if m:
        named = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if named != trade_date:
            raise FormatError(f"{name}: filename date {named} disagrees with header date {trade_date}")
    out = []
    for i, l in enumerate(lines, start=1):
        f = [x.strip() for x in l.split(",")]
        if not f or f[0] != "20":
            continue
        where = f"{name} line {i}"
        if len(f) != 7:
            raise FormatError(f"{where}: record type 20 needs 7 fields, found {len(f)}")
        traded = integer(f[4], "qty", where)
        delivered = integer(f[5], "deliverable", where)
        pct = optional_money(f[6], "delivery percentage", where)
        out.append({"symbol": f[2], "series": f[3], "traded_qty_reported": traded,
                    "delivery_qty": delivered, "delivery_pct_reported": pct})
    if not out:
        raise FormatError(f"{name}: no type-20 records")
    if declared_count is not None and declared_count != len(out):
        raise FormatError(f"{name}: type-10 header declares {declared_count} detail rows, found {len(out)}")
    return "nse_mto_delivery", trade_date, out


def parse_full_bhav_delivery(data, name="<file>"):
    """Parse NSE `sec_bhavdata_full_DDMMYYYY.csv` as an independent delivery cross-check source.

    This file has no ISIN/FinInstrmId, so ingestion must reconcile symbol+series to the day's bhavcopy.
    A dash in DELIV_QTY/DELIV_PER is preserved as unavailable evidence rather than converted to zero.
    """
    text = data.decode("utf-8-sig")
    rows = _rows(text)
    if not rows:
        raise FormatError(f"{name}: empty file")
    header = [h.strip() for h in rows[0]]
    while header and header[-1] == "":
        header.pop()
    if header != FULL_BHAV_DELIVERY_COLS:
        raise FormatError(f"{name}: unrecognised full-bhav delivery header {header[:8]}... ({len(header)} cols)")
    col = {h: i for i, h in enumerate(header)}
    out, dates = [], set()
    for i, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) < len(header):
            r = r + [""] * (len(header) - len(r))
        where = f"{name} line {i}"
        get = lambda k: r[col[k]].strip()  # noqa: E731
        try:
            d = dt.datetime.strptime(get("DATE1").title(), "%d-%b-%Y").date()
        except ValueError as e:
            raise FormatError(f"{where}: DATE1={get('DATE1')!r} is not DD-Mon-YYYY") from e
        dates.add(d)
        tq = integer(get("TTL_TRD_QNTY"), "TTL_TRD_QNTY", where)
        dq = optional_integer(get("DELIV_QTY") if get("DELIV_QTY") != "-" else "", "DELIV_QTY", where)
        dp = optional_money(get("DELIV_PER"), "DELIV_PER", where)
        if (dq is None) != (dp is None):
            raise FormatError(f"{where}: DELIV_QTY and DELIV_PER must both be present or both be '-' ")
        out.append({"symbol": get("SYMBOL"), "series": get("SERIES"), "traded_qty_reported": tq,
                    "delivery_qty": dq, "delivery_pct_reported": dp, "delivery_available": dq is not None})
    if len(dates) != 1:
        raise FormatError(f"{name}: expected one trade date, found {sorted(dates)}")
    if not out:
        raise FormatError(f"{name}: no data rows")
    return "nse_sec_bhavdata_full_delivery", dates.pop(), out

