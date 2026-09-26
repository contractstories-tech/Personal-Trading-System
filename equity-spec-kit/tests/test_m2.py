#!/usr/bin/env python3
"""Stage 0 slice 1 - M2 price ingestion, the PIT primitive, the canary and the warehouse.

    python3 tests/test_m2.py                    exit 0 = all pass (Parquet round-trip reported as NOT RUN
                                                if pyarrow is absent)
    python3 tests/test_m2.py --require-parquet  also fails if the Parquet codec could not run
                                                (use this on the machine that holds the warehouse)

Every test runs once per available codec (r5.5, audit B4): JSONL always, Parquet whenever pyarrow is installed.
r5.4 exercised Parquet in one test only, which is how a store invariant held on JSONL and not on Parquet.
And once per platform path (r5.6): on Windows the real Windows primitives; on a POSIX host both the POSIX
primitives and the Windows code paths against emulated kernel32 / msvcrt (eos/fsio.py). The emulation catches a
Windows-only call on the wrong path (r5.5's directory fsync); it does not replace running this suite on Windows.
"""
import copy
import datetime as dt
import decimal
import json
import os
import shutil
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, KIT)
sys.path.insert(0, HERE)
import yaml  # noqa: E402
import fixtures as F  # noqa: E402
from eos import canary, fsio, pit, source_policy, store  # noqa: E402
from eos.m2 import ingest, parsers, resolve  # noqa: E402
from eos.timeutil import IST, UTC, at_ist, ist, parse_ts, run_cutoffs  # noqa: E402
import threading  # noqa: E402

D1, D2, D3 = dt.date(2026, 9, 16), dt.date(2026, 9, 17), dt.date(2026, 9, 18)
A, B, C = (s[2] for s in F.SEC)
TESTS, NOT_RUN = [], []
CODEC = "jsonl"          # set per pass by the runner below


def case(fn):
    """Registers an M2 case (named 'case', not 'test', so pytest does not collect the decorator itself)."""
    TESTS.append(fn)
    return fn


class Env:
    def __init__(self, codec=None):
        self.dir = tempfile.mkdtemp()
        self.wh = store.Warehouse(os.path.join(self.dir, "wh"), codec or CODEC)

    def f(self, name):
        return os.path.join(self.dir, name)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        rmtree(self.dir)


def rmtree(path):
    """Landed raw files are read-only; Windows refuses to delete a read-only file until it is made writable."""
    def retry(func, p, _exc):
        os.chmod(p, 0o700)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=retry)


def raises(exc, fn, *a, **k):
    try:
        fn(*a, **k)
    except exc as e:
        return e
    raise AssertionError(f"expected {exc.__name__}")


def recv(day, hhmm="08:00"):
    """A backfilled file is received after its trade date (r5.5: same-day backfill is refused as a live file)."""
    return at_ist(day + dt.timedelta(days=1), hhmm)


def load_days(e, days, fmt=F.legacy, deliver=True):
    for d in days:
        ingest.ingest_bhavcopy(e.wh, fmt(e.f(f"b{d}.csv"), d), recv(d))
        if deliver:
            ingest.ingest_delivery(e.wh, F.mto(e.f(f"m{d}.DAT"), d), recv(d))


# ------------------------------------------------------------------ golden cases through the production primitive
def _g(rows):
    """Golden fixtures carry naive IST wall-clock times; convert explicitly (the primitive refuses naive)."""
    return [dict(r, usable_from=ist(r["usable_from"])) for r in rows]


@case
def golden_pit_cases_pass_on_production_primitive():
    G = yaml.safe_load(open(os.path.join(KIT, "golden", "golden_cases.yaml"), encoding="utf-8"))
    rows = _g(G["pit"]["rows"])
    for c in G["pit"]["cases"]:
        r = pit.asof(rows, "INE0TEST", c["basis"], ist(c["cutoff"]))
        assert (r["value"] if r else None) == c["expect_value"], c["id"]
    cn = G["pit"]["canary"]
    raises(pit.LookAheadError, pit.read_checked, rows[cn["row_index"]], ist(cn["cutoff"]))
    cu = G["cutoffs"]
    cuts = {k: ist(v) for k, v in cu["cutoffs"].items()}
    for c in cu["cases"]:
        r = pit.asof_domain(_g(cu["rows"]), c.get("isin", "INE0TEST"), c["domain"], cuts)
        assert (r["value"] if r else None) == c["expect_value"], c["id"]
    bw = G["basis_window"]
    for c in bw["cases"]:
        assert pit.basis_for_window(_g(bw["facts"]), "INE0B", ist(c["cutoff"]), c["periods"]) == c["expect"], c["id"]
    rs = G["restatement"]
    for c in rs["cases"]:
        pan = pit.period_panel_as_of(_g(rs["facts"]), "INE0R", "consolidated", ist(c["cutoff"]))
        assert pan[("revenue", dt.date(2019, 3, 31))] == c["expect"]["fy2019"], c["id"]
        assert pan[("revenue", dt.date(2020, 3, 31))] == c["expect"]["fy2020"], c["id"]
    for c in G["pit"]["cases"]:     # includes G19e: usable exactly at the cutoff is used
        r = pit.asof(rows, "INE0TEST", c["basis"], ist(c["cutoff"]))
        assert (r["value"] if r else None) == c["expect_value"], c["id"]
    cb = G["pit"]["canary_boundary"]
    pit.read_checked(rows[cb["row_index"]], ist(cb["cutoff"]))          # G20b: no raise at equality


@case
def naive_timestamp_refused_by_pit_layer():
    """H8: a missing offset must never be silently read as IST (or anything else)."""
    raises(ValueError, parse_ts, "2026-09-18T20:00")
    raises(ValueError, pit.read_checked, {"usable_from": "2026-09-18T18:00"}, "2026-09-18T20:00+05:30")
    assert parse_ts("2026-09-18T20:00+05:30") == dt.datetime(2026, 9, 18, 14, 30, tzinfo=UTC)
    raises(ValueError, ist, "2026-09-18T20:00+05:30")


@case
def cutoffs_come_from_registry_in_ist():
    c = run_cutoffs(D3)
    assert c["exchange_eod"] == dt.datetime(2026, 9, 18, 23, 0, tzinfo=IST)
    assert c["disclosure"] == dt.datetime(2026, 9, 18, 20, 0, tzinfo=IST)
    assert c["exchange_eod"].tzinfo == UTC


# ------------------------------------------------------------------ parsers
@case
def legacy_and_udiff_parse_to_identical_rows():
    with Env() as e:
        f1, d1, r1 = parsers.parse_bhavcopy(parsers.read_bytes(F.legacy(e.f("l.csv"), D2)))
        f2, d2, r2 = parsers.parse_bhavcopy(parsers.read_bytes(F.udiff(e.f("u.csv"), D2)))
        assert (f1, f2) == ("nse_bhavcopy_legacy", "nse_bhavcopy_udiff") and d1 == d2 == D2
        assert len(r1) == len(r2) == 3
        assert all(r["source_instrument_id"] is None for r in r1)
        assert [r["source_instrument_id"] for r in r2] == ["1000", "1001", "1002"]
        common = lambda r: {k: v for k, v in r.items() if k != "source_instrument_id"}
        assert [common(r) for r in r1] == [common(r) for r in r2]
        assert r1[0]["traded_value"] == decimal.Decimal("1185000.0000")  # from the file, never close x volume


@case
def zipped_file_is_read():
    import zipfile
    with Env() as e:
        p = F.legacy(e.f("l.csv"), D1)
        with zipfile.ZipFile(e.f("l.zip"), "w") as z:
            z.write(p, "cm16SEP2026bhav.csv")
        assert parsers.parse_bhavcopy(parsers.read_bytes(e.f("l.zip")))[1] == D1


@case
def unknown_header_fails_loudly():
    with Env() as e:
        p = e.f("x.csv")
        open(p, "w", encoding="utf-8", newline="\n").write("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,ISIN\nA,EQ,1,1,1,1,INE000A01011\n")
        raises(parsers.FormatError, parsers.parse_bhavcopy, parsers.read_bytes(p))
        open(p, "w", encoding="utf-8", newline="\n").write("hello\n")
        raises(parsers.FormatError, parsers.parse_mto, parsers.read_bytes(p))


@case
def excess_precision_and_non_numbers_rejected():
    with Env() as e:
        rows = F.bars(D1)
        rows[0]["c"] = "104.12345"
        raises(parsers.FormatError, parsers.parse_bhavcopy, parsers.read_bytes(F.legacy(e.f("a.csv"), D1, rows)))
        rows = F.bars(D1)
        rows[1]["vol"] = "12.5"
        raises(parsers.FormatError, parsers.parse_bhavcopy, parsers.read_bytes(F.legacy(e.f("b.csv"), D1, rows)))


@case
def mixed_dates_in_one_file_rejected():
    with Env() as e:
        p = F.legacy(e.f("a.csv"), D1)
        txt = open(p, encoding="utf-8").read().replace("16-SEP-2026", "17-SEP-2026", 1)
        open(p, "w", encoding="utf-8", newline="\n").write(txt)
        raises(parsers.FormatError, parsers.parse_bhavcopy, parsers.read_bytes(p))


