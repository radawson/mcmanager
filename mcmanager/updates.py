"""Update checking and jar fetching via the Modrinth API (stdlib only)."""
from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

_UA = f"radawson/mcmanager/{__version__} (github.com/radawson/mcmanager)"
_MODRINTH = "https://api.modrinth.com/v2"
_DEFAULT_LOADERS = ("paper", "spigot", "bukkit", "purpur", "folia")


class SourceError(Exception):
    """A source could not be queried (project not found, network, etc.)."""


@dataclass
class Candidate:
    version_number: str
    filename: str
    url: str


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SourceError("not found (404) - check the slug") from exc
        raise SourceError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SourceError(str(exc)) from exc


def normalize_version(v: str | None) -> str:
    """Strip a leading v and build metadata for comparison: '2.15.2+e9ed0d1' -> '2.15.2'."""
    if not v:
        return ""
    return v.strip().lstrip("vV").split("+", 1)[0].strip()


def _ver_tuple(v: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in re.split(r"[.\-_]", normalize_version(v)):
        m = re.match(r"\d+", part)
        out.append(int(m.group()) if m else 0)
    return tuple(out)


def is_newer(latest: str, installed: str) -> bool:
    """Best-effort: True if `latest` looks strictly newer than `installed`."""
    if normalize_version(latest) == normalize_version(installed):
        return False
    try:
        return _ver_tuple(latest) > _ver_tuple(installed)
    except Exception:
        return normalize_version(latest) != normalize_version(installed)


def modrinth_latest(slug: str, mc_version: str, loaders=_DEFAULT_LOADERS) -> Candidate | None:
    """Newest Modrinth version of `slug` compatible with `mc_version`, or None if the
    project has no build for that MC version."""
    query = urllib.parse.urlencode({
        "loaders": json.dumps(list(loaders)),
        "game_versions": json.dumps([mc_version]),
    })
    versions = _get_json(f"{_MODRINTH}/project/{slug}/version?{query}")
    if not versions:
        return None
    # Newest first by publish date (don't rely on server ordering).
    versions.sort(key=lambda v: v.get("date_published", ""), reverse=True)
    top = versions[0]
    files = top.get("files") or []
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if not primary or not primary.get("url"):
        return None
    return Candidate(
        version_number=top.get("version_number", "?"),
        filename=primary.get("filename", f"{slug}.jar"),
        url=primary["url"],
    )


def download(url: str, dest: Path) -> int:
    """Download `url` to `dest`, returning the byte size."""
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=180) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)
    return dest.stat().st_size
