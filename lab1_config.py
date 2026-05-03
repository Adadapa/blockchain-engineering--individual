from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_FILE = "lab1_config.json"


@dataclass(frozen=True)
class Lab1Config:
    email: str | None = None
    github_url: str | None = None
    key_file: str | None = None
    nonce: int | None = None


def load_lab1_config(path: str | Path) -> Lab1Config:
    config_path = Path(path)
    if not config_path.exists():
        return Lab1Config()

    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    if not isinstance(raw, dict):
        raise ValueError(f"config file {config_path} must contain a JSON object")

    email = raw.get("email")
    github_url = raw.get("github_url")
    key_file = raw.get("key_file")
    nonce = raw.get("nonce")

    if email is not None and not isinstance(email, str):
        raise ValueError("config field 'email' must be a string")
    if github_url is not None and not isinstance(github_url, str):
        raise ValueError("config field 'github_url' must be a string")
    if key_file is not None and not isinstance(key_file, str):
        raise ValueError("config field 'key_file' must be a string")
    if nonce is not None and not isinstance(nonce, int):
        raise ValueError("config field 'nonce' must be an integer")

    return Lab1Config(
        email=email,
        github_url=github_url,
        key_file=key_file,
        nonce=nonce,
    )


def resolve_config_value(cli_value: object, config_value: object, default_value: object) -> object:
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return config_value
    return default_value