# ------------------------------------------------------------------ availability
@case
def backfill_first_version_is_inferred_at_2230_and_used_same_day():
    with Env() as e:
        load_days(e, [D1])
        r = [x for x in e.wh.read("price_observation") if x["isin"] == A][0]
        assert r["availability_inferred"] and r["usable_from"] == at_ist(D1, "22:30")
        assert r["received_at"] == recv(D1)
        got = resolve.history_known_as_of(e.wh, D1)
        assert {x["isin"] for x in got} == {A, B, C}


@case
def live_row_processed_after_cutoff_is_not_used_that_day():
    with Env() as e:
        p = F.legacy(e.f("a.csv"), D1)
        ingest.ingest_bhavcopy(e.wh, p, received_at=at_ist(D1, "22:55"), mode="live", now=at_ist(D1, "23:10"))
        r = [x for x in e.wh.read("price_observation") if x["isin"] == A][0]
        assert r["usable_from"] == at_ist(D1, "23:10") and not r["availability_inferred"]
        assert resolve.history_known_as_of(e.wh, D1) == []
        assert len(resolve.history_known_as_of(e.wh, D2)) == 3


@case
def usable_from_is_never_before_publication():
    with Env() as e:
        load_days(e, [D1])
        for r in e.wh.read("price_observation") + e.wh.read("delivery_observation"):
            assert r["usable_from"] >= r["source_published_at"], r["isin"]


@case
def policy_refuses_inferred_time_at_or_after_cutoff():
    with Env() as e:
        for sid in ("nse_cm_bhavcopy", "nse_cm_delivery"):
            p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml"), encoding="utf-8"))
            p["sources"][sid]["availability"].update(inferred_published_time_ist="22:45", policy_lag_minutes=15)
            path = e.f(f"sp-{sid}.yaml")
            yaml.safe_dump(p, open(path, "w", encoding="utf-8", newline="\n"))
            raises(source_policy.PolicyError, source_policy.load, path)
        source_policy.load()  # the shipped policy loads


@case
def availability_is_source_specific():
    """B9: the delivery file's inferred time is its own, not the bhavcopy's."""
    with Env() as e:
        p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml"), encoding="utf-8"))
        p["sources"]["nse_cm_delivery"]["availability"]["inferred_published_time_ist"] = "22:50"
        path = e.f("sp.yaml")
        yaml.safe_dump(p, open(path, "w", encoding="utf-8", newline="\n"))
        pol = source_policy.load(path)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1), policy=pol)
        ingest.ingest_delivery(e.wh, F.mto(e.f("m.DAT"), D1), recv(D1), policy=pol)
        pr = [r for r in e.wh.read("price_observation") if r["isin"] == A][0]
        dr = [r for r in e.wh.read("delivery_observation") if r["isin"] == A][0]
        assert pr["usable_from"] == at_ist(D1, "22:30") and dr["usable_from"] == at_ist(D1, "22:50")
        prof = resolve.availability_profile(resolve.history_known_as_of(e.wh, D1))
        assert prof["price_inferred_share"] == 1.0 and prof["delivery_inferred_share"] == 1.0


# ------------------------------------------------------------------ versioning and corrections
@case
def same_file_twice_is_a_noop():
    with Env() as e:
        p = F.legacy(e.f("a.csv"), D1)
        ingest.ingest_bhavcopy(e.wh, p, recv(D1))
        n = len(e.wh.read("price_observation"))
        assert ingest.ingest_bhavcopy(e.wh, p, recv(D2))["noop"]
        assert len(e.wh.read("price_observation")) == n


@case
def cross_format_same_content_is_one_observation():
    """r5.10 restores r5.3's rule: the same content in the other format writes no new version. r5.8-r5.9 gave the
    UDiFF row a new identity (FinInstrmId), wrote three 'new' rows and tombstoned the legacy ones."""
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("b.csv"), D1), recv(D2))
        assert res["rows_new"] == 0 and res["rows_changed"] == 0 and res["rows_unchanged"] == 3
        assert e.wh.partitions("observation_tombstone") == []
        assert len([r for r in resolve.history_known_as_of(e.wh, D3) if r["trade_date"] == D1]) == 3


@case
def correction_in_the_other_format_is_never_back_dated():
    """r5.10 (review of r5.8/r5.9): a correction delivered as UDiFF after a legacy original is version 2, available
    when received. r5.8-r5.9 stored it as a 'first version' inferred usable at 22:30 on the trade date, so a decision
    on the trade date saw a price received days later and the canonical read failed with two candidates."""
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))
        late = at_ist(D3 + dt.timedelta(days=4), "10:00")
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("b.csv"), D1, F.bars(D1, bump={A: 150})), late)
        assert res["rows_changed"] == 1 and res["rows_new"] == 0
        a = sorted((r["version_no"], r["availability_inferred"], r["usable_from"], r.get("source_instrument_id"))
                   for r in e.wh.read("price_observation", [D1.isoformat()]) if r["isin"] == A)
        assert [(v, inf) for v, inf, _, _ in a] == [(1, True), (2, False)] and a[1][2] == late and a[1][3] is not None
        close_on = lambda day: [x["close"] for x in resolve.history_known_as_of(e.wh, day)  # noqa: E731
                                if x["isin"] == A and x["trade_date"] == D1]
        assert close_on(D1) == [decimal.Decimal("119")]                  # the trade-date decision saw only the original
        assert close_on(late.astimezone(IST).date()) == [decimal.Decimal("150")]


@case
def same_isin_and_series_under_two_fininstrmids_is_a_duplicate():
    """One observation per (ISIN, series) per session: two FinInstrmIds claiming it are ambiguous and quarantined."""
    with Env() as e:
        rows = F.bars(D1)
        bad = [dict(rows[0], sid=7000), dict(rows[0], sid=7001)] + [dict(r, sid=7100 + n) for n, r in enumerate(rows[1:])]
        raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh, F.udiff(e.f("u.csv"), D1, bad), recv(D1))
        assert e.wh.partitions("price_observation") == []


@case
def correction_is_a_new_version_resolved_as_of():
    """Stage 0 acceptance: 'a price correction is resolved as-of correctly' (synthetic)."""
    with Env() as e:
        load_days(e, [D1, D2, D3], deliver=False)
        corr = F.legacy(e.f("corr.csv"), D1, F.bars(D1, bump={A: 120}))
        res = ingest.ingest_bhavcopy(e.wh, corr, received_at=at_ist(D2, "10:00"))
        assert res["rows_changed"] == 1 and res["rows_unchanged"] == 2
        v = sorted((x["version_no"], x["supersedes_version"], x["availability_inferred"])
                   for x in e.wh.read("price_observation", [D1.isoformat()]) if x["isin"] == A)
        assert v == [(1, None, True), (2, 1, False)]  # the correction is not back-dated
        close_on = lambda asof: [x["close"] for x in resolve.history_known_as_of(e.wh, asof)  # noqa: E731
                                 if x["isin"] == A and x["trade_date"] == D1][0]
        assert close_on(D1) == decimal.Decimal("119")   # run for D1 saw the original print
        assert close_on(D2) == decimal.Decimal("120")   # correction received 10:00 on D2
        assert close_on(D3) == decimal.Decimal("120")


def _policy(**per_source):
    pol = copy.deepcopy(source_policy.load())
    for sid, fields in per_source.items():
        pol["sources"][sid].update(fields)
    return pol


@case
def reissue_missing_a_security_keeps_prior_while_reissue_semantics_are_unverified():
    """r5.10: no real NSE reissue has yet shown that a reissue is a complete snapshot, so an omission is logged and
    the prior version kept (r5.8-r5.9 tombstoned it)."""
    with Env() as e:
        load_days(e, [D1], deliver=False)
        rows = F.bars(D1)
        rows[0]["c"] = "118.00"
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("r.csv"), D1, rows[:2]), recv(D2))
        assert [(c["isin"], c["kind"]) for c in res["conflicts"]] == [(C, "absent_in_reissue")]
        assert "unverified" in res["conflicts"][0]["detail"]
        assert e.wh.partitions("observation_tombstone") == []
        assert C in {x["isin"] for x in resolve.history_known_as_of(e.wh, D3)}


@case
def reissue_missing_a_security_creates_point_in_time_tombstone_when_complete():
    """With reissue_semantics: complete_snapshot, a same-format omission is a point-in-time withdrawal."""
    with Env() as e:
        pol = _policy(nse_cm_bhavcopy={"reissue_semantics": "complete_snapshot"})
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1), policy=pol)
        rows = F.bars(D1)
        rows[0]["c"] = "118.00"
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("r.csv"), D1, rows[:2]), recv(D2), policy=pol)
        assert [(c["isin"], c["kind"]) for c in res["conflicts"]] == [(C, "withdrawn_in_reissue")]
        assert C in {x["isin"] for x in resolve.history_known_as_of(e.wh, D1)}  # before withdrawal was known
        assert C not in {x["isin"] for x in resolve.history_known_as_of(e.wh, D3)}
        tomb = e.wh.read("observation_tombstone", [D1.isoformat()])
        assert len(tomb) == 1 and tomb[0]["isin"] == C and tomb[0]["reason"] == "absent_from_complete_reissue"


