"""Partitioned warehouse (Document 02 s12) with batch transactions.

One logical write (for example, one source file's price rows, conflicts, coverage and ingestion-log
entry) is ONE batch, and a batch is all-or-nothing:

  1. stage   every part file is written to its partition (temp file, fsync, rename). Staged parts are
             invisible: no manifest lists them.
  2. commit  one batch record _batches/<id>.json, written atomically, lists every part. THIS is the
             commit point. A crash before it leaves only orphan files; a crash after it is rolled forward.
  3. apply   each partition's _manifest.json gains the batch's parts (idempotent), then the marker
             _applied/<id> is written.

Readers refuse to read while any committed batch is unapplied, so no one ever sees half a batch. The
next writer recovers (re-applies) pending batches before doing anything else. Every manifest entry
names its batch, and a part whose batch has no commit record is refused.

All writes happen inside Warehouse.writer(): one exclusive lock held for the whole read-latest ->
allocate-version -> commit sequence, so two ingestions cannot allocate the same version. A duplicate
(source observation identity, trade_date, version_no) is checked at read time and is a hard IntegrityError.

Readers never glob: they read manifests, or a snapshot of manifests taken earlier, and verify every
part's hash.

Codecs: 'parquet' (production; needs pyarrow) and 'jsonl' (tests and environments without pyarrow).
Both are driven by the same table schemas below.
"""
import contextlib
import datetime as dt
import decimal
import hashlib
import json
import os
import socket
import threading
import uuid

from . import fsio

D4 = decimal.Decimal("0.0001")

