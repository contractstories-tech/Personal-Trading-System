"""Synthetic NSE-shaped files for M2 tests. Fake ISINs; layouts per eos/m2/parsers.py.
Real sample files replace these as the ground truth once Harsh uploads them."""
import datetime as dt
import os
import gzip

SEC = [  # symbol, series, isin
    ("AAAIND", "EQ", "INE000A01011"),
    ("BBBLTD", "EQ", "INE000B01012"),
    ("CCCTFT", "BE", "INE000C01013"),
]
UDIFF_HDR = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,"
             "StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,"
             "SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,"
             "Rsvd1,Rsvd2,Rsvd3,Rsvd4")


def bars(day, bump=None):
    """Deterministic OHLCV per security for a date. bump: {isin: new_close} to simulate a correction."""
    out = []
    for n, (sym, ser, isin) in enumerate(SEC):
        base = 100 + 10 * n + day.day
        o, h, l, c = base, base + 5, base - 2, base + 3
        if bump and isin in bump:
            c = bump[isin]
            h = max(h, c)
        vol = 10000 * (n + 1)
        out.append(dict(sym=sym, ser=ser, isin=isin, o=f"{o:.2f}", h=f"{h:.2f}", l=f"{l:.2f}", c=f"{c:.2f}",
                        last=f"{c:.2f}", pc=f"{base - 1:.2f}", vol=vol, val=f"{vol * (base + 1.5):.2f}", trades=100 + n))
    return out


def legacy(path, day, rows=None):
    rows = rows if rows is not None else bars(day)
    ts = day.strftime("%d-%b-%Y").upper()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n")
        for r in rows:
            f.write(f"{r['sym']},{r['ser']},{r['o']},{r['h']},{r['l']},{r['c']},{r['last']},{r['pc']},{r['vol']},"
                    f"{r['val']},{ts},{r['trades']},{r['isin']},\n")
    return path


def udiff(path, day, rows=None):
    rows = rows if rows is not None else bars(day)
    d = day.isoformat()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(UDIFF_HDR + "\n")
        for n, r in enumerate(rows):
            sid = r.get("sid", 1000 + n)
            f.write(f"{d},{d},CM,NSE,STK,{sid},{r['isin']},{r['sym']},{r['ser']},,,,,{r['sym']} LTD,{r['o']},"
                    f"{r['h']},{r['l']},{r['c']},{r['last']},{r['pc']},,{r['c']},0,0,{r['vol']},{r['val']},"
                    f"{r['trades']},F1,1,,,,,\n")
    return path


def mto(path, day, deliv=None, rows=None):
    rows = rows if rows is not None else bars(day)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("Security Wise Delivery Position - Compulsory Rolling Settlement\n")
        f.write(f"10,MTO,{day.strftime('%d%m%Y')},123456789,{len(rows):07d}\n")
        f.write(f"Trade Date <{day.strftime('%d-%b-%Y').upper()}>,Settlement Type <N>,Settlement No <2026001>,"
                f"Settlement Date <{day.strftime('%d-%b-%Y').upper()}>\n")
        f.write("Record Type,Sr No,Name of Security,Quantity Traded,Deliverable Quantity(gross across client level),"
                "% of Deliverable Quantity to Traded Quantity\n")
        for n, r in enumerate(rows, start=1):
            dq = (deliv or {}).get(r["isin"], r["vol"] // 2)
            tq = r["vol"]
            f.write(f"20,{n},{r['sym']},{r['ser']},{tq},{dq},{100 * dq / tq:.2f}\n")
    return path



def security_master(path, day, rows):
    """Write a current-shape MII security master gzip. rows use compact keys used by the r5.8 goldens."""
    from eos.m2.parsers import MII_SECURITY_COLS
    if not path.lower().endswith(".csv.gz"):
        raise ValueError("security-master fixture filename must end .csv.gz")
    records = []
    for r in rows:
        rec = {c: "" for c in MII_SECURITY_COLS}
        rec.update({
            "FinInstrmId": str(r["sid"]), "TckrSymb": r["sym"], "SctySrs": r.get("ser", "EQ"),
            "FinInstrmNm": r.get("name", r["sym"]), "ISIN": r["isin"], "NewBrdLotQty": "1",
            "SctyTpFlg": str(r.get("type", 0)), "SctyStsNrmlMkt": str(r.get("status", 6)),
            "ElgbltyNrmlMkt": str(r.get("elig", 1)), "DelFlg": r.get("del", "N"),
        })
        records.append(rec)
    import csv, io
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=MII_SECURITY_COLS, lineterminator="\n")
    w.writeheader(); w.writerows(records)
    with gzip.open(path, "wb") as f:
        f.write(buf.getvalue().encode("utf-8"))
    return path


def full_bhav_delivery(path, day, rows=None, missing_isins=None, pct_overrides=None):
    """Write the NSE security-wise full bhavcopy/deliverable CSV used as r5.9 validation evidence."""
    from eos.m2.parsers import FULL_BHAV_DELIVERY_COLS
    import csv
    rows = rows if rows is not None else bars(day)
    missing_isins = set(missing_isins or [])
    pct_overrides = pct_overrides or {}
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FULL_BHAV_DELIVERY_COLS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            tq = r["vol"]
            dq = tq // 2
            missing = r["isin"] in missing_isins
            pct = pct_overrides.get(r["isin"], f"{100 * dq / tq:.2f}")
            w.writerow({
                "SYMBOL": r["sym"], "SERIES": r["ser"], "DATE1": day.strftime("%d-%b-%Y").upper(),
                "PREV_CLOSE": r["pc"], "OPEN_PRICE": r["o"], "HIGH_PRICE": r["h"], "LOW_PRICE": r["l"],
                "LAST_PRICE": r["last"], "CLOSE_PRICE": r["c"], "AVG_PRICE": r["c"],
                "TTL_TRD_QNTY": tq, "TURNOVER_LACS": "1.00", "NO_OF_TRADES": r["trades"],
                "DELIV_QTY": "-" if missing else dq, "DELIV_PER": "-" if missing else pct,
            })
    return path