@case
def delivery_never_maps_onto_a_withdrawn_price_row():
    """r5.10: delivery rows join only ACTIVE price observations; r5.9 also joined tombstoned ones."""
    with Env() as e:
        pol = _policy(nse_cm_bhavcopy={"reissue_semantics": "complete_snapshot"}, nse_cm_delivery={})
        pol["quality"]["max_quarantine_share"] = 0.4
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1), policy=pol)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("r.csv"), D1, F.bars(D1)[:2]), recv(D1, "09:00"), policy=pol)
        res = ingest.ingest_delivery(e.wh, F.mto(e.f("MTO_16092026.DAT"), D1), recv(D1, "10:00"), policy=pol)
        assert [(q["symbol"], q["reason"]) for q in res["quarantined"]] == [(F.SEC[2][0], "unmapped_symbol")]
        assert C not in {r["isin"] for r in e.wh.read("delivery_observation") if not canary.is_canary(r["isin"])}


@case
def an_omission_in_the_other_format_is_never_a_withdrawal():
    """Even with complete_snapshot semantics, a row absent from a file of the OTHER format is kept: the two formats'
    row sets differ, so absence there proves nothing."""
    with Env() as e:
        pol = _policy(nse_cm_bhavcopy={"reissue_semantics": "complete_snapshot"})
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1), policy=pol)
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("u.csv"), D1, F.bars(D1)[:2]), recv(D2), policy=pol)
        assert [(c["isin"], c["kind"]) for c in res["conflicts"]] == [(C, "absent_in_reissue")]
        assert "nse_bhavcopy_legacy" in res["conflicts"][0]["detail"]
        assert e.wh.partitions("observation_tombstone") == []


# ------------------------------------------------------------------ quality checks: parsed warehouse state is unchanged on reject
def _unchanged(e, fn):
    """A rejected source may add its durable raw receipt / parse evidence, but no parsed domain table may change."""
    evidence = {"raw_file", "raw_parse_event"}
    before = {t: e.wh.read(t) for t in store.TABLES if t not in evidence}
    fn()
    after = {t: e.wh.read(t) for t in store.TABLES if t not in evidence}
    assert after == before, "a rejected file changed parsed warehouse data"


@case
def ohlc_violation_rejects_whole_file():
    with Env() as e:
        load_days(e, [D1], deliver=False)
        rows = F.bars(D2)
        rows[1]["h"] = "1.00"
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("x.csv"), D2, rows), recv(D2)))


@case
def duplicate_isin_and_canary_prefix_rejected():
    with Env() as e:
        rows = F.bars(D1)
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("d.csv"), D1, rows + [rows[0]]), recv(D1)))
        rows = F.bars(D1)
        rows[0]["isin"] = "INCANARY0003"
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("c.csv"), D1, rows), recv(D1)))


@case
def row_count_collapse_fires_kill_switch_small_drop_warns():
    many = [dict(r, isin=f"INE{n:03d}X01010", sym=f"S{n}") for n in range(20) for r in F.bars(D1)[:1]]
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1, many), recv(D1))
        few = [dict(r, **{"o": "118.00", "h": "123.00", "l": "116.00", "c": "121.00"}) for r in many[:17]]
        _unchanged(e, lambda: raises(ingest.KillSwitch, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("b.csv"), D2, few), recv(D2)))   # 85%
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c.csv"), D2, many[:19]), recv(D2))  # 95% - warn only
        assert not res["warnings"]
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("d.csv"), D3, many[:18]), recv(D3))  # 94.7%
        assert res["warnings"]


@case
def delivery_needs_bhavcopy_and_valid_quantities():
    with Env() as e:
        raises(ingest.QualityError, ingest.ingest_delivery, e.wh, F.mto(e.f("m.DAT"), D1), recv(D1))
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1))
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_delivery, e.wh,
                                     F.mto(e.f("m2.DAT"), D1, deliv={A: 999999}), recv(D1)))
        rows = F.bars(D1)
        rows[0]["sym"] = "UNKNOWN"
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_delivery, e.wh,
                                     F.mto(e.f("m3.DAT"), D1, rows=rows), recv(D1)))


@case
def delivery_volume_mismatch_is_logged_not_overwritten():
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1))
        rows = F.bars(D1)
        rows[1]["vol"] = rows[1]["vol"] + 500  # 2.5% off
        res = ingest.ingest_delivery(e.wh, F.mto(e.f("m.DAT"), D1, rows=rows), recv(D1))
        assert [c["kind"] for c in res["conflicts"]] == ["volume_mismatch"]
        assert [x["volume"] for x in resolve.history_known_as_of(e.wh, D1) if x["isin"] == B] == [20000]


@case
def delivery_join_and_missing_states():
    with Env() as e:
        load_days(e, [D1])
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b2.csv"), D2), recv(D2))          # no delivery file for D2
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b3.csv"), D3), recv(D3))
        ingest.ingest_delivery(e.wh, F.mto(e.f("m3.DAT"), D3, rows=F.bars(D3)[:2]), recv(D3))  # C absent
        got = {(x["isin"], x["trade_date"]): x for x in resolve.history_known_as_of(e.wh, D3)}
        assert got[(A, D1)]["delivery_state"] == "known" and got[(A, D1)]["delivery_qty"] == 5000
        assert got[(A, D2)]["delivery_missing_reason"] == "no_source_coverage"
        assert got[(C, D3)]["delivery_missing_reason"] == "absent_in_covered_file"
        assert got[(A, D3)]["delivery_qty"] is not None


# ------------------------------------------------------------------ canary: planted read-path defects
def _cut_sel(field):
    def sel(rows, cutoff):
        best = {}
        for r in rows:
            if r[field] <= cutoff:
                k = (r["isin"], r["trade_date"])
                if k not in best or r["version_no"] > best[k]["version_no"]:
                    best[k] = r
        return list(best.values())
    return sel


def _no_filter(rows, cutoff):
    return list({(r["isin"], r["trade_date"]): r for r in sorted(rows, key=lambda r: r["version_no"])}.values())


def _disclosure_cutoff(rows, cutoff):
    return resolve.select_latest_usable(rows, cutoff - dt.timedelta(hours=3))


def _empty(rows, cutoff):
    return []


def _max_version_then_filter_wrong(rows, cutoff):
    latest = {}
    for r in rows:
        k = (r["isin"], r["trade_date"])
        if k not in latest or r["version_no"] > latest[k]["version_no"]:
            latest[k] = r
    return list(latest.values())


PLANTED = [
    ("no availability filter", _no_filter),
    ("filters on received_at", _cut_sel("received_at")),
    ("filters on source_published_at", _cut_sel("source_published_at")),
    ("filters on effective_from", _cut_sel("effective_from")),
    ("filters on system_available_at", _cut_sel("system_available_at")),
    ("highest version regardless of cutoff", _max_version_then_filter_wrong),
    ("disclosure cutoff used for exchange data", _disclosure_cutoff),
    ("returns nothing", _empty),
]


@case
def canary_catches_every_planted_read_defect():
    with Env() as e:
        load_days(e, [D1, D2])
        resolve.history_known_as_of(e.wh, D2)  # correct path passes
        missed = []
        for name, sel in PLANTED:
            try:
                resolve.history_known_as_of(e.wh, D2, select=sel)
                missed.append(name)
            except pit.LookAheadError:
                pass
        assert not missed, f"canary missed: {missed}"
        print(f"      {len(PLANTED)}/{len(PLANTED)} planted read defects caught")


@case
def canary_catches_real_row_read_early():
    """The guard, not just the sentinels: a real correction usable later must not reach an earlier run."""
    with Env() as e:
        load_days(e, [D1, D2], deliver=False)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c.csv"), D1, F.bars(D1, bump={A: 130})), at_ist(D3, "09:00"))
        raises(pit.LookAheadError, resolve.price_raw_resolved, e.wh, D2, select=_max_version_then_filter_wrong)


# ------------------------------------------------------------------ warehouse
def _state(wh, include_raw_evidence=True):
    """Reader-visible state, normalised; receipt transaction can be inspected separately from parsed state."""
    out = {}
    for t in store.TABLES:
        if not include_raw_evidence and t in {"raw_file", "raw_parse_event"}:
            continue
        rows = wh.read(t)
        # Event creation time and conflict logging time are nondeterministic bookkeeping, not semantic state.
        out[t] = sorted(repr(sorted((k, v) for k, v in r.items() if k not in ("logged_at", "parsed_at")))
                        for r in rows)
    return out


CRASH_POINTS = ["before_record", "after_record", "mid_apply", "before_marker"]


