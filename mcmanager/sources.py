"""Loads the plugin -> update-source mapping from sources.yml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_SOURCES_FILE = Path(__file__).with_name("sources.yml")


@dataclass
class Source:
    plugin: str
    kind: str = "unknown"  # modrinth | github | hangar | spigot | local | manual | unknown
    id: str | None = None
    note: str | None = None


def load_sources() -> dict[str, Source]:
    """Returns a map of lowercased plugin name -> Source."""
    if not _SOURCES_FILE.is_file():
        return {}
    data = yaml.safe_load(_SOURCES_FILE.read_text()) or {}
    out: dict[str, Source] = {}
    for name, spec in (data.get("plugins") or {}).items():
        spec = spec or {}
        out[str(name).lower()] = Source(
            plugin=str(name),
            kind=spec.get("kind", "unknown"),
            id=spec.get("id"),
            note=spec.get("note"),
        )
    return out


def source_for(plugin_name: str | None, sources: dict[str, Source]) -> Source:
    key = (plugin_name or "").lower()
    return sources.get(key, Source(plugin=plugin_name or "?", kind="unknown"))
