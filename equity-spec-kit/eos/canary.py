"""Look-ahead canary (Document 01 s14; Document 02 s17: 'the canary hard-fails').

Every partition of a point-in-time table carries sentinel rows, written with the first real part.
Each sentinel is built to be selected by one plausible wrong read and excluded by the right one:

  INCANARY0001  every timestamp early EXCEPT system_available_at        -> caught if a read filters on
                                                                           received_at, source_published_at or effective_from
  INCANARY0002  system_available_at early, effective_from late          -> caught if a read filters on system_available_at
  INCANARY0003  v1 usable at 22:30 IST on the trade date, v2 never usable
                - v2 returned                                            -> 'highest version' ignoring the cutoff
                - v1 absent                                              -> read used the wrong domain's cutoff (20:00),
                                                                           or returned nothing at all

A leaked sentinel or an absent required sentinel raises CanaryError. An empty result is never a pass.
"""
import datetime as dt
from .pit import CanaryError
from .timeutil import FAR_FUTURE, at_ist

PREFIX = "INCANARY"
REQUIRED = ("INCANARY0003", 1)


def is_canary(isin):
    return isin.startswith(PREFIX)


def sentinels(table, trade_date, domain, base):
    """base: a dict of neutral column values for the table."""
    early = at_ist(trade_date, "16:00")
    ok = at_ist(trade_date, "22:30")

    def row(isin, v, pub, rec, eff, sysav, usable, sup=None):
        return {**base, "isin": isin, "trade_date": trade_date, "version_no": v, "symbol": isin, "series": "ZZ",
                "source_id": "canary", "source_format": "canary", "file_sha256": "canary", "domain": domain,
                "source_published_at": pub, "received_at": rec, "effective_from": eff,
                "system_available_at": sysav, "usable_from": usable, "availability_inferred": False,
                "supersedes_version": sup}
    return [
        row("INCANARY0001", 1, early, early, early, FAR_FUTURE, FAR_FUTURE),
        row("INCANARY0002", 1, early, early, FAR_FUTURE, early, FAR_FUTURE),
        row("INCANARY0003", 1, ok, ok, ok, ok, ok),
        row("INCANARY0003", 2, ok, ok, FAR_FUTURE, FAR_FUTURE, FAR_FUTURE, sup=1),
    ]


def check(chosen, partitions_read, cutoff):
    """chosen: rows a read selected (sentinels included). partitions_read: trade dates that held rows."""
    got = {(r["isin"], r["version_no"], r["trade_date"]) for r in chosen if is_canary(r["isin"])}
    for isin, v, d in got:
        if (isin, v) != REQUIRED:
            raise CanaryError(f"canary {isin} v{v} ({d}) leaked into a read at cutoff {cutoff}: the read path "
                              f"is selecting rows that are not usable yet")
    for d in partitions_read:
        if (REQUIRED[0], REQUIRED[1], d) not in got:
            raise CanaryError(f"canary {REQUIRED[0]} v1 ({d}) missing from a read at cutoff {cutoff}: the read "
                              f"path used the wrong cutoff or dropped usable rows")
