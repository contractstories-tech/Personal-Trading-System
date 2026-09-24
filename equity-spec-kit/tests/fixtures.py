"""Synthetic NSE-shaped files for M2 tests. Fake ISINs; layouts per eos/m2/parsers.py.
Real sample files replace these as the ground truth once Harsh uploads them."""
import datetime as dt
import os

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
            f.write(f"{d},{d},CM,NSE,STK,{1000 + n},{r['isin']},{r['sym']},{r['ser']},,,,,{r['sym']} LTD,{r['o']},"
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