@case
def crash_at_every_batch_boundary_is_all_or_nothing():
    """B2: one file is one batch. At every crash point a reader sees the old state or is refused;
    recovery then yields exactly the state of an uninterrupted ingestion, and the retry is clean."""
    with Env() as ref:
        load_days(ref, [D1], deliver=False)
        before = _state(ref.wh)
        ingest.ingest_bhavcopy(ref.wh, F.legacy(ref.f("c.csv"), D1, F.bars(D1, bump={A: 125})), at_ist(D2, "09:00"))
        after = _state(ref.wh)
    for point in CRASH_POINTS:
        with Env() as e:
            load_days(e, [D1], deliver=False)
            corr = F.legacy(e.f("c.csv"), D1, F.bars(D1, bump={A: 125}))
            raises(store.SimulatedCrash, ingest.ingest_bhavcopy, e.wh, corr, at_ist(D2, "09:00"), _crash_at=point)
            assert _lock_free(e.wh), point                       # a crash inside the writer releases the lock
            if point == "before_record":
                assert _state(e.wh, include_raw_evidence=False) == {
                    k: v for k, v in before.items() if k not in {"raw_file", "raw_parse_event"}
                }, point                                         # parsed transaction did not become visible
                assert len(e.wh.read("raw_file")) == 2, point    # transaction 1 did: baseline + correction receipt
                assert e.wh.orphans(), point                     # only unreferenced debris
                res = ingest.ingest_bhavcopy(e.wh, corr, at_ist(D2, "09:00"))
                assert not res["noop"] and res["rows_changed"] == 1, point
            else:
                raises(store.StoreError, e.wh.read, "price_observation")   # half a batch is never readable
                with e.wh.writer():
                    pass                                          # any writer rolls the batch forward
                assert ingest.ingest_bhavcopy(e.wh, corr, at_ist(D2, "09:30"))["noop"], point
            e.wh.remove_orphans()
            # The parsed/parse-event transaction must equal an uninterrupted ingestion. A later retry may add
            # a distinct raw receipt when its received_at differs; that is a truthful acquisition event, not
            # partial parsed state.
            got, want = _state(e.wh), after
            assert {k: v for k, v in got.items() if k != "raw_file"} == {
                k: v for k, v in want.items() if k != "raw_file"
            }, point
            expected_receipts = 2 if point == "before_record" else 3
            assert len(e.wh.read("raw_file")) == expected_receipts, (point, e.wh.read("raw_file"))
            assert e.wh.orphans() == [], point


@case
def crash_during_recovery_then_recovery_completes():
    with Env() as e:
        load_days(e, [D1], deliver=False)
        corr = F.legacy(e.f("c.csv"), D1, F.bars(D1, bump={A: 125}))
        raises(store.SimulatedCrash, ingest.ingest_bhavcopy, e.wh, corr, at_ist(D2, "09:00"), _crash_at="after_record")
        e.wh._held, e.wh._owner = 1, threading.get_ident()      # a recovering writer, then crash it
        raises(store.SimulatedCrash, e.wh.recover, _crash_at="mid_apply")
        e.wh._held, e.wh._owner = 0, None
        raises(store.StoreError, e.wh.read, "price_observation")
        with e.wh.writer():
            pass
        got = [x["close"] for x in resolve.history_known_as_of(e.wh, D3) if x["isin"] == A]
        assert got == [decimal.Decimal("125")]


@case
def uncommitted_part_listed_in_a_manifest_is_refused():
    with Env() as e:
        load_days(e, [D1], deliver=False)
        pdir = e.wh.pdir("price_observation", D1.isoformat())
        man = json.load(open(os.path.join(pdir, "_manifest.json"), encoding="utf-8"))
        man["parts"][0]["batch"] = "never-committed"
        json.dump(man, open(os.path.join(pdir, "_manifest.json"), "w", encoding="utf-8", newline="\n"))
        raises(store.IntegrityError, e.wh.read, "price_observation")


@case
def writes_outside_a_writer_are_refused():
    with Env() as e:
        raises(store.StoreError, e.wh.batch)


@case
def tampered_part_is_refused():
    with Env() as e:
        load_days(e, [D1], deliver=False)
        pdir = e.wh.pdir("price_observation", D1.isoformat())
        part = [f for f in os.listdir(pdir) if f.startswith("part-")][0]
        with open(os.path.join(pdir, part), "a", encoding="utf-8", newline="\n") as f:
            f.write("\n")
        raises(store.StoreError, e.wh.read, "price_observation")


@case
def snapshot_isolates_reads_from_later_writes():
    with Env() as e:
        load_days(e, [D1, D2], deliver=False)
        snap = e.wh.snapshot()
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c.csv"), D1, F.bars(D1, bump={A: 140})), at_ist(D2, "09:00"))
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b3.csv"), D3), recv(D3))
        old = resolve.history_known_as_of(e.wh, D3, snapshot=snap)
        assert {x["trade_date"] for x in old} == {D1, D2}
        assert [x["close"] for x in old if x["isin"] == A and x["trade_date"] == D1] == [decimal.Decimal("119")]


def _lock_free(wh):
    try:
        fd = fsio.lock_exclusive(os.path.join(wh.root, ".writer.lock"))
    except fsio.LockHeld:
        return False
    fsio.unlock(fd)
    return True


@case
def live_writer_refused_and_lock_file_alone_blocks_nothing():
    """r5.6: the lock is an OS lock. A second holder is refused while the first holds it; a leftover lock FILE
    (what r5.5 treated as the lock) blocks nothing."""
    with Env() as e:
        lock = os.path.join(e.wh.root, ".writer.lock")
        fd = fsio.lock_exclusive(lock)                    # another handle: another writer, as far as the OS knows
        try:
            raises(store.StoreError, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))
            assert e.wh.partitions("price_observation") == []
        finally:
            fsio.unlock(fd)
        assert os.path.exists(lock)                       # the file stays, and is harmless
        assert not ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))["noop"]
        assert os.path.exists(lock) and _lock_free(e.wh)


_HOLDER = """
import os, sys, time
sys.path.insert(0, sys.argv[1])
from eos import store
wh = store.Warehouse(sys.argv[2], sys.argv[3])
with wh.writer():
    print("locked", flush=True)
    time.sleep(120)
"""


@case
def writer_killed_while_holding_the_lock_leaves_no_stale_lock():
    """Review P1 (stale lock): r5.5's lock file survived a hard crash and blocked every later ingestion until
    someone deleted it by hand. A process killed while holding the writer releases it with its death."""
    import subprocess
    with Env() as e:
        child = subprocess.Popen([sys.executable, "-c", _HOLDER, KIT, e.wh.root, CODEC], stdout=subprocess.PIPE,
                                 text=True, encoding="utf-8")
        try:
            assert child.stdout.readline().strip() == "locked"
            raises(store.StoreError, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))
        finally:
            child.kill()                                  # SIGKILL / TerminateProcess: no cleanup code runs
            child.wait(timeout=30)
            child.stdout.close()
        assert child.returncode != 0
        import time
        for _ in range(100):          # Windows frees a dead process's locks "when resources allow": wait <= 10 s
            if _lock_free(e.wh):
                break
            time.sleep(0.1)
        assert not ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))["noop"]


@case
def parser_rejection_keeps_a_durable_raw_receipt():
    """r5.7 Fix 4: landing is transaction 1; parser rejection cannot erase the fact of receipt."""
    with Env() as e:
        p = e.f("unknown.csv")
        payload = b"THIS,IS,NOT,A,KNOWN,EXCHANGE,FORMAT\n1,2,3,4,5,6,7\n"
        open(p, "wb").write(payload)
        err = raises(parsers.FormatError, ingest.ingest_bhavcopy, e.wh, p, recv(D1))
        assert err
        (raw,) = e.wh.read("raw_file")
        assert raw["source_id"] == "nse_cm_bhavcopy"
        assert raw["original_name"] == "unknown.csv"
        assert raw["file_sha256"] == store.hashlib.sha256(payload).hexdigest()
        assert raw["size_bytes"] == len(payload)
        assert open(e.wh.raw_path(raw["landed_path"]), "rb").read() == payload
        assert e.wh.read("price_observation") == []
        (event,) = e.wh.read("raw_parse_event")
        assert event["file_sha256"] == raw["file_sha256"] and event["status"] == "rejected"
        assert "FormatError" in event["parse_error"] and event["trade_date"] is None
        assert e.wh.verify_raw_integrity() == 1