TABLES = {
    "price_observation": {
        "source_instrument_id": "str", "isin": "str", "trade_date": "date", "version_no": "int", "series": "str", "symbol": "str",
        "open": "dec", "high": "dec", "low": "dec", "close": "dec", "prev_close": "dec",
        "volume": "int", "traded_value": "dec", "num_trades": "int",
        "source_id": "str", "source_format": "str", "file_sha256": "str",
        "source_published_at": "ts", "received_at": "ts", "effective_from": "ts",
        "system_available_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "domain": "str"},
    "delivery_observation": {
        "source_instrument_id": "str", "isin": "str", "trade_date": "date", "version_no": "int", "series": "str", "symbol": "str",
        "delivery_qty": "int", "traded_qty_reported": "int", "delivery_pct_reported": "dec",
        "source_id": "str", "source_format": "str", "file_sha256": "str",
        "source_published_at": "ts", "received_at": "ts", "effective_from": "ts",
        "system_available_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "domain": "str"},
    # r5.9: independent full-bhavcopy delivery evidence used to cross-check the primary MTO feed.
    "delivery_crosscheck_observation": {
        "source_instrument_id": "str", "isin": "str", "trade_date": "date", "version_no": "int", "series": "str", "symbol": "str",
        "delivery_available": "bool", "delivery_qty": "int", "traded_qty_reported": "int", "delivery_pct_reported": "dec",
        "source_id": "str", "source_format": "str", "file_sha256": "str",
        "source_published_at": "ts", "received_at": "ts", "effective_from": "ts",
        "system_available_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "domain": "str"},
    "source_coverage": {
        "source_id": "str", "trade_date": "date", "complete": "bool", "rows": "int", "file_sha256": "str",
        "usable_from": "ts", "received_at": "ts", "domain": "str"},
    "ingestion_log": {
        "file_sha256": "str", "source_id": "str", "trade_date": "date", "received_at": "ts",
        "rows_new": "int", "rows_changed": "int", "rows_unchanged": "int", "mode": "str"},
    "data_conflict": {
        "table_name": "str", "source_instrument_id": "str", "isin": "str", "series": "str", "trade_date": "date", "kind": "str", "detail": "str",
        "file_sha256": "str", "logged_at": "ts"},
    # r5.5 (audit C5): a defective row is quarantined, not allowed to reject the whole file
    "row_quarantine": {
        "table_name": "str", "trade_date": "date", "source_instrument_id": "str", "isin": "str", "symbol": "str", "series": "str",
        "reason": "str", "detail": "str", "file_sha256": "str", "logged_at": "ts"},
    # r5.8: explicit withdrawal of a source observation by a later complete-file reissue.
    "observation_tombstone": {
        "table_name": "str", "source_instrument_id": "str", "isin": "str", "series": "str",
        "trade_date": "date", "version_no": "int", "source_id": "str", "file_sha256": "str",
        "received_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "reason": "str", "domain": "str"},
    # r5.8: versioned NSE MII security-master observations.  effective_session is deliberately nullable;
    # an unresolved master version is stored as evidence but cannot silently govern a historical session.
    "security_master_observation": {
        "source_instrument_id": "str", "master_file_date": "date", "version_no": "int",
        "symbol": "str", "series": "str", "name": "str", "isin": "str",
        "instrument_type": "int", "normal_market_status": "int", "normal_market_eligibility": "int",
        "price_range_text": "str", "price_range_type": "str", "max_price": "dec", "min_price": "dec", "tick_size": "dec",
        "delete_flag": "str", "is_dummy": "bool", "status_code_known": "bool",
        "security_class": "str", "market_eligible": "bool",
        "effective_session": "date", "effective_session_basis": "str",
        "source_id": "str", "source_format": "str", "file_sha256": "str",
        "source_published_at": "ts", "received_at": "ts", "effective_from": "ts",
        "system_available_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "domain": "str"},
    # r5.7: a receipt is committed as soon as landed bytes are durable, before parsing starts.
    "raw_file": {
        "source_id": "str", "file_sha256": "str", "original_name": "str", "source_url": "str",
        "retrieved_at": "ts", "received_at": "ts", "size_bytes": "int", "landed_path": "str",
        "acquisition_method": "str"},
    # Parsing is a separate transaction. Structural/parser rejection is evidence, not grounds to erase receipt.
    "raw_parse_event": {
        "source_id": "str", "file_sha256": "str", "received_at": "ts", "parsed_at": "ts",
        "status": "str", "source_format": "str", "trade_date": "date", "parse_error": "str"},
}


class StoreError(Exception):
    pass


class IntegrityError(StoreError):
    """The warehouse contradicts its own invariants (duplicate identity, uncommitted part listed)."""


class SimulatedCrash(RuntimeError):
    """Test hook only."""


# ------------------------------------------------------------------ pre-write validation (every codec)
def validate(table, rows):
    """One check for every codec (audit B4): r5.4 refused naive timestamps only inside the JSONL encoder, so the
    production Parquet codec stored a naive 22:30 IST as 22:30 UTC. Unknown columns are refused rather than
    silently dropped; floats are refused where the schema says decimal; bools are refused where it says int."""
    cols = TABLES[table]
    for r in rows:
        extra = set(r) - set(cols)
        if extra:
            raise StoreError(f"{table}: unknown column(s) {sorted(extra)}")
        for k, t in cols.items():
            v = r.get(k)
            if v is None:
                continue
            ok = {"str": isinstance(v, str),
                  "int": isinstance(v, int) and not isinstance(v, bool),
                  "bool": isinstance(v, bool),
                  "dec": isinstance(v, (decimal.Decimal, int)) and not isinstance(v, bool),
                  "date": isinstance(v, dt.date) and not isinstance(v, dt.datetime),
                  "ts": isinstance(v, dt.datetime)}[t]
            if not ok:
                raise StoreError(f"{table}.{k}: {type(v).__name__} is not a valid {t}")
            if t == "ts" and v.tzinfo is None:
                raise StoreError("naive timestamp refused: all timestamps are UTC-aware")


# ------------------------------------------------------------------ value encoding
def _enc(v, t):
    if v is None:
        return None
    if t == "dec":
        return str(v)
    if t == "date":
        return v.isoformat()
    if t == "ts":
        return v.astimezone(dt.timezone.utc).isoformat()
    return v


def _dec(v, t):
    if v is None:
        return None
    if t == "dec":
        return decimal.Decimal(v)
    if t == "date":
        return dt.date.fromisoformat(v)
    if t == "ts":
        return dt.datetime.fromisoformat(v)
    return v


class JsonlCodec:
    ext = "jsonl"

    def dumps(self, table, rows):
        cols = TABLES[table]
        return "".join(json.dumps({k: _enc(r.get(k), t) for k, t in cols.items()}, sort_keys=True) + "\n"
                       for r in rows).encode()

    def loads(self, table, data):
        cols = TABLES[table]
        return [{k: _dec(o.get(k), t) for k, t in cols.items()} for o in map(json.loads, data.decode().splitlines())]


class ParquetCodec:
    ext = "parquet"

    def __init__(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError as e:  # never fall back silently
            raise StoreError("parquet codec requires pyarrow; install it or choose codec='jsonl' explicitly") from e

    def _schema(self, table):
        import pyarrow as pa
        m = {"str": pa.string(), "int": pa.int64(), "bool": pa.bool_(), "date": pa.date32(),
             "dec": pa.decimal128(20, 4), "ts": pa.timestamp("us", tz="UTC")}
        return pa.schema([(k, m[t]) for k, t in TABLES[table].items()])

    def dumps(self, table, rows):
        import io
        import pyarrow as pa
        import pyarrow.parquet as pq
        cols = TABLES[table]
        conv = lambda v, t: v.astimezone(dt.timezone.utc) if (t == "ts" and v is not None) else \
            (decimal.Decimal(v) if (t == "dec" and v is not None) else v)  # noqa: E731
        tbl = pa.Table.from_pylist([{k: conv(r.get(k), t) for k, t in cols.items()} for r in rows],
                                   schema=self._schema(table))
        buf = io.BytesIO()
        pq.write_table(tbl, buf)
        return buf.getvalue()

    def loads(self, table, data):
        import io
        import pyarrow.parquet as pq
        rows = pq.read_table(io.BytesIO(data)).to_pylist()
        for r in rows:
            for k, t in TABLES[table].items():
                if t == "ts" and r.get(k) is not None and r[k].tzinfo is None:
                    r[k] = r[k].replace(tzinfo=dt.timezone.utc)
        return rows


def codec(name):
    return {"jsonl": JsonlCodec, "parquet": ParquetCodec}[name]()


# ------------------------------------------------------------------ durable writes
def _atomic_write(path, data):
    """Temp file, flush to disk, then the platform's durable replace (eos/fsio.py): directory fsync on POSIX,
    MoveFileExW write-through on Windows. r5.5 fsync-ed the directory everywhere, which cannot work on Windows."""
    fsio.write_durable(path, data, f".tmp-{uuid.uuid4().hex}")


class Batch:
    def __init__(self, wh):
        self.wh, self.entries, self.done = wh, [], False
        self.id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:8]

    def add(self, table, key, rows):
        if self.done:
            raise StoreError("batch already committed")
        if not rows:
            return None
        pdir = self.wh.pdir(table, key)
        validate(table, rows)
        os.makedirs(pdir, exist_ok=True)
        data = self.wh.codec.dumps(table, rows)
        sha = hashlib.sha256(data).hexdigest()
        name = f"part-{self.id}-{len(self.entries):03d}-{sha[:12]}.{self.wh.codec.ext}"
        _atomic_write(os.path.join(pdir, name), data)
        self.entries.append({"table": table, "key": key, "file": name, "sha256": sha, "rows": len(rows)})
        return name

    def commit(self, _crash_at=None):
        """_crash_at: test hook - 'before_record', 'after_record', 'mid_apply', 'before_marker'."""
        self.done = True
        if not self.entries:
            return None
        if _crash_at == "before_record":
            raise SimulatedCrash(_crash_at)
        _atomic_write(os.path.join(self.wh.root, "_batches", f"{self.id}.json"),
                      json.dumps({"batch": self.id, "parts": self.entries}, indent=1).encode())
        if _crash_at == "after_record":
            raise SimulatedCrash(_crash_at)
        self.wh._apply(self.id, self.entries, _crash_at)
        return self.id


class Warehouse:
    def __init__(self, root, codec_name="parquet", create=True):
        """create=False opens an existing warehouse only (r5.10: a report given a mistyped path must fail, not
        silently create an empty warehouse and report every source missing)."""
        self.root = root
        self.codec = codec(codec_name)
        self._held = 0          # re-entrancy depth, valid only for the owning thread
        self._owner = None
        self._lock_fd = None
        if not create:
            missing = [d for d in ("_batches", "_applied") if not os.path.isdir(os.path.join(root, d))]
            if missing:
                raise StoreError(f"{root} is not a warehouse (no {', '.join(missing)}); refusing to create one here")
            return
        for d in ("", "_batches", "_applied"):
            os.makedirs(os.path.join(root, d), exist_ok=True)

    # ---- partitions
    def pdir(self, table, key):
        if table not in TABLES:
            raise StoreError(f"unknown table {table}")
        return os.path.join(self.root, table, f"p={key}")

    def _manifest(self, pdir):
        p = os.path.join(pdir, "_manifest.json")
        return json.loads(fsio.read_bytes(p).decode("utf-8")) if os.path.exists(p) else {"parts": []}

    def partitions(self, table):
        base = os.path.join(self.root, table)
        if not os.path.isdir(base):
            return []
        return sorted(d[2:] for d in os.listdir(base)
                      if d.startswith("p=") and self._manifest(os.path.join(base, d))["parts"])

    # ---- the writer: one lock for the whole logical operation
    @contextlib.contextmanager
    def writer(self):
        """An operating-system lock (eos/fsio.py), released by the OS if this process dies, so a crash never
        leaves a stale lock (r5.5's O_EXCL file did). Re-entrant for the owning thread only."""
        lock = os.path.join(self.root, ".writer.lock")
        me = threading.get_ident()
        if self._held and self._owner != me:
            # re-entry is per THREAD: another thread sharing this object must take the lock like anyone else
            raise StoreError(f"another writer holds {lock}")
        if self._held == 0:
            try:
                self._lock_fd = fsio.lock_exclusive(lock)
            except fsio.LockHeld:
                raise StoreError(f"another writer holds {lock} (the lock is released automatically when "
                                 f"that process exits; see {os.path.join(self.root, '.writer.owner')})") from None
            self._owner = me
            try:   # diagnostics only; the OS lock is the authority
                with open(os.path.join(self.root, ".writer.owner"), "w", encoding="utf-8") as f:
                    f.write(f"pid {os.getpid()}\nhost {socket.gethostname()}\n"
                            f"since {dt.datetime.now(dt.timezone.utc).isoformat()}\n")
            except OSError:
                pass
        self._held += 1
        try:
            if self._held == 1:
                self.recover()
            yield self
        finally:
            self._held -= 1
            if self._held == 0:
                self._owner = None
                fd, self._lock_fd = self._lock_fd, None
                fsio.unlock(fd)

    # ---- raw landing (r5.6): the exact bytes of every source file, content-addressed and write-once
    def land(self, source_id, path):
        """Copy a source file into _raw/<source_id>/<sha256><ext> and return (sha256, landed_path, size).
        Write-once: landing the same content again is a no-op; a landed file whose bytes no longer match
        its name is an IntegrityError. Parsing then reads the landed copy, never the original, so a later
        change to the download folder cannot change what was ingested. Needs the writer lock."""
        if not self._held or self._owner != threading.get_ident():
            raise StoreError("land() needs Warehouse.writer()")
        if not source_id.replace("_", "").isalnum():
            raise StoreError(f"source_id {source_id!r}: letters, digits and underscores only")
        data = fsio.read_bytes(path)
        sha = hashlib.sha256(data).hexdigest()
        ext = "".join(c for c in os.path.splitext(path)[1].lower() if c.isalnum() or c == ".")[:10]
        rel = f"_raw/{source_id}/{sha}{ext}"
        dest = os.path.join(self.root, *rel.split("/"))
        if os.path.exists(dest):
            if hashlib.sha256(fsio.read_bytes(dest)).hexdigest() != sha:
                raise IntegrityError(f"{rel}: landed bytes no longer match their hash")
            return sha, rel, len(data)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _atomic_write(dest, data)
        os.chmod(dest, 0o444)          # read-only attribute on Windows too
        return sha, rel, len(data)

    def raw_path(self, landed_path):
        return os.path.join(self.root, *landed_path.split("/"))

    def verify_raw_integrity(self, receipts=None):
        """Re-hash landed raw blobs against durable receipts; raise on missing, moved or changed evidence.

        Ordinary metadata reads need not pay this cost. Snapshot creation does, because a snapshot is an assertion
        that the evidence set is intact and suitable for replay/backtest evidence freezing.
        """
        receipts = self.read("raw_file") if receipts is None else receipts
        base = os.path.realpath(os.path.join(self.root, "_raw"))
        checked = 0
        for r in receipts:
            rel = r["landed_path"]
            path = os.path.realpath(self.raw_path(rel))
            try:
                inside = os.path.commonpath([base, path]) == base
            except ValueError:
                inside = False
            if not inside:
                raise IntegrityError(f"raw_file {r['file_sha256'][:12]}: landed_path {rel!r} is outside _raw")
            if not os.path.isfile(path):
                raise IntegrityError(f"raw_file {r['file_sha256'][:12]}: landed blob {rel} is missing")
            data = fsio.read_bytes(path)
            got = hashlib.sha256(data).hexdigest()
            if got != r["file_sha256"]:
                raise IntegrityError(f"raw_file {r['file_sha256'][:12]}: landed blob {rel} hashes to {got}")
            if len(data) != r["size_bytes"]:
                raise IntegrityError(f"raw_file {r['file_sha256'][:12]}: landed blob {rel} size {len(data)} != receipt {r['size_bytes']}")
            checked += 1
        return checked

    def batch(self):
        if not self._held or self._owner != threading.get_ident():
            raise StoreError("writes need Warehouse.writer(): the lock must span read, version and commit")
        return Batch(self)

    def append(self, table, key, rows, _crash_at=None):
        """One-table convenience: a batch of one part."""
        with self.writer():
            b = self.batch()
            name = b.add(table, key, rows)
            b.commit(_crash_at)
            return name

    # ---- commit bookkeeping
    def _committed(self):
        return {f[:-5] for f in os.listdir(os.path.join(self.root, "_batches")) if f.endswith(".json")}

    def _applied(self):
        return set(os.listdir(os.path.join(self.root, "_applied")))

    def pending(self):
        return sorted(self._committed() - self._applied())

    def _apply(self, batch_id, entries, _crash_at=None):
        for n, e in enumerate(entries):
            pdir = self.pdir(e["table"], e["key"])
            man = self._manifest(pdir)
            if not any(p["file"] == e["file"] for p in man["parts"]):
                man["parts"].append({"file": e["file"], "sha256": e["sha256"], "rows": e["rows"], "batch": batch_id})
                _atomic_write(os.path.join(pdir, "_manifest.json"), json.dumps(man, indent=1).encode())
            if _crash_at == "mid_apply" and n == 0 and len(entries) > 1:
                raise SimulatedCrash(_crash_at)
        if _crash_at == "before_marker":
            raise SimulatedCrash(_crash_at)
        _atomic_write(os.path.join(self.root, "_applied", batch_id), b"")

    def recover(self, _crash_at=None):
        """Roll forward every committed batch that is not yet applied. Idempotent; needs the lock."""
        if not self._held or self._owner != threading.get_ident():
            raise StoreError("recover() needs Warehouse.writer()")
        done = []
        for bid in self.pending():
            rec = json.loads(fsio.read_bytes(os.path.join(self.root, "_batches", f"{bid}.json")).decode("utf-8"))
            for e in rec["parts"]:
                if not os.path.exists(os.path.join(self.pdir(e["table"], e["key"]), e["file"])):
                    raise IntegrityError(f"committed batch {bid} names a missing part {e['file']}")
            self._apply(bid, rec["parts"], _crash_at)
            done.append(bid)
        return done

    def _consistent(self):
        p = self.pending()
        if p:
            raise StoreError(f"{len(p)} committed batch(es) not yet applied ({p[0]}...): open a writer to recover "
                             f"before reading")
        return self._committed()

    # ---- reads
    def snapshot(self):
        """Every partition's listed parts, frozen. Reads under a snapshot never see later parts.

        Snapshot creation is also an integrity assertion, so every durable raw receipt is re-hashed first.
        """
        self._consistent()
        self.verify_raw_integrity()
        snap = {}
        for t in TABLES:
            for k in self.partitions(t):
                parts = self._manifest(self.pdir(t, k))["parts"]
                if parts:
                    snap[f"{t}/{k}"] = [dict(p) for p in parts]
        body = json.dumps(snap, sort_keys=True).encode()
        return {"parts": snap, "snapshot_sha256": hashlib.sha256(body).hexdigest()}

    def read(self, table, keys=None, snapshot=None):
        committed = self._consistent()
        keys = self.partitions(table) if keys is None else keys
        out = []
        for k in keys:
            pdir = self.pdir(table, k)
            parts = snapshot["parts"].get(f"{table}/{k}", []) if snapshot is not None else self._manifest(pdir)["parts"]
            for p in parts:
                if p.get("batch") not in committed:
                    raise IntegrityError(f"{table}/{k}/{p['file']} is listed but its batch {p.get('batch')} "
                                         f"has no commit record")
                data = fsio.read_bytes(os.path.join(pdir, p["file"]))
                if hashlib.sha256(data).hexdigest() != p["sha256"]:
                    raise StoreError(f"{table}/{k}/{p['file']}: content does not match its manifest hash")
                out.extend(self.codec.loads(table, data))
        return out

    def orphans(self):
        """Part files on disk that no manifest lists: debris of batches that never committed."""
        found = []
        for t in TABLES:
            base = os.path.join(self.root, t)
            if not os.path.isdir(base):
                continue
            for d in os.listdir(base):
                pdir = os.path.join(base, d)
                listed = {p["file"] for p in self._manifest(pdir)["parts"]} | {"_manifest.json"}
                found += [os.path.join(pdir, f) for f in os.listdir(pdir) if f not in listed]
        return found

    def remove_orphans(self):
        with self.writer():          # recovery runs first, so committed-but-unapplied parts are listed
            for f in self.orphans():
                os.remove(f)
