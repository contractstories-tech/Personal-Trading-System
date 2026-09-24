#!/usr/bin/env python3
"""Stage 0 slice 1 - M2 price ingestion, the PIT primitive, the canary and the warehouse.

    python3 tests/test_m2.py                    exit 0 = all pass (Parquet round-trip reported as NOT RUN
                                                if pyarrow is absent)
    python3 tests/test_m2.py --require-parquet  also fails if the Parquet codec could not run
                                                (use this on the machine that holds the warehouse)

Every test runs once per available codec (r5.5, audit B4): JSONL always, Parquet whenever pyarrow is installed.
r5.4 exercised Parquet in one test only, which is how a store invariant held on JSONL and not on Parquet.
"""
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
from eos import canary, pit, source_policy, store  # noqa: E402
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
        shutil.rmtree(self.dir)


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
    G = yaml.safe_load(open(os.path.join(KIT, "golden", "golden_cases.yaml")))
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
        assert r1 == r2 and len(r1) == 3
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
        open(p, "w").write("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,ISIN\nA,EQ,1,1,1,1,INE000A01011\n")
        raises(parsers.FormatError, parsers.parse_bhavcopy, parsers.read_bytes(p))
        open(p, "w").write("hello\n")
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
        txt = open(p).read().replace("16-SEP-2026", "17-SEP-2026", 1)
        open(p, "w").write(txt)
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
            p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml")))
            p["sources"][sid]["availability"].update(inferred_published_time_ist="22:45", policy_lag_minutes=15)
            path = e.f(f"sp-{sid}.yaml")
            yaml.safe_dump(p, open(path, "w"))
            raises(source_policy.PolicyError, source_policy.load, path)
        source_policy.load()  # the shipped policy loads


@case
def availability_is_source_specific():
    """B9: the delivery file's inferred time is its own, not the bhavcopy's."""
    with Env() as e:
        p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml")))
        p["sources"]["nse_cm_delivery"]["availability"]["inferred_published_time_ist"] = "22:50"
        path = e.f("sp.yaml")
        yaml.safe_dump(p, open(path, "w"))
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
def same_content_in_other_format_writes_no_version():
    with Env() as e:
        ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))
        n = len(e.wh.read("price_observation"))
        res = ingest.ingest_bhavcopy(e.wh, F.udiff(e.f("b.csv"), D1), recv(D2))
        assert res["rows_unchanged"] == 3 and res["rows_changed"] == 0
        assert len(e.wh.read("price_observation")) == n


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


@case
def reissue_missing_a_security_logs_conflict_and_keeps_prior():
    with Env() as e:
        load_days(e, [D1], deliver=False)
        rows = F.bars(D1)
        rows[0]["c"] = "118.00"
        res = ingest.ingest_bhavcopy(e.wh, F.legacy(e.f("r.csv"), D1, rows[:2]), recv(D2))
        assert [c["isin"] for c in res["conflicts"]] == [C]
        assert C in {x["isin"] for x in resolve.history_known_as_of(e.wh, D3)}
        assert len(e.wh.read("data_conflict")) == 1


# ------------------------------------------------------------------ quality checks: nothing written on reject
def _unchanged(e, fn):
    before = e.wh.snapshot()["snapshot_sha256"]
    fn()
    assert e.wh.snapshot()["snapshot_sha256"] == before, "a rejected file changed the warehouse"


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
def _state(wh):
    """Everything a reader can observe, normalised (part names differ between warehouses)."""
    out = {}
    for t in store.TABLES:
        rows = wh.read(t)
        out[t] = sorted(repr(sorted((k, v) for k, v in r.items() if k not in ("logged_at",))) for r in rows)
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
            assert not os.path.exists(os.path.join(e.wh.root, ".writer.lock")), point
            if point == "before_record":
                assert _state(e.wh) == before, point            # nothing became visible
                assert e.wh.orphans(), point                     # only unreferenced debris
                res = ingest.ingest_bhavcopy(e.wh, corr, at_ist(D2, "09:00"))
                assert not res["noop"] and res["rows_changed"] == 1, point
            else:
                raises(store.StoreError, e.wh.read, "price_observation")   # half a batch is never readable
                with e.wh.writer():
                    pass                                          # any writer rolls the batch forward
                assert ingest.ingest_bhavcopy(e.wh, corr, at_ist(D2, "09:30"))["noop"], point
            e.wh.remove_orphans()
            assert _state(e.wh) == after, point
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
        man = json.load(open(os.path.join(pdir, "_manifest.json")))
        man["parts"][0]["batch"] = "never-committed"
        json.dump(man, open(os.path.join(pdir, "_manifest.json"), "w"))
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
        with open(os.path.join(pdir, part), "a") as f:
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


@case
def concurrent_writer_refused():
    with Env() as e:
        open(os.path.join(e.wh.root, ".writer.lock"), "w").close()
        raises(store.StoreError, ingest.ingest_bhavcopy, e.wh, F.legacy(e.f("a.csv"), D1), recv(D1))


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
        p = yaml.safe_load(open(os.path.join(KIT, "policies", "source_policy.yaml")))
        p["backfill"]["live_capture_start"] = D2.isoformat()
        path = e.f("sp.yaml")
        yaml.safe_dump(p, open(path, "w"))
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
        assert seen == [("ingestion_log", [D2.isoformat()])], seen


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


def run_all(require_parquet=False):
    global CODEC
    try:
        import pyarrow  # noqa: F401
        codecs = ["jsonl", "parquet"]
    except ImportError:
        codecs = ["jsonl"]
    fails, runs = 0, 0
    for CODEC in codecs:
        print(f"--- codec: {CODEC}")
        for t in TESTS:
            runs += 1
            try:
                n_before = len(NOT_RUN)
                t()
                print(f"{'SKIP' if len(NOT_RUN) > n_before else 'ok  '}  {t.__name__}")
            except Exception:
                fails += 1
                print(f"FAIL  {t.__name__} [{CODEC}]")
                traceback.print_exc()
    CODEC = "jsonl"
    print(f"\n{runs - fails}/{runs} passed ({len(TESTS)} cases x {len(codecs)} codec(s): {', '.join(codecs)})")
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
    sys.exit(1 if run_all("--require-parquet" in sys.argv) else 0)
