"""Local dashboard groups, independent of Keycafe permission groups."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings

from .keycafe import KeycafeError


@contextmanager
def database():
    path = Path(settings.TABLEAU_GROUPS_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS groups (id TEXT PRIMARY KEY, name TEXT NOT NULL, key_ids TEXT NOT NULL)')
        yield connection


def list_groups():
    with database() as connection:
        return [{"id": row[0], "name": row[1], "keyIds": json.loads(row[2])}
                for row in connection.execute('SELECT id, name, key_ids FROM groups ORDER BY name COLLATE NOCASE, id')]


def get_group(group_id):
    for group in list_groups():
        if group['id'] == group_id:
            return group
    raise KeycafeError(404, 'Schlüsselgruppe nicht gefunden.')


def save_group(payload, group_id=None):
    if not isinstance(payload, dict):
        raise KeycafeError(400, 'Ungültige Gruppendaten.')
    name, ids = payload.get('name'), payload.get('keyIds')
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise KeycafeError(400, 'Bitte einen Gruppennamen mit höchstens 120 Zeichen eingeben.')
    if not isinstance(ids, list) or len(ids) > 2000 or any(
        not isinstance(value, (int, str)) or isinstance(value, bool) or not str(value).isascii()
        or not str(value).isdigit() or int(value) <= 0 for value in ids
    ):
        raise KeycafeError(400, 'Bitte gültige numerische Keycafe-Schlüssel-IDs angeben (maximal 2000).')
    ids = list(dict.fromkeys(str(int(value)) for value in ids))
    with database() as connection:
        if group_id:
            cursor = connection.execute('UPDATE groups SET name=?, key_ids=? WHERE id=?', (name.strip(), json.dumps(ids), group_id))
            if not cursor.rowcount:
                raise KeycafeError(404, 'Schlüsselgruppe nicht gefunden.')
        else:
            group_id = str(uuid.uuid4())
            connection.execute('INSERT INTO groups VALUES (?, ?, ?)', (group_id, name.strip(), json.dumps(ids)))
    return {"id": group_id, "name": name.strip(), "keyIds": ids}


def delete_group(group_id):
    with database() as connection:
        if not connection.execute('DELETE FROM groups WHERE id=?', (group_id,)).rowcount:
            raise KeycafeError(404, 'Schlüsselgruppe nicht gefunden.')
