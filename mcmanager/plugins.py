"""Plugin inventory over the server's plugins directory."""
from __future__ import annotations

from pathlib import Path

from .config import plugins_dir
from .jarmeta import PluginMeta, read_plugin_meta


def scan_plugins(directory: Path | None = None) -> list[PluginMeta]:
    directory = directory or plugins_dir()
    return [read_plugin_meta(p) for p in sorted(directory.glob("*.jar"))]


def find_disabled(directory: Path | None = None) -> list[Path]:
    """Jars parked as disabled/backup (``*.jar.disabled``, ``*.jar.bak``)."""
    directory = directory or plugins_dir()
    return sorted(directory.glob("*.jar.disabled")) + sorted(directory.glob("*.jar.bak"))
