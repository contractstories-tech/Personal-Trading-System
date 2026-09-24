"""The single point-in-time read primitive (Document 01 s14). No module writes its own PIT join.

A row is usable in a run iff usable_from <= the run's cutoff for the row's own domain.
Reading a row that is not yet usable raises - it never returns an empty result.
"""
from .timeutil import parse_ts


class LookAheadError(Exception):
    """A row not yet usable reached a consumer."""


class CanaryError(LookAheadError):
    """The canary rows show the read path is wrong: a sentinel leaked, or a required sentinel is absent."""


def usable(row, cutoffs):
    return parse_ts(row["usable_from"]) <= parse_ts(cutoffs[row["domain"]])


def guard(rows, cutoff):
    """Post-condition on every PIT read: nothing returned may be later than the cutoff."""
    c = parse_ts(cutoff)
    for r in rows:
        if parse_ts(r["usable_from"]) > c:
            raise LookAheadError(f"{r.get('isin')} {r.get('trade_date', '')} v{r.get('version_no', '')}: "
                                 f"usable_from {r['usable_from']} after cutoff {cutoff}")
    return rows


def read_checked(row, cutoff):
    guard([row], cutoff)
    return row


def asof(rows, isin, basis, cutoff):
    """Latest row of the requested basis usable at the cutoff. Basis filter BEFORE choosing the latest."""
    c = parse_ts(cutoff)
    cands = [r for r in rows if r["isin"] == isin and r["basis"] == basis and parse_ts(r["usable_from"]) <= c]
    return max(cands, key=lambda r: parse_ts(r["usable_from"])) if cands else None


def asof_domain(rows, isin, domain, cutoffs):
    cands = [r for r in rows if r["isin"] == isin and r["domain"] == domain and usable(r, cutoffs)]
    return max(cands, key=lambda r: parse_ts(r["usable_from"])) if cands else None


def period_panel_as_of(facts, isin, basis, cutoff):
    """{(fact, period_end): value}, each period at its latest version usable at the cutoff (Doc 02 s7; audit B5).
    A restatement of an old period replaces that period only; it never becomes 'the latest row'."""
    c = parse_ts(cutoff)
    best = {}
    for r in facts:
        if r["isin"] != isin or r["basis"] != basis or parse_ts(r["usable_from"]) > c:
            continue
        k = (r["fact"], r["period_end"])
        if k not in best or r["version"] > best[k]["version"]:
            best[k] = r
    return {k: r["value"] for k, r in best.items()}


def basis_for_window(facts, isin, cutoff, periods, fact="revenue"):
    """Basis of a multi-period feature, decided as of the cutoff: consolidated if consolidated figures exist for
    every period, standalone if for none, None (missing) if the window would mix bases."""
    cons = period_panel_as_of(facts, isin, "consolidated", cutoff)
    have = [(fact, p) in cons for p in periods]
    return "consolidated" if all(have) else ("standalone" if not any(have) else None)
