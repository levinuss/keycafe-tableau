"""Cross-worker cache and rolling request budget for the single Keycafe server."""
import fcntl
import hashlib
import json
import sqlite3
import time
from contextlib import closing, contextmanager
from pathlib import Path

from django.conf import settings

MAX_COOLDOWN_SECONDS = 900
_INITIALIZED_DBS: set[tuple[str, int]] = set()


@contextmanager
def database():
    from .keycafe import KeycafeError

    path = Path(settings.TABLEAU_UPSTREAM_DB)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path, timeout=25)) as db:
            db_key = (str(path.resolve()), path.stat().st_ino)
            if db_key not in _INITIALIZED_DBS:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, value TEXT)')
                db.execute('CREATE TABLE IF NOT EXISTS requests (created REAL)')
                db.execute('CREATE TABLE IF NOT EXISTS cooldown (id INTEGER PRIMARY KEY, until REAL)')
                _INITIALIZED_DBS.add(db_key)
            with db:
                yield db
    except (sqlite3.Error, OSError):
        raise KeycafeError(503, 'Der Zwischenspeicher ist nicht verfügbar.') from None


def scope(auth):
    return hashlib.sha256(auth.authorization.encode()).hexdigest()


@contextmanager
def lock(key):
    from .keycafe import KeycafeError

    path = Path(settings.TABLEAU_UPSTREAM_DB)
    # Bound the number of lock files even as holders and inventory change.
    stripe = hashlib.sha256(key.encode()).hexdigest()[:2]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(f'{path}.{stripe}.lock', 'a')
    except OSError:
        raise KeycafeError(503, 'Der Zwischenspeicher ist nicht verfügbar.') from None
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX)
        except OSError:
            raise KeycafeError(503, 'Der Zwischenspeicher ist nicht verfügbar.') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def cache_row(key):
    with database() as db:
        return db.execute('SELECT value FROM cache WHERE key = ? AND expires > ?',
                          (key, time.time())).fetchone()


def cached(key, ttl, loader, validate=lambda value: True):
    row = cache_row(key)
    if row:
        return json.loads(row[0])
    with lock(key):
        row = cache_row(key)
        if row:
            return json.loads(row[0])
        value = loader()
        if not validate(value):
            return value
        ttl_seconds = ttl(value) if callable(ttl) else ttl
        with database() as db:
            db.execute('DELETE FROM cache WHERE expires <= ?', (time.time(),))
            db.execute('INSERT OR REPLACE INTO cache VALUES (?, ?, ?)',
                       (key, time.time() + ttl_seconds, json.dumps(value)))
        return value


def reserve():
    from .keycafe import KeycafeError
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        now = time.time()
        db.execute('DELETE FROM requests WHERE created <= ?', (now - 60,))
        row = db.execute('SELECT until FROM cooldown WHERE id = 1').fetchone()
        if row and row[0] > now:
            raise KeycafeError(503, 'Keycafe pausiert wegen des Anfragelimits. Bitte später erneut versuchen.')
        if db.execute('SELECT COUNT(*) FROM requests').fetchone()[0] >= settings.KEYCAFE_REQUESTS_PER_MINUTE:
            raise KeycafeError(503, 'Das Keycafe-Anfragelimit ist erreicht. Bitte in einer Minute erneut versuchen.')
        db.execute('INSERT INTO requests VALUES (?)', (now,))


def backoff(seconds=60):
    until = time.time() + min(max(60, seconds), MAX_COOLDOWN_SECONDS)
    with database() as db:
        db.execute(
            'INSERT INTO cooldown (id, until) VALUES (1, ?) '
            'ON CONFLICT(id) DO UPDATE SET until = MAX(cooldown.until, excluded.until)',
            (until,),
        )
