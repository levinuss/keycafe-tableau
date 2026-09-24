import os
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = strip_inline_comment(value.strip())
        value = strip_quotes(value)

        if key and not os.environ.get(key):
            os.environ[key] = value


def strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]

    return value


def strip_inline_comment(value: str) -> str:
    if not value or value[0] in {"'", '"'}:
        return value

    marker = " #"
    if marker in value:
        return value.split(marker, 1)[0].rstrip()

    return value