@case
def raw_provenance_rules_distinguish_manual_and_automated_acquisition():
    """r5.7 Fix 9: null provenance is legitimate only where the declared acquisition method permits it."""
    with Env() as e:
        src = F.legacy(e.f("manual.csv"), D1)
        ingest.ingest_bhavcopy(e.wh, src, recv(D1), acquisition_method="manual_upload")
        (raw,) = e.wh.read("raw_file")
        assert raw["acquisition_method"] == "manual_upload"
        assert raw["source_url"] is None and raw["retrieved_at"] is None

    with Env() as e:
        src = F.legacy(e.f("download.csv"), D1)
        retrieved = at_ist(D2, "07:50")
        received = at_ist(D2, "08:00")
        ingest.ingest_bhavcopy(e.wh, src, received, acquisition_method="scheduled_download",
                               source_url="https://example.invalid/download.csv", retrieved_at=retrieved)
        (raw,) = e.wh.read("raw_file")
        assert raw["acquisition_method"] == "scheduled_download"
        assert raw["source_url"] == "https://example.invalid/download.csv" and raw["retrieved_at"] == retrieved

    for method, url, retrieved in (("scheduled_download", None, at_ist(D2, "07:50")),
                                   ("scheduled_download", "https://example.invalid/x", None),
                                   ("api", None, None),
                                   ("vendor_drop", None, None),
                                   ("archive_import", None, None),
                                   ("not_a_method", None, None)):
        with Env() as e:
            src = F.legacy(e.f("bad.csv"), D1)
            raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh, src, recv(D1),
                   acquisition_method=method, source_url=url, retrieved_at=retrieved)
            assert e.wh.read("raw_file") == [], "invalid provenance must fail before landing/receipt"

    with Env() as e:
        src = F.legacy(e.f("future.csv"), D1)
        raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh, src, at_ist(D2, "08:00"),
               acquisition_method="scheduled_download", source_url="https://example.invalid/x",
               retrieved_at=at_ist(D2, "08:01"))
        assert e.wh.read("raw_file") == []


@case
def raw_integrity_verification_detects_forced_post_landing_tamper():
    """r5.7 Fix 10: immutable permissions are defence in depth; evidence verification re-hashes the bytes."""
    with Env() as e:
        src = F.legacy(e.f("b.csv"), D1)
        ingest.ingest_bhavcopy(e.wh, src, recv(D1))
        (raw,) = e.wh.read("raw_file")
        assert e.wh.verify_raw_integrity() == 1
        e.wh.snapshot()  # an evidence freeze/snapshot must also verify raw blobs
        landed = e.wh.raw_path(raw["landed_path"])
        os.chmod(landed, 0o644)
        with open(landed, "ab") as f:
            f.write(b"forced-tamper")
        ex = raises(store.IntegrityError, e.wh.verify_raw_integrity)
        assert raw["file_sha256"][:12] in str(ex)
        raises(store.IntegrityError, e.wh.snapshot)


@case
def raw_file_is_landed_byte_for_byte_and_parsed_from_the_landed_copy():
    """Review P1 (raw landing): every source file's exact bytes are kept, content-addressed and write-once,
    and a raw_file receipt is committed before parsing/observations."""
    with Env() as e:
        src = F.legacy(e.f("cm16SEP2026bhav.csv"), D1)
        original = open(src, "rb").read()
        at = at_ist(D2, "07:55")
        ingest.ingest_bhavcopy(e.wh, src, recv(D1), source_url="https://example.invalid/cm16SEP2026bhav.csv",
                               retrieved_at=at)
        (raw,) = e.wh.read("raw_file")
        assert raw["original_name"] == "cm16SEP2026bhav.csv" and raw["retrieved_at"] == at
        assert raw["acquisition_method"] == "manual_upload"
        assert raw["size_bytes"] == len(original) and raw["file_sha256"] == store.hashlib.sha256(original).hexdigest()
        landed = e.wh.raw_path(raw["landed_path"])
        assert raw["landed_path"] == f"_raw/nse_cm_bhavcopy/{raw['file_sha256']}.csv"
        assert open(landed, "rb").read() == original
        # the download folder changes afterwards: the landed copy and every observation are untouched
        with open(src, "wb") as f:
            f.write(b"overwritten")
        assert open(landed, "rb").read() == original
        assert {r["file_sha256"] for r in e.wh.read("price_observation") if not canary.is_canary(r["isin"])} \
            == {raw["file_sha256"]}
        # landing the same bytes again is a no-op; a landed file whose bytes changed is refused
        with open(e.f("copy.csv"), "wb") as f:
            f.write(original)
        assert ingest.ingest_bhavcopy(e.wh, e.f("copy.csv"), recv(D1))["noop"]
        os.chmod(landed, 0o644)
        with open(landed, "ab") as f:
            f.write(b"\n")
        raises(store.IntegrityError, ingest.ingest_bhavcopy, e.wh, e.f("copy.csv"), recv(D1))


@case
def parsing_reads_the_landed_copy_not_the_original():
    with Env() as e:
        src = F.legacy(e.f("b.csv"), D1)
        real_land = e.wh.land

        def land_then_tamper(source_id, path):
            out = real_land(source_id, path)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write("garbage that would not parse\n")
            return out
        e.wh.land = land_then_tamper
        res = ingest.ingest_bhavcopy(e.wh, src, recv(D1))
        assert not res["noop"] and res["rows_new"] == 3


@case
def two_ingestions_racing_cannot_both_allocate_a_version():
    """B3: the lock spans read-latest -> allocate -> commit. While one correction is between its read and
    its commit, a second is refused rather than allocating the same version number."""
    with Env() as e:
        load_days(e, [D1], deliver=False)
        c1 = F.legacy(e.f("c1.csv"), D1, F.bars(D1, bump={A: 130}))
        c2 = F.legacy(e.f("c2.csv"), D1, F.bars(D1, bump={A: 140}))
        inside, release, errors = threading.Event(), threading.Event(), []
        real_version = ingest._version

        def slow_version(*a, **k):
            out = real_version(*a, **k)
            inside.set()
            release.wait(5)
            return out

        ingest._version = slow_version
        try:
            t = threading.Thread(target=lambda: ingest.ingest_bhavcopy(e.wh, c1, at_ist(D2, "09:00")))
            t.start()
            inside.wait(5)
            ingest._version = real_version
            try:
                ingest.ingest_bhavcopy(e.wh, c2, at_ist(D2, "09:01"))
            except store.StoreError as ex:
                errors.append(ex)
            release.set()
            t.join(5)
        finally:
            ingest._version = real_version
        assert len(errors) == 1, "the second writer was not refused"
        ingest.ingest_bhavcopy(e.wh, c2, at_ist(D2, "09:05"))      # retried afterwards, it versions correctly
        v = sorted((r["version_no"], r["close"]) for r in e.wh.read("price_observation") if r["isin"] == A)
        assert v == [(1, decimal.Decimal("119")), (2, decimal.Decimal("130")), (3, decimal.Decimal("140"))], v
        assert [x["close"] for x in resolve.history_known_as_of(e.wh, D3) if x["isin"] == A] == [decimal.Decimal("140")]


@case
def duplicate_version_identity_is_an_integrity_failure():
    """B3 belt and braces: if duplicates ever exist (the reviewer's stale-read scenario), reads fail hard
    instead of silently picking one."""
    with Env() as e:
        load_days(e, [D1], deliver=False)
        real = e.wh.read
        stale = list(real("price_observation", [D1.isoformat()]))
        e.wh.read = lambda t, k=None, s=None: stale if t == "price_observation" and k == [D1.isoformat()] else real(t, k, s)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c1.csv"), D1, F.bars(D1, bump={A: 130})), at_ist(D2, "09:00"))
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c2.csv"), D1, F.bars(D1, bump={A: 140})), at_ist(D2, "09:01"))
        e.wh.read = real
        raises(store.IntegrityError, resolve.history_known_as_of, e.wh, D3)


# ------------------------------------------------------------------ the two read contracts
@case
def history_known_as_of_and_panel_differ_exactly_on_later_corrections():
    """B8: a correction to D1 arrives at 10:00 on D2. The decision at D1 must see the original; the decision
    at D3 may see the correction; the panel shows each bar as first known."""
    with Env() as e:
        load_days(e, [D1, D2, D3], deliver=False)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("c.csv"), D1, F.bars(D1, bump={A: 125})), at_ist(D2, "10:00"))
        close = lambda rows, d: [x["close"] for x in rows if x["isin"] == A and x["trade_date"] == d][0]  # noqa
        panel = resolve.point_in_time_panel(e.wh, D1, D3)
        assert close(panel, D1) == decimal.Decimal("119")                            # as first known
        assert close(resolve.history_known_as_of(e.wh, D1), D1) == decimal.Decimal("119")
        assert close(resolve.history_known_as_of(e.wh, D3), D1) == decimal.Decimal("125")
        # the panel's row for each date equals that date's own exact view of that date
        for d in (D1, D2, D3):
            exact = [x for x in resolve.history_known_as_of(e.wh, d) if x["trade_date"] == d]
            assert [x for x in panel if x["trade_date"] == d] == exact, d
        assert {x["resolved_at_cutoff"] for x in panel if x["trade_date"] == D2} == {run_cutoffs(D2)["exchange_eod"]}


# ------------------------------------------------------------------ r5.5 additions (audit B3, B4, C5, C6)
@case
def panel_keeps_a_late_first_publication_and_masks_it_per_decision():
    """B3a: D2's file is first published at 23:30, after D2's 23:00 cutoff. r5.4's panel dropped D2 for ever;
    the decision on D2 must not see it, and every later decision must."""
    with Env() as e:
        for d, hhmm in ((D1, "22:40"), (D2, "23:30"), (D3, "22:40")):
            ingest.ingest_bhavcopy(e.wh, F.legacy(e.f(f"b{d}.csv"), d), at_ist(d, hhmm), mode="live",
                                   now=at_ist(d, hhmm))
        panel = resolve.point_in_time_panel(e.wh, D1, D3)
        assert {x["trade_date"] for x in panel} == {D1, D2, D3}
        dates = lambda E: {x["trade_date"] for x in resolve.panel_as_of(panel, E)}  # noqa: E731
        assert dates(D2) == {D1}
        assert dates(D3) == {D1, D2, D3} == {x["trade_date"] for x in resolve.history_known_as_of(e.wh, D3)}


