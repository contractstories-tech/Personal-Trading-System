"""Time conventions (Document 02 s1, s3): timestamps are UTC-aware; session logic is IST (fixed +05:30)."""
import datetime as dt
import os
import yaml

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
UTC = dt.timezone.utc
FAR_FUTURE = dt.datetime(9999, 12, 31, tzinfo=UTC)
KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def at_ist(day, hhmm):
    """Aware UTC datetime for HH:MM IST on a trading date."""
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=IST).astimezone(UTC)


def parse_ts(s):
    """ISO timestamp -> aware UTC. A timestamp without an offset is REFUSED: silently assuming a zone can
    move an event by hours (review H8). Callers holding naive IST values convert them explicitly with ist()."""
    t = s if isinstance(s, dt.datetime) else dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError(f"timestamp without a UTC offset refused: {s!r}")
    return t.astimezone(UTC)


def ist(s):
    """Explicit conversion of a naive IST wall-clock timestamp (e.g. golden fixtures) to aware UTC."""
    t = s if isinstance(s, dt.datetime) else dt.datetime.fromisoformat(s)
    if t.tzinfo is not None:
        raise ValueError(f"ist() takes naive IST wall-clock time only: {s!r}")
    return t.replace(tzinfo=IST).astimezone(UTC)


def load_registry():
    return yaml.safe_load(open(os.path.join(KIT, "registry.yaml"), encoding="utf-8"))


def run_cutoffs(day, registry=None):
    """Both cutoffs of the run for trading date `day` (Document 02 s3; registry cutoff_policy)."""
    reg = registry or load_registry()
    return {dom: at_ist(day, spec["time_ist"]) for dom, spec in reg["cutoff_policy"].items()}
