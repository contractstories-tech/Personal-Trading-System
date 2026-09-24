"""Loads policies/source_policy.yaml and refuses a policy that breaks its own invariants."""
import datetime as dt
import os
import yaml
from .timeutil import KIT, at_ist, load_registry


class PolicyError(Exception):
    pass


def load(path=None, registry=None):
    p = yaml.safe_load(open(path or os.path.join(KIT, "policies", "source_policy.yaml")))
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
    return p