@case
def panel_masks_delivery_that_arrived_after_the_decision():
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b1.csv"), D1), at_ist(D1, "22:00"), mode="live", now=at_ist(D1, "22:01"))
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b2.csv"), D2), at_ist(D2, "22:00"), mode="live", now=at_ist(D2, "22:01"))
        ingest.ingest_delivery(e.wh, F.mto(e.f("m1.DAT"), D1), at_ist(D2, "09:00"), mode="live", now=at_ist(D2, "09:01"))
        panel = resolve.point_in_time_panel(e.wh, D1, D2)
        at = lambda E: [x for x in resolve.panel_as_of(panel, E) if x["isin"] == A and x["trade_date"] == D1][0]  # noqa
        assert at(D1)["delivery_state"] == "missing" and at(D1)["delivery_missing_reason"] == "not_yet_available"
        assert at(D2)["delivery_state"] == "known"


@case
def backfill_inference_refused_for_a_same_day_file_and_after_live_capture_start():
    """B3b: a file received on its own trade date is a live file; r5.4 back-dated it to 22:30."""
    with Env() as e:
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("a.csv"), D1),
                                     at_ist(D1, "23:45"), mode="backfill"))
        p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml"), encoding="utf-8"))
        p["backfill"]["live_capture_start"] = D2.isoformat()
        path = e.f("sp.yaml")
        yaml.safe_dump(p, open(path, "w", encoding="utf-8", newline="\n"))
        pol = source_policy.load(path)
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b1.csv"), D1), recv(D1), policy=pol)       # before: allowed
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("b2.csv"), D2), at_ist(D3, "12:00"), policy=pol))


@case
def one_bad_row_is_quarantined_not_the_whole_day():
    """C5: 1 defective row in 20 (5%) is quarantined and the other 19 are written; beyond the limit, nothing is."""
    many = [dict(r, isin=f"INE{n:03d}X01010", sym=f"S{n}") for n in range(20) for r in F.bars(D1)[:1]]
    with Env() as e:
        bad = [dict(r) for r in many]
        bad[3].update(o="0.00", h="0.00", l="0.00", c="0.00")
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1, bad), recv(D1))
        assert [q["reason"] for q in res["quarantined"]] == ["ohlc_invalid"]
        got = {x["isin"] for x in resolve.history_known_as_of(e.wh, D1)}
        assert len(got) == 19 and bad[3]["isin"] not in got
        assert [q["isin"] for q in e.wh.read("row_quarantine")] == [bad[3]["isin"]]
        worse = [dict(r) for r in many]
        for i in (1, 2):
            worse[i]["isin"] = "BAD"
        _unchanged(e, lambda: raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
                                     F.legacy(e.f("b.csv"), D2, worse), recv(D2)))


@case
def quarantined_delivery_is_not_reported_as_absent():
    many = [dict(r, isin=f"INE{n:03d}X01010", sym=f"S{n}") for n in range(20) for r in F.bars(D1)[:1]]
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1, many), recv(D1))
        res = ingest.ingest_delivery(e.wh, F.mto(e.f("m.DAT"), D1, rows=many, deliv={many[0]["isin"]: 10 ** 9}),
                                     recv(D1))
        assert [q["reason"] for q in res["quarantined"]] == ["invalid_quantity"]
        got = {x["isin"]: x for x in resolve.history_known_as_of(e.wh, D1)}
        assert got[many[0]["isin"]]["delivery_missing_reason"] == "quarantined"
        assert got[many[1]["isin"]]["delivery_state"] == "known"


@case
def store_refuses_unknown_columns_floats_for_decimals_and_bools_for_ints():
    with Env() as e:
        base = {"file_sha256": "x", "source_id": "s", "trade_date": D1, "received_at": at_ist(D1, "22:00"),
                "rows_new": 1, "rows_changed": 0, "rows_unchanged": 0, "mode": "backfill"}
        raises(store.StoreError, e.wh.append, "ingestion_log", "2026-09-16", [dict(base, surprise=1)])
        raises(store.StoreError, e.wh.append, "ingestion_log", "2026-09-16", [dict(base, rows_new=True)])
        row = {k: None for k in store.TABLES["price_observation"]}
        row.update(isin="INE000A01011", trade_date=D1, version_no=1, close=119.5)
        raises(store.StoreError, e.wh.append, "price_observation", "2026-09-16", [row])


@case
def duplicate_file_check_reads_only_its_own_date():
    """C6: r5.4 re-read the whole ingestion log for every file."""
    with Env() as e:
        load_days(e, [D1, D2], deliver=False)
        seen = []
        real = e.wh.read
        e.wh.read = lambda t, k=None, s=None: (seen.append((t, k)), real(t, k, s))[1]
        assert ingest.ingest_bhavcopy(e.wh, F.legacy(e.f(f"b{D2}.csv"), D2), recv(D2))["noop"]
        e.wh.read = real
        assert seen == [("raw_file", [recv(D2).astimezone(IST).date().isoformat()]),
                        ("ingestion_log", [D2.isoformat()])], seen


@case
def naive_timestamps_refused_by_store():
    with Env() as e:
        row = {k: None for k in store.TABLES["ingestion_log"]}
        row.update(received_at=dt.datetime(2026, 9, 16, 23, 0))
        raises(store.StoreError, e.wh.append, "ingestion_log", "2026-09-16", [row])


@case
def parquet_round_trip():
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        NOT_RUN.append("parquet_round_trip (pyarrow not installed)")
        return
    with Env("parquet") as e:
        load_days(e, [D1, D2])
        got = resolve.history_known_as_of(e.wh, D2)
        assert len(got) == 6 and got[0]["close"] == decimal.Decimal("119")
        assert all(x["usable_from"].tzinfo is not None for x in got)


@case
def parquet_codec_never_falls_back_silently():
    try:
        import pyarrow  # noqa: F401
        return
    except ImportError:
        raises(store.StoreError, store.Warehouse, tempfile.mkdtemp(), "parquet")



# ------------------------------------------------------------------ r5.8 real-NSE-derived source/master semantics
@case
def udiff_same_isin_across_eq_and_bl_is_valid_and_eq_is_canonical():
    with Env() as e:
        rows = F.bars(D1)
        san_eq = dict(rows[0], sid=19001, sym="SANOFI", ser="EQ", isin="INE058A01010")
        san_bl = dict(san_eq, sid=19002, ser="BL", c="7000.00", h="7001.00", l="6999.00", o="7000.00",
                      last="7000.00", pc="6995.00", val="700000.00")
        rows = [san_eq, san_bl, dict(rows[1], sid=19003), dict(rows[2], sid=19004)]
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("u.csv"), D1, rows), recv(D1))
        assert res["rows_new"] == 4 and res["quarantined"] == []
        src = resolve.source_prices_known_as_of(e.wh, D1)
        assert len(src) == 4 and len([r for r in src if r["isin"] == "INE058A01010"]) == 2
        got = [r for r in resolve.history_known_as_of(e.wh, D1) if r["isin"] == "INE058A01010"]
        assert len(got) == 1 and got[0]["series"] == "EQ" and got[0]["source_instrument_id"] == "19001"


@case
def real_20260924_shape_3637_source_rows_are_preserved_and_bl_is_only_noncanonical():
    """Real-file acceptance shape from 24-Sep-2026: 3,637 source rows including two EQ+BL ISIN pairs."""
    with Env() as e:
        base = F.bars(D1)[0]
        rows = []
        for n in range(3637):
            isin = f"INE{n:08d}X"
            rows.append(dict(base, sid=100000+n, sym=f"S{n}", ser="EQ", isin=isin,
                             vol=100+n, val=f"{(100+n)*100:.2f}", trades=1+n))
        # Two legitimate block-deal observations reuse the economic-security ISIN but have different source tokens.
        rows[1].update(isin=rows[0]["isin"], sym=rows[0]["sym"], ser="BL")
        rows[3].update(isin=rows[2]["isin"], sym=rows[2]["sym"], ser="BL")
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("u.csv"), D1, rows), recv(D1))
        assert res["rows_new"] == 3637 and len(res["quarantined"]) == 0
        src = resolve.source_prices_known_as_of(e.wh, D1)
        canonical = resolve.history_known_as_of(e.wh, D1)
        assert len(src) == 3637 and len(canonical) == 3635
        assert e.wh.verify_raw_integrity() == 1


@case
def exact_duplicate_source_observation_is_still_rejected():
    with Env() as e:
        rows = F.bars(D1)
        a = dict(rows[0], sid=5000)
        # Same exchange token twice is a true duplicate; both rows quarantine and exceed the file threshold.
        raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh,
               F.udiff(e.f("dupe.csv"), D1, [a, dict(a), dict(rows[1], sid=5001), dict(rows[2], sid=5002)]), recv(D1))


