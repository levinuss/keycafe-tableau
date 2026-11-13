import os

from .keycafe import normalize_key, summarize_keys


DEMO_SMARTBOX = {"id": "box-reception", "name": "SmartBox am Empfang"}

DEMO_GROUPS = [
    {"id": "demo-all", "name": "Alle Schlüssel", "type": "KEY"},
    {"id": "demo-facilities", "name": "Gebäude", "type": "KEY"},
    {"id": "demo-fleet", "name": "Fuhrpark", "type": "KEY"},
    {"id": "demo-it", "name": "IT & Technik", "type": "KEY"},
]

DEMO_KEYS = [
    {
        "id": "demo-101",
        "groupIds": ["demo-facilities"],
        "name": "Haupteingang",
        "description": "Haupteingang des Verwaltungsgebäudes",
        "serialNumber": "DEMO-A101",
        "homeLocation": DEMO_SMARTBOX,
        "currentLocation": DEMO_SMARTBOX,
    },
    {
        "id": "demo-102",
        "groupIds": ["demo-facilities"],
        "name": "Werkstattschlüssel",
        "description": "Generalschlüssel der zentralen Werkstatt",
        "serialNumber": "DEMO-A102",
        "homeLocation": DEMO_SMARTBOX,
        "removedAt": "2026-11-13T08:30:00Z",
        "currentUser": {
            "id": "user-amelie",
            "firstName": "Amelie",
            "lastName": "Fischer",
            "email": "amelie.fischer@example.org",
        },
    },
    {
        "id": "demo-103",
        "groupIds": ["demo-facilities"],
        "name": "Archiv",
        "description": "Zugang zum Archivraum",
        "serialNumber": "DEMO-A103",
        "homeLocation": DEMO_SMARTBOX,
        "currentLocation": DEMO_SMARTBOX,
    },
    {
        "id": "demo-201",
        "groupIds": ["demo-fleet"],
        "name": "Dienstwagen 01",
        "description": "Elektrischer Dienstwagen",
        "serialNumber": "DEMO-F201",
        "homeLocation": DEMO_SMARTBOX,
        "currentLocation": DEMO_SMARTBOX,
    },
    {
        "id": "demo-202",
        "groupIds": ["demo-fleet"],
        "name": "Dienstwagen 02",
        "description": "Dienstwagen mit Hybridantrieb",
        "serialNumber": "DEMO-F202",
        "homeLocation": DEMO_SMARTBOX,
        "removedAt": "2026-11-13T08:30:00Z",
        "currentUser": {
            "id": "user-daniel",
            "firstName": "Daniel",
            "lastName": "Klein",
            "email": "daniel.klein@example.org",
        },
    },
    {
        "id": "demo-203",
        "groupIds": ["demo-fleet"],
        "name": "Transporter",
        "description": "Transporter des Gebäudeservices",
        "serialNumber": "DEMO-F203",
        "homeLocation": DEMO_SMARTBOX,
        "removedAt": "2026-11-13T08:30:00Z",
        "currentUser": {
            "id": "user-noor",
            "firstName": "Noor",
            "lastName": "Haddad",
            "email": "noor.haddad@example.org",
        },
    },
    {
        "id": "demo-301",
        "groupIds": ["demo-it"],
        "name": "Serverraum A",
        "description": "Zugang zum Rechenzentrum",
        "serialNumber": "DEMO-I301",
        "homeLocation": DEMO_SMARTBOX,
        "currentLocation": DEMO_SMARTBOX,
    },
    {
        "id": "demo-302",
        "groupIds": ["demo-it"],
        "name": "Netzwerkschrank West",
        "description": "Netzwerkschrank im Westflügel",
        "serialNumber": "DEMO-I302",
        "homeLocation": DEMO_SMARTBOX,
        "currentLocation": DEMO_SMARTBOX,
    },
    {
        "id": "demo-303",
        "groupIds": ["demo-it"],
        "name": "Medienschrank",
        "description": "Technikschrank im Hörsaal",
        "serialNumber": "DEMO-I303",
        "homeLocation": DEMO_SMARTBOX,
    },
]


def demo_mode_enabled() -> bool:
    return os.environ.get("KEYCAFE_DEMO_MODE", "").lower() in {
        "1", "true", "yes", "on",
    }


def demo_groups() -> list[dict]:
    return [{"id": group["id"], "name": group["name"]} for group in DEMO_GROUPS]


def demo_keys(group: str | None = None) -> dict:
    selected_group = group or "demo-all"
    if selected_group == "demo-all":
        raw_keys = DEMO_KEYS
    else:
        raw_keys = [key for key in DEMO_KEYS if selected_group in key["groupIds"]]

    keys = [normalize_key(key) for key in raw_keys]
    return {
        "keys": keys,
        "summary": summarize_keys(keys),
    }
