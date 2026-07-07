"""Extract plugin metadata from a Bukkit/Paper plugin jar.

Reads ``plugin.yml`` (Bukkit) or ``paper-plugin.yml`` (Paper) from the jar and
normalises the fields we care about into a :class:`PluginMeta`.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class PluginMeta:
    path: Path
    name: str | None = None
    version: str | None = None
    main: str | None = None
    api_version: str | None = None
    kind: str = "unknown"  # "paper", "bukkit", or "unknown"
    depends: list[str] = field(default_factory=list)
    soft_depends: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.path.stem


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def _paper_dependencies(data: dict, meta: PluginMeta) -> None:
    """paper-plugin.yml nests deps under dependencies.{server,bootstrap}."""
    deps = data.get("dependencies")
    if not isinstance(deps, dict):
        return
    server = deps.get("server")
    if not isinstance(server, dict):
        return
    for dep_name, cfg in server.items():
        required = cfg.get("required", True) if isinstance(cfg, dict) else True
        (meta.depends if required else meta.soft_depends).append(str(dep_name))


def read_plugin_meta(jar: Path) -> PluginMeta:
    meta = PluginMeta(path=jar)
    if not jar.is_file():
        meta.error = "not a regular file"
        return meta

    try:
        with zipfile.ZipFile(jar) as zf:
            names = set(zf.namelist())
            if "paper-plugin.yml" in names:
                descriptor, meta.kind = "paper-plugin.yml", "paper"
            elif "plugin.yml" in names:
                descriptor, meta.kind = "plugin.yml", "bukkit"
            else:
                meta.error = "no plugin.yml / paper-plugin.yml"
                return meta
            with zf.open(descriptor) as fh:
                data = yaml.safe_load(fh) or {}
    except zipfile.BadZipFile:
        meta.error = "not a valid jar/zip"
        return meta
    except (OSError, yaml.YAMLError) as exc:
        meta.error = f"{type(exc).__name__}: {exc}"
        return meta

    if not isinstance(data, dict):
        meta.error = "descriptor is not a mapping"
        return meta

    meta.name = data.get("name")
    meta.version = None if data.get("version") is None else str(data.get("version"))
    meta.main = data.get("main")
    meta.api_version = None if data.get("api-version") is None else str(data.get("api-version"))
    meta.authors = _as_list(data.get("authors") or data.get("author"))
    meta.provides = _as_list(data.get("provides"))

    if meta.kind == "paper":
        _paper_dependencies(data, meta)
    else:
        meta.depends = _as_list(data.get("depend"))
        meta.soft_depends = _as_list(data.get("softdepend"))

    return meta