@case
def mii_master_classifies_from_exchange_fields_not_names_or_isin_prefixes():
    with Env() as e:
        rows = [
            dict(sid=1, sym="20MICRONS", isin="INE144J01027", type=0, ser="EQ"),
            dict(sid=2, sym="GOLD360", isin="INF579M01BB5", type=4, ser="EQ"),
            dict(sid=3, sym="JISLDVREQS", isin="IN9175A01010", type=0, ser="EQ"),
            dict(sid=4, sym="011NSETEST", isin="DUMMYSAN005", type=0, ser="EQ"),
            dict(sid=5, sym="DECGOLD", isin="INE945F01025", type=0, ser="EQ", name="DECCAN GOLD MINES LTD."),
        ]
        pth = F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1, rows)
        res = ingest.ingest_security_master(e.wh, pth, recv(D1), effective_session=D1,
                                            effective_session_basis="validated_convention")
        assert res["rows_new"] == 5 and e.wh.verify_raw_integrity() == 1
        got = {r["symbol"]: r for r in e.wh.read("security_master_observation")}
        assert got["20MICRONS"]["security_class"] == "company_equity"
        assert got["GOLD360"]["security_class"] == "other"
        assert got["JISLDVREQS"]["security_class"] == "company_equity"  # IN9 is not rejected by prefix
        assert got["011NSETEST"]["is_dummy"] and got["011NSETEST"]["market_eligible"] is False
        assert got["DECGOLD"]["security_class"] == "company_equity"  # name contains GOLD but is not a fund heuristic


@case
def master_effective_session_prevents_same_date_lookahead_and_unresolved_fails_closed():
    old = [dict(sid=11033, sym="SANGINITA", isin="INE753W01010", type=0, ser="BE")]
    new = [dict(sid=11033, sym="AGASTYAEN", isin="INE753W01010", type=0, ser="BE")]
    with Env() as e:
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1, old),
                                      recv(D1), effective_session=D1, effective_session_basis="exchange_notice")
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_17092026.csv.gz"), D2, new),
                                      recv(D2), effective_session=D3, effective_session_basis="exchange_notice")
        assert resolve.security_master_state_as_of(e.wh, D2)["11033"]["row"]["symbol"] == "SANGINITA"
        assert resolve.security_master_state_as_of(e.wh, D3)["11033"]["row"]["symbol"] == "AGASTYAEN"
    with Env() as e:
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1, old),
                                      recv(D1), effective_session=D1, effective_session_basis="exchange_notice")
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_17092026.csv.gz"), D2, new),
                                      recv(D2))
        assert resolve.security_master_state_as_of(e.wh, D2)["11033"]["state"] == "master_state_unresolved"


@case
def explicit_no_trade_requires_resolved_eligible_master_and_complete_bhavcopy():
    with Env() as e:
        bh = [dict(F.bars(D2)[0], sid=1000), dict(F.bars(D2)[1], sid=1001)]
        ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("u.csv"), D2, bh), recv(D2))
        master = [
            dict(sid=1000, sym=bh[0]["sym"], isin=bh[0]["isin"], type=0, ser="EQ"),
            dict(sid=1001, sym=bh[1]["sym"], isin=bh[1]["isin"], type=0, ser="EQ"),
            dict(sid=2000, sym="ASSAMENT", isin="INE165G01010", type=0, ser="EQ"),
            dict(sid=3000, sym="GOLD360", isin="INF579M01BB5", type=4, ser="EQ"),
        ]
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1, master),
                                      recv(D1), effective_session=D2, effective_session_basis="validated_convention")
        states = {r["source_instrument_id"]: r for r in resolve.resolve_session_states(e.wh, D2)}
        assert states["1000"]["trade_state"] == "traded"
        assert states["2000"]["trade_state"] == "no_trade" and states["2000"]["canonical_price"] is None
        assert states["3000"]["trade_state"] == "not_in_target_universe"
        assert not [r for r in e.wh.read("price_observation", [D2.isoformat()]) if r.get("source_instrument_id") == "2000"]


@case
def unresolved_or_unknown_master_semantics_never_create_no_trade():
    with Env() as e:
        bh = [dict(F.bars(D2)[0], sid=1000)]
        ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("u.csv"), D2, bh), recv(D2))
        rows = [dict(sid=2000, sym="X", isin="INE123A01010", type=0, ser="EQ", status=99)]
        ingest.ingest_security_master(e.wh, F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1, rows),
                                      recv(D1), effective_session=D2, effective_session_basis="validated_convention")
        state = {r["source_instrument_id"]: r for r in resolve.resolve_session_states(e.wh, D2)}["2000"]
        assert state["trade_state"] == "master_state_unresolved"
        assert state["master_row"]["status_code_known"] is False and state["master_row"]["market_eligible"] is None


@case
def current_mii_header_is_exact_and_schema_drift_fails_loudly():
    import gzip
    with Env() as e:
        good = F.security_master(e.f("NSE_CM_security_16092026.csv.gz"), D1,
                                 [dict(sid=1, sym="AAA", isin="INE000A01011")])
        fmt, day, rows = parsers.parse_security_master(parsers.read_bytes(good), os.path.basename(good))
        assert fmt == "nse_cm_mii_security" and day == D1 and len(rows) == 1
        text = parsers.read_bytes(good).decode("utf-8").replace("FinInstrmId,", "TokenRenamed,", 1)
        bad = e.f("NSE_CM_security_16092026_bad.csv.gz")
        with gzip.open(bad, "wb") as f:
            f.write(text.encode())
        # Use the valid expected filename when calling parser so the failure is the header, not filename parsing.
        raises(parsers.FormatError, parsers.parse_security_master, gzip.decompress(open(bad, "rb").read()),
               "NSE_CM_security_16092026.csv.gz")



@case
def mto_header_count_filename_date_and_percentage_are_enforced():
    with Env() as e:
        good = F.mto(e.f("MTO_16092026.DAT"), D1)
        fmt, day, rows = parsers.parse_mto(parsers.read_bytes(good), os.path.basename(good))
        assert fmt == "nse_mto_delivery" and day == D1 and len(rows) == 3
        assert rows[0]["delivery_pct_reported"] == decimal.Decimal("50.0000")
        text = open(good, encoding="utf-8").read()
        bad_count = text.replace(",0000003\n", ",0000004\n", 1)
        raises(parsers.FormatError, parsers.parse_mto, bad_count.encode(), "MTO_16092026.DAT")
        raises(parsers.FormatError, parsers.parse_mto, text.encode(), "MTO_17092026.DAT")


@case
def mto_percentage_mismatch_is_logged_without_overwriting_quantities():
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1))
        p = F.mto(e.f("MTO_16092026.DAT"), D1)
        text = open(p, encoding="utf-8").read().replace(",5000,50.00\n", ",5000,49.00\n", 1)
        open(p, "w", encoding="utf-8", newline="\n").write(text)
        res = ingest.ingest_delivery(e.wh, p, recv(D1))
        assert "delivery_pct_mismatch" in [c["kind"] for c in res["conflicts"]]
        row = [r for r in e.wh.read("delivery_observation") if r["isin"] == A][0]
        assert row["delivery_qty"] == 5000 and row["delivery_pct_reported"] == decimal.Decimal("49.0000")


@case
def full_bhav_delivery_is_independent_crosscheck_and_preserves_missing_delivery():
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1))
        p = F.full_bhav_delivery(e.f("sec_bhavdata_full_16092026.csv"), D1, missing_isins={B},
                                 pct_overrides={A: "49.00"})
        res = ingest.ingest_delivery_crosscheck(e.wh, p, recv(D1))
        assert res["rows_new"] == 3 and "delivery_pct_mismatch" in [c["kind"] for c in res["conflicts"]]
        got = {r["isin"]: r for r in e.wh.read("delivery_crosscheck_observation")}
        assert got[A]["delivery_available"] is True and got[A]["delivery_qty"] == 5000
        assert got[B]["delivery_available"] is False and got[B]["delivery_qty"] is None
        assert not e.wh.partitions("delivery_observation")  # validation reference can never become the primary feed


