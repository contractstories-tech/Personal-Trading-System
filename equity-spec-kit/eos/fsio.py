"""Platform file primitives for the warehouse: durable replace, exclusive writer lock, retried reads (r5.6).

r5.5 made a rename durable by fsync-ing its directory, which works only on POSIX: Windows cannot open a
directory with os.open, so every warehouse write failed there (review, Windows defect 1). Each platform now
uses its own durable primitive:

  posix    os.replace(tmp, dst), then fsync the directory so the new directory entry survives power loss.
  windows  MoveFileExW(tmp, dst, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH): the call returns only
           after the move is flushed to disk. No directory is ever opened. A sharing violation (another
           process, typically an antivirus or indexer, has the file open) is retried with bounded backoff.

The writer lock is an operating-system lock, released by the OS when the holding process dies, so a hard
crash can never leave a stale lock that blocks every later ingestion (r5.5 used an O_EXCL file that
survived a crash):

  posix    fcntl.flock(fd, LOCK_EX | LOCK_NB) on the lock file.
  windows  msvcrt.locking(fd, LK_NBLCK, 1) on byte 0 of the lock file.

The lock file itself is never deleted: deleting it would let a second writer lock a new file while the
first still holds the old one.

EOS_PLATFORM selects the implementation: unset means the running OS; 'windows-sim' runs the Windows code
paths on a POSIX host against emulated kernel32 and msvcrt that behave like Windows where it matters (a
directory cannot be opened; a locked byte range is exclusive per handle; a sharing violation can be
injected). It is how the Windows paths are exercised in CI here. It is NOT evidence that they run on
Windows: only a run on Windows is.
"""
import errno
import os
import time

MOVEFILE_REPLACE_EXISTING = 0x1
MOVEFILE_WRITE_THROUGH = 0x8
ERROR_ACCESS_DENIED = 5
ERROR_SHARING_VIOLATION = 32
RETRY_DELAYS = (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0)   # ~3.9 s in total, then the error stands


class LockHeld(OSError):
    """Another process (or another handle in this one) holds the writer lock."""


def platform():
    p = os.environ.get("EOS_PLATFORM") or ("windows" if os.name == "nt" else "posix")
    if p not in ("posix", "windows", "windows-sim"):
        raise ValueError(f"EOS_PLATFORM={p!r}: expected posix, windows or windows-sim")
    return p


def is_windows_like():
    return platform() in ("windows", "windows-sim")


# ------------------------------------------------------------------ Windows emulation (windows-sim only)
class _SimKernel32:
    """MoveFileExW as Windows behaves for the warehouse: replaces atomically, records the flags it was given,
    and fails with a sharing violation when a test injects one."""

    def __init__(self):
        self.calls = []
        self.inject_sharing_violations = 0
        self.last_error = 0

    def MoveFileExW(self, src, dst, flags):  # noqa: N802 - Windows API name
        self.calls.append((src, dst, flags))
        if self.inject_sharing_violations:
            self.inject_sharing_violations -= 1
            self.last_error = ERROR_SHARING_VIOLATION
            return 0
        if not flags & MOVEFILE_REPLACE_EXISTING and os.path.exists(dst):
            self.last_error = 183    # ERROR_ALREADY_EXISTS
            return 0
        try:
            os.replace(src, dst)
        except OSError as e:
            self.last_error = {errno.ENOENT: 2, errno.EACCES: ERROR_ACCESS_DENIED}.get(e.errno, 31)
            return 0
        return 1


class _SimMsvcrt:
    """msvcrt.locking semantics that matter here: a non-blocking lock is refused while any other handle,
    in this process or another, holds it; the OS drops it when the process dies. Emulated with flock,
    which has the same per-handle, released-at-death behaviour."""
    LK_UNLCK, LK_LOCK, LK_NBLCK, LK_RLCK, LK_NBRLCK = 0, 1, 2, 3, 4

    @staticmethod
    def locking(fd, mode, nbytes):
        import fcntl
        if mode == _SimMsvcrt.LK_UNLCK:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OSError(errno.EACCES, "Permission denied") from None   # what msvcrt raises on Windows


SIM_KERNEL32 = _SimKernel32()


def _kernel32():
    if platform() == "windows-sim":
        return SIM_KERNEL32, lambda: SIM_KERNEL32.last_error
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.MoveFileExW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    k.MoveFileExW.restype = wintypes.BOOL
    return k, ctypes.get_last_error


def _msvcrt():
    if platform() == "windows-sim":
        return _SimMsvcrt
    import msvcrt
    return msvcrt


# ------------------------------------------------------------------ durable replace
def _fsync_dir(path):
    if is_windows_like():
        raise AssertionError("a directory is never opened on Windows")   # structural guard, see module docstring
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def replace_durable(src, dst):
    """Atomically move src over dst and return only once the move is durable."""
    if not is_windows_like():
        os.replace(src, dst)
        _fsync_dir(os.path.dirname(os.path.abspath(dst)))
        return
    k, last_error = _kernel32()
    flags = MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
    for delay in RETRY_DELAYS + (None,):
        if k.MoveFileExW(os.path.abspath(src), os.path.abspath(dst), flags):
            return
        err = last_error()
        if err not in (ERROR_ACCESS_DENIED, ERROR_SHARING_VIOLATION) or delay is None:
            raise OSError(f"MoveFileExW({src!r} -> {dst!r}) failed with Windows error {err}")
        time.sleep(delay)


def write_durable(path, data, tmp_name):
    """Write bytes to a temp file in path's directory, flush them to disk, then replace path durably."""
    tmp = os.path.join(os.path.dirname(path), tmp_name)
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    try:
        replace_durable(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def read_bytes(path):
    """Read a whole file, retrying a Windows sharing violation (a scanner holding it) with bounded backoff."""
    for delay in RETRY_DELAYS + (None,):
        try:
            with open(path, "rb") as f:
                return f.read()
        except PermissionError:
            if not is_windows_like() or delay is None:
                raise
            time.sleep(delay)


# ------------------------------------------------------------------ writer lock
def lock_exclusive(path):
    """Open (never create-exclusive, never delete) the lock file and take the OS lock. Returns the fd.
    Raises LockHeld if anyone else holds it."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if is_windows_like():
            m = _msvcrt()
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                m.locking(fd, m.LK_NBLCK, 1)
            except OSError:
                raise LockHeld(errno.EACCES, f"another writer holds {path}") from None
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LockHeld(errno.EAGAIN, f"another writer holds {path}") from None
    except BaseException:
        os.close(fd)
        raise
    return fd


def unlock(fd):
    try:
        if is_windows_like():
            m = _msvcrt()
            os.lseek(fd, 0, os.SEEK_SET)
            m.locking(fd, m.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
