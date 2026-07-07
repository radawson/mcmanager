"""Configuration and path resolution for mcmanager.

Defaults target the PaperMC install on this host; override with environment
variables (MCM_SERVER_DIR, MCM_PLUGINS_DIR) or later a config file.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SERVER_DIR = Path("/home/papercraft/papermc")


def server_dir() -> Path:
    return Path(os.environ.get("MCM_SERVER_DIR", DEFAULT_SERVER_DIR))


def plugins_dir() -> Path:
    env = os.environ.get("MCM_PLUGINS_DIR")
    return Path(env) if env else server_dir() / "plugins"
