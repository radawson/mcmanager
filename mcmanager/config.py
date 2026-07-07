"""Configuration and path resolution for mcmanager.

Defaults target the PaperMC install on the server host; override with environment
variables (MCM_SERVER_DIR, MCM_PLUGINS_DIR, MCM_MC_VERSION, MCM_BACKUP_DIR).
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

DEFAULT_SERVER_DIR = Path("/home/papercraft/papermc")


def server_dir() -> Path:
    return Path(os.environ.get("MCM_SERVER_DIR", DEFAULT_SERVER_DIR))


def plugins_dir() -> Path:
    env = os.environ.get("MCM_PLUGINS_DIR")
    return Path(env) if env else server_dir() / "plugins"


def update_dir() -> Path:
    """Paper's hot-swap folder: a jar placed here replaces its plugin on next (re)start."""
    return plugins_dir() / "update"


def backup_dir() -> Path:
    """Where the updater copies a jar before replacing it."""
    env = os.environ.get("MCM_BACKUP_DIR")
    return Path(env) if env else server_dir().parent / "plugin-backups" / "mcmanager"


def server_mc_version() -> str | None:
    """The server's Minecraft version, read from paper-current.jar's version.json
    (e.g. "26.1.2"). Overridable with MCM_MC_VERSION; None if undetectable."""
    env = os.environ.get("MCM_MC_VERSION")
    if env:
        return env
    jar = server_dir() / "paper-current.jar"
    if not jar.is_file():
        return None
    try:
        with zipfile.ZipFile(jar) as zf:
            with zf.open("version.json") as fh:
                return json.load(fh).get("id")
    except (OSError, zipfile.BadZipFile, KeyError, ValueError):
        return None
