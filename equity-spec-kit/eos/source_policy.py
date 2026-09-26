"""Loads policies/source_policy.yaml and refuses a policy that breaks its own invariants."""
import datetime as dt
import os
import yaml
from .timeutil import KIT, at_ist, load_registry


class PolicyError(Exception):
    pass


def load(path=None, registry=None):
    p = yaml.safe_load(open(path or os.path.join(KIT, "policies", "source_policy.yaml"), encoding="utf-8"))
    reg = registry or load_registry()
    day = dt.date(2020, 1, 1)
    for sid, s in p["sources"].items():
        if s["domain"] not in reg["cutoff_policy"]:
            raise PolicyError(f"source {sid}: unknown domain {s['domain']}")
        a = s.get("availability")
        if a is None:
            raise PolicyError(f"source {sid}: no availability rule")
        if a.get("inferred_basis") not in ("unverified", "measured"):
            raise PolicyError(f"source {sid}: inferred_basis must be 'unverified' or 'measured'")
        inferred = at_ist(day, a["inferred_published_time_ist"]) + dt.timedelta(minutes=a["policy_lag_minutes"])
        cutoff = at_ist(day, reg["cutoff_policy"][s["domain"]]["time_ist"])
        if inferred >= cutoff:
            raise PolicyError(f"source {sid}: inferred availability is not before the {s['domain']} cutoff; "
                              f"every backfilled row would miss its own day")
    q = p["quality"]
    if not (0 < q["row_count_kill_ratio"] < 1 - q["row_count_warn_band"] < 1):
        raise PolicyError("row-count kill ratio must sit below the warning band")
    if not (0 <= q.get("max_quarantine_share", -1) < 0.5):
        raise PolicyError("quality.max_quarantine_share must be in [0, 0.5)")
    if not (0 <= q.get("delivery_pct_tolerance_pp", -1) <= 1):
        raise PolicyError("quality.delivery_pct_tolerance_pp must be in [0, 1]")
    b = p.get("backfill")
    if not isinstance(b, dict) or not isinstance(b.get("min_age_days"), int) or b["min_age_days"] < 1:
        raise PolicyError("backfill.min_age_days must be an integer >= 1")
    start = b.get("live_capture_start")
    if start is not None:
        try:
            dt.date.fromisoformat(str(start))
        except ValueError:
            raise PolicyError(f"backfill.live_capture_start {start!r} is not a date")
    return p
