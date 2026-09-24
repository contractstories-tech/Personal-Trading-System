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
(isin, trade_date, version_no) is still checked at read time and is a hard IntegrityError.

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
import threading
import uuid

D4 = decimal.Decimal("0.0001")

TABLES = {
    "price_observation": {
        "isin": "str", "trade_date": "date", "version_no": "int", "series": "str", "symbol": "str",
        "open": "dec", "high": "dec", "low": "dec", "close": "dec", "prev_close": "dec",
        "volume": "int", "traded_value": "dec", "num_trades": "int",
        "source_id": "str", "source_format": "str", "file_sha256": "str",
        "source_published_at": "ts", "received_at": "ts", "effective_from": "ts",
        "system_available_at": "ts", "usable_from": "ts", "availability_inferred": "bool",
        "supersedes_version": "int", "domain": "str"},
    "delivery_observation": {
        "isin": "str", "trade_date": "date", "version_no": "int", "series": "str", "symbol": "str",
        "delivery_qty": "int", "traded_qty_reported": "int",
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
        "table_name": "str", "isin": "str", "trade_date": "date", "kind": "str", "detail": "str",
        "file_sha256": "str", "logged_at": "ts"},
}


class StoreError(Exception):
    pass


class IntegrityError(StoreError):
    """The warehouse contradicts its own invariants (duplicate identity, uncommitted part listed)."""


class SimulatedCrash(RuntimeError):
    """Test hook only."""


# ------------------------------------------------------------------ value encoding
def _enc(v, t):
    if v is None:
        return None
    if t == "dec":
        return str(v)
    if t == "date":
        return v.isoformat()
    if t == "ts":
        if v.tzinfo is None:
            raise StoreError("naive timestamp refused: all timestamps are UTC-aware")
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
        tbl = pa.Table.from_pylist([{k: r.get(k) for k in cols} for r in rows], schema=self._schema(table))
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
def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(path, data):
    d = os.path.dirname(path)
    tmp = os.path.join(d, f".tmp-{uuid.uuid4().hex}")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _fsync_dir(d)


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
    def __init__(self, root, codec_name="parquet"):
        self.root = root
        self.codec = codec(codec_name)
        self._held = 0          # re-entrancy depth, valid only for the owning thread
        self._owner = None
        for d in ("", "_batches", "_applied"):
            os.makedirs(os.path.join(root, d), exist_ok=True)

    # ---- partitions
    def pdir(self, table, key):
        if table not in TABLES:
            raise StoreError(f"unknown table {table}")
        return os.path.join(self.root, table, f"p={key}")

    def _manifest(self, pdir):
        p = os.path.join(pdir, "_manifest.json")
        return json.load(open(p)) if os.path.exists(p) else {"parts": []}

    def partitions(self, table):
        base = os.path.join(self.root, table)
        if not os.path.isdir(base):
            return []
        return sorted(d[2:] for d in os.listdir(base)
                      if d.startswith("p=") and self._manifest(os.path.join(base, d))["parts"])

    # ---- the writer: one lock for the whole logical operation
    @contextlib.contextmanager
    def writer(self):
        lock = os.path.join(self.root, ".writer.lock")
        me = threading.get_ident()
        if self._held and self._owner != me:
            # re-entry is per THREAD: another thread sharing this object must take the lock like anyone else
            raise StoreError(f"another writer holds {lock}; remove it only if no ingestion is running")
        if self._held == 0:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise StoreError(f"another writer holds {lock}; remove it only if no ingestion is running")
            os.write(fd, f"pid {os.getpid()}\n".encode())
            os.close(fd)
            self._owner = me
        self._held += 1
        try:
            if self._held == 1:
                self.recover()
            yield self
        finally:
            self._held -= 1
            if self._held == 0:
                self._owner = None
                os.remove(lock)

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
            rec = json.load(open(os.path.join(self.root, "_batches", f"{bid}.json")))
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
        """Every partition's listed parts, frozen. Reads under a snapshot never see later parts."""
        self._consistent()
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
                data = open(os.path.join(pdir, p["file"]), "rb").read()
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
