"""Cross-worker cache and rolling request budget for the single Keycafe server."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
import fcntl


def database():
    path = Path(settings.TABLEAU_UPSTREAM_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=25)
    db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, value TEXT)')
    db.execute('CREATE TABLE IF NOT EXISTS requests (created REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS cooldown (id INTEGER PRIMARY KEY, until REAL)')
    return db


def scope(auth):
    return hashlib.sha256(auth.authorization.encode()).hexdigest()


@contextmanager
def lock():
    path = Path(settings.TABLEAU_UPSTREAM_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + '.lock', 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def cached(key, ttl, loader, validate=lambda value: True):
    # Serialize fills across workers so simultaneous tabs share one upstream fetch.
    with lock():
        with database() as db:
            now = time.time()
            db.execute('DELETE FROM cache WHERE expires <= ?', (now,))
            row = db.execute('SELECT value FROM cache WHERE key = ?', (key,)).fetchone()
            if row:
                return json.loads(row[0])
        value = loader()
        if not validate(value):
            return value
        with database() as db:
            db.execute('INSERT OR REPLACE INTO cache VALUES (?, ?, ?)',
                       (key, time.time() + ttl, json.dumps(value)))
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
    with database() as db:
        db.execute('INSERT OR REPLACE INTO cooldown VALUES (1, ?)', (time.time() + max(60, seconds),))