@case
def mto_and_full_bhav_delivery_are_compared_in_either_order():
    """r5.10: r5.9 described full-bhav delivery as a cross-check of MTO but never compared the two. Whichever file
    arrives second now logs each difference; neither value is ever changed."""
    for order in ("mto_first", "full_bhav_first"):
        with Env() as e:
            ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("b.csv"), D1), recv(D1))
            vol_c = next(r["vol"] for r in F.bars(D1) if r["isin"] == C)
            mto = lambda: ingest.ingest_delivery(e.wh, F.mto(e.f("MTO_16092026.DAT"), D1, deliv={C: vol_c // 2 + 7}),  # noqa: E731
                                                 recv(D1, "09:00"))
            fb = lambda: ingest.ingest_delivery_crosscheck(e.wh, F.full_bhav_delivery(  # noqa: E731
                e.f("sec_bhavdata_full_16092026.csv"), D1, missing_isins={B}), recv(D1, "09:30"))
            first, second = (mto, fb) if order == "mto_first" else (fb, mto)
            assert not [c for c in first()["conflicts"] if c["kind"].startswith("delivery_") and "mismatch" in c["kind"]
                        and c["kind"] != "delivery_pct_mismatch"]
            got = sorted((c["isin"], c["kind"]) for c in second()["conflicts"]
                         if c["kind"] in ("delivery_source_mismatch", "delivery_availability_mismatch"))
            assert got == [(B, "delivery_availability_mismatch"), (C, "delivery_source_mismatch")], (order, got)
            primary = {r["isin"]: r["delivery_qty"] for r in e.wh.read("delivery_observation")}
            assert primary[C] == vol_c // 2 + 7 and primary[B] is not None    # MTO stays primary, uncorrected


@case
def a_file_rejected_after_parsing_records_its_outcome():
    """r5.10: a file that parses but fails a quality check gets a `rejected` parse event with its format and date;
    r5.7-r5.9 left only the receipt, which looks the same as a crash between receipt and parse."""
    with Env() as e:
        raises(ingest.QualityError, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("b.csv"), D1), at_ist(D1, "23:30"))
        (ev,) = e.wh.read("raw_parse_event")
        assert ev["status"] == "rejected" and ev["trade_date"] == D1 and ev["source_format"] == "nse_bhavcopy_legacy"
        assert "fewer than" in ev["parse_error"] and len(e.wh.read("raw_file")) == 1
        load_days(e, [D1], deliver=False)
        raises(ingest.KillSwitch, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("k.csv"), D2, F.bars(D2)[:1]), recv(D2))
        kinds = sorted((r["status"], r["trade_date"]) for r in e.wh.read("raw_parse_event"))
        assert ("rejected", D2) in kinds


@case
def security_master_retains_price_range_fields_without_interpreting_band_state():
    import gzip, csv, io
    with Env() as e:
        from eos.m2.parsers import MII_SECURITY_COLS
        rec = {c: "" for c in MII_SECURITY_COLS}
        rec.update({"FinInstrmId": "1", "TckrSymb": "AAA", "SctySrs": "EQ", "FinInstrmNm": "AAA LTD",
                    "ISIN": A, "NewBrdLotQty": "1", "SctyTpFlg": "0", "SctyStsNrmlMkt": "6",
                    "ElgbltyNrmlMkt": "1", "DelFlg": "N", "PricRg": "90.00-110.00", "PricRgTp": "1",
                    "MaxPric": "110.00", "MinPric": "90.00", "TickSz": "0.05"})
        buf = io.StringIO(newline="")
        w = csv.DictWriter(buf, fieldnames=MII_SECURITY_COLS, lineterminator="\n"); w.writeheader(); w.writerow(rec)
        p = e.f("NSE_CM_security_16092026.csv.gz")
        with gzip.open(p, "wb") as f: f.write(buf.getvalue().encode())
        ingest.ingest_security_master(e.wh, p, recv(D1))
        row = e.wh.read("security_master_observation")[0]
        assert row["price_range_text"] == "90.00-110.00"
        assert row["max_price"] == decimal.Decimal("110.0000") and row["tick_size"] == decimal.Decimal("0.0500")
        assert row["effective_session"] is None  # range evidence does not silently become a band-close decision


@case
def price_band_reference_capture_is_receipted_but_never_promoted_to_coverage():
    with Env() as e:
        p = e.f("sec_list_16092026.csv")
        open(p, "wb").write(b"SYMBOL,SERIES,BAND\nAAAIND,EQ,20\n")
        res = ingest.capture_unparsed_reference(e.wh, "nse_cm_price_band", p, recv(D1))
        assert res["status"] == "captured_unparsed" and e.wh.verify_raw_integrity() == 1
        events = e.wh.read("raw_parse_event")
        assert len(events) == 1 and events[0]["status"] == "captured_unparsed"
        assert not e.wh.partitions("source_coverage")
        raises(ingest.QualityError, ingest.capture_unparsed_reference, e.wh, "unknown", p, recv(D1))

# ------------------------------------------------------------------ platform primitives (r5.6, Windows defects)
class _WindowsOs:
    """os as eos/fsio.py sees it during the windows-sim pass: opening a directory fails, as on Windows."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def open(self, path, flags, *a, **k):
        if self._real.path.isdir(path):
            raise PermissionError(13, "Permission denied: Windows cannot open a directory", path)
        return self._real.open(path, flags, *a, **k)


@case
def windows_replace_uses_write_through_and_never_opens_a_directory():
    """Review Windows defect 1: r5.5 fsync-ed the directory after every rename, which raises on Windows, so no
    warehouse write could succeed there. Under the Windows paths every replace is MoveFileExW with
    REPLACE_EXISTING | WRITE_THROUGH and no directory is opened. Runs on the windows-sim pass here (and is
    trivially true on a real Windows pass, where the calls go to kernel32)."""
    if fsio.platform() != "windows-sim":
        return
    fsio.SIM_KERNEL32.calls.clear()
    with Env() as e:
        load_days(e, [D1])
    flags = {c[2] for c in fsio.SIM_KERNEL32.calls}
    assert fsio.SIM_KERNEL32.calls and flags == {fsio.MOVEFILE_REPLACE_EXISTING | fsio.MOVEFILE_WRITE_THROUGH}
    raises(AssertionError, fsio._fsync_dir, KIT)


@case
def windows_sharing_violation_is_retried_then_reported():
    """An antivirus or indexer holding the target makes MoveFileExW fail with a sharing violation. A brief one
    is retried with bounded backoff; a persistent one is an error and leaves no temp file behind."""
    old = os.environ.get("EOS_PLATFORM")
    os.environ["EOS_PLATFORM"] = "windows-sim"
    delays, fsio.RETRY_DELAYS = fsio.RETRY_DELAYS, (0.0,) * len(fsio.RETRY_DELAYS)
    try:
        d = tempfile.mkdtemp()
        target = os.path.join(d, "x.json")
        fsio.SIM_KERNEL32.inject_sharing_violations = 3
        fsio.write_durable(target, b"one", ".tmp-a")
        assert open(target, "rb").read() == b"one" and fsio.SIM_KERNEL32.inject_sharing_violations == 0
        fsio.SIM_KERNEL32.inject_sharing_violations = len(fsio.RETRY_DELAYS) + 1
        raises(OSError, fsio.write_durable, target, b"two", ".tmp-b")
        assert open(target, "rb").read() == b"one" and sorted(os.listdir(d)) == ["x.json"]
        rmtree(d)
    finally:
        fsio.SIM_KERNEL32.inject_sharing_violations = 0
        fsio.RETRY_DELAYS = delays
        if old is None:
            os.environ.pop("EOS_PLATFORM", None)
        else:
            os.environ["EOS_PLATFORM"] = old


def platforms():
    """Every case runs on each platform path this host can exercise: the real one, and on a POSIX host the
    Windows paths against emulated kernel32 / msvcrt. On Windows the real Windows paths run."""
    return ["windows"] if os.name == "nt" else ["posix", "windows-sim"]


def run_all(require_parquet=False):
    global CODEC
    try:
        import pyarrow  # noqa: F401
        codecs = ["jsonl", "parquet"]
    except ImportError:
        codecs = ["jsonl"]
    fails, runs = 0, 0
    saved = os.environ.get("EOS_PLATFORM")
    for plat in platforms():
        os.environ["EOS_PLATFORM"] = plat
        fsio.os = _WindowsOs(os) if plat == "windows-sim" else os
        try:
            for CODEC in codecs:
                print(f"--- platform: {plat}, codec: {CODEC}")
                for t in TESTS:
                    runs += 1
                    try:
                        n_before = len(NOT_RUN)
                        t()
                        print(f"{'SKIP' if len(NOT_RUN) > n_before else 'ok  '}  {t.__name__}")
                    except Exception:
                        fails += 1
                        print(f"FAIL  {t.__name__} [{plat}, {CODEC}]")
                        traceback.print_exc()
        finally:
            fsio.os = os
            if saved is None:
                os.environ.pop("EOS_PLATFORM", None)
            else:
                os.environ["EOS_PLATFORM"] = saved
    CODEC = "jsonl"
    print(f"\n{runs - fails}/{runs} passed ({len(TESTS)} cases x {len(codecs)} codec(s): {', '.join(codecs)} x "
          f"platform path(s): {', '.join(platforms())})")
    if "parquet" not in codecs:
        print("NOT RUN: every case on the parquet codec (pyarrow not installed)")
        if require_parquet:
            fails += 1
    return fails


def test_m2_suite():
    """pytest entry point: every M2 case on every available codec (r5.4's decorator was collected as a test and
    no M2 case ran under pytest)."""
    assert run_all() == 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):   # UTF-8 output whatever the console or pipe (Windows defaults to cp1252)
        _s.reconfigure(encoding="utf-8")
    sys.exit(1 if run_all("--require-parquet" in sys.argv) else 0)
