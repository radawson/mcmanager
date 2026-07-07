"""Command-line interface for mcmanager (``mcm``)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, updates
from .config import backup_dir, plugins_dir, server_mc_version, update_dir
from .jarmeta import PluginMeta
from .plugins import find_disabled, scan_plugins
from .sources import load_sources, source_for


def _fmt_table(rows: list[list[str]], headers: list[str]) -> str:
    cols = list(zip(*([headers] + rows))) if rows else [[h] for h in headers]
    widths = [max(len(str(c)) for c in col) for col in cols]

    def line(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    out = [line(headers), line(["-" * w for w in widths])]
    out += [line(r) for r in rows]
    return "\n".join(out)


def _meta_dict(m: PluginMeta) -> dict:
    return {
        "file": m.path.name,
        "name": m.name,
        "version": m.version,
        "kind": m.kind,
        "api_version": m.api_version,
        "main": m.main,
        "depends": m.depends,
        "soft_depends": m.soft_depends,
        "provides": m.provides,
        "authors": m.authors,
        "error": m.error,
    }


def cmd_list(args) -> int:
    metas = scan_plugins()
    if args.json:
        print(json.dumps([_meta_dict(m) for m in metas], indent=2))
        return 0
    rows = [
        [m.name or "?", m.version or "?", m.kind, m.api_version or "-", m.error or ""]
        for m in metas
    ]
    print(f"# {len(metas)} plugin jar(s) in {plugins_dir()}")
    print(_fmt_table(rows, ["NAME", "VERSION", "KIND", "API", "NOTE"]))
    disabled = find_disabled()
    if disabled:
        print(f"\n# {len(disabled)} disabled/backup jar(s):")
        for d in disabled:
            print(f"  - {d.name}")
    return 0


def cmd_show(args) -> int:
    metas = {m.label.lower(): m for m in scan_plugins()}
    m = metas.get(args.name.lower())
    if not m:
        print(f"No plugin named {args.name!r} found in {plugins_dir()}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(_meta_dict(m), indent=2))
        return 0
    print(f"{m.name}  {m.version}")
    print(f"  file:        {m.path.name}")
    print(f"  kind:        {m.kind}")
    print(f"  api-version: {m.api_version or '-'}")
    print(f"  main:        {m.main or '-'}")
    print(f"  depends:     {', '.join(m.depends) or '-'}")
    print(f"  softdepends: {', '.join(m.soft_depends) or '-'}")
    print(f"  provides:    {', '.join(m.provides) or '-'}")
    print(f"  authors:     {', '.join(m.authors) or '-'}")
    if m.error:
        print(f"  error:       {m.error}")
    return 0


def cmd_doctor(args) -> int:
    metas = scan_plugins()
    issues: list[str] = []

    for m in metas:
        if m.error:
            issues.append(f"[parse]  {m.path.name}: {m.error}")

    by_name: dict[str, list[PluginMeta]] = {}
    for m in metas:
        if m.name:
            by_name.setdefault(m.name.lower(), []).append(m)
    for group in by_name.values():
        if len(group) > 1:
            files = ", ".join(g.path.name for g in group)
            issues.append(f"[dupe]   plugin {group[0].name!r} provided by {len(group)} jars: {files}")

    legacy = [m.name for m in metas if m.kind == "bukkit" and not m.api_version and not m.error]
    if legacy:
        issues.append(f"[legacy] {len(legacy)} plugin(s) declare no api-version: {', '.join(legacy)}")

    present: set[str] = set()
    for m in metas:
        if m.name:
            present.add(m.name.lower())
        present.update(p.lower() for p in m.provides)
    for m in metas:
        for dep in m.depends:
            if dep.lower() not in present:
                issues.append(f"[dep]    {m.label}: hard-depends on {dep!r} which is not installed")

    if not issues:
        print("doctor: no issues found")
        return 0
    print(f"doctor: {len(issues)} issue(s) found:")
    for i in issues:
        print(f"  - {i}")
    return 1


def cmd_outdated(args) -> int:
    mc = server_mc_version()
    if not mc:
        print("Could not determine server MC version (set MCM_MC_VERSION).", file=sys.stderr)
        return 2
    sources = load_sources()
    metas = scan_plugins()
    rows: list[list[str]] = []
    available = 0
    for m in sorted(metas, key=lambda x: (x.name or x.path.stem).lower()):
        name = m.name or m.path.stem
        installed = m.version or "?"
        src = source_for(name, sources)
        if src.kind == "modrinth" and src.id:
            try:
                cand = updates.modrinth_latest(src.id, mc)
            except updates.SourceError as exc:
                rows.append([name, installed, "-", f"modrinth error: {exc}"])
                continue
            if cand is None:
                rows.append([name, installed, "-", f"no {mc} build on modrinth"])
            elif updates.is_newer(cand.version_number, installed):
                rows.append([name, installed, cand.version_number, "UPDATE AVAILABLE"])
                available += 1
            else:
                rows.append([name, installed, cand.version_number, "up-to-date"])
        elif src.kind == "local":
            rows.append([name, installed, "-", "local (built from source)"])
        elif src.kind in ("spigot", "github", "hangar", "manual"):
            rows.append([name, installed, "-", f"{src.kind} (manual)" + (f" - {src.note}" if src.note else "")])
        else:
            rows.append([name, installed, "-", "no source configured (edit sources.yml)"])

    print(f"# update check against Minecraft {mc}  ({plugins_dir()})")
    print(_fmt_table(rows, ["NAME", "INSTALLED", "LATEST", "STATUS"]))
    print(f"\n# {available} update(s) available via Modrinth. Apply with: mcm plugins update <name>  (or --all)")
    return 0


def _stage_update(meta: PluginMeta, cand: "updates.Candidate", dry_run: bool) -> bool:
    """Download, verify, back up the current jar, and stage the new one into update/."""
    upd = update_dir()
    if dry_run:
        print(f"  [dry-run] {meta.name}: {meta.version} -> {cand.version_number} "
              f"(would stage {cand.filename} into {upd}, backing up {meta.path.name})")
        return True
    upd.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / cand.filename
        size = updates.download(cand.url, tmp)
        try:
            with zipfile.ZipFile(tmp) as zf:
                names = set(zf.namelist())
        except zipfile.BadZipFile:
            print(f"  ERROR {meta.name}: downloaded file is not a valid jar; skipped", file=sys.stderr)
            return False
        if not ({"plugin.yml", "paper-plugin.yml"} & names):
            print(f"  ERROR {meta.name}: {cand.filename} has no plugin.yml; skipped", file=sys.stderr)
            return False
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        bdir = backup_dir() / stamp
        bdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(meta.path, bdir / meta.path.name)
        shutil.copy2(tmp, upd / cand.filename)
    print(f"  {meta.name}: {meta.version} -> {cand.version_number}  staged {cand.filename} ({size:,} bytes)")
    print(f"    backup: {bdir / meta.path.name}")
    return True


def cmd_update(args) -> int:
    if not args.all and not args.name:
        print("Specify a plugin name or --all.", file=sys.stderr)
        return 2
    mc = server_mc_version()
    if not mc:
        print("Could not determine server MC version (set MCM_MC_VERSION).", file=sys.stderr)
        return 2
    sources = load_sources()
    metas = scan_plugins()
    by_name = {(m.name or m.path.stem).lower(): m for m in metas}

    if args.all:
        targets = [m for m in metas if source_for(m.name or m.path.stem, sources).kind == "modrinth"]
    else:
        m = by_name.get(args.name.lower())
        if not m:
            print(f"No installed plugin named {args.name!r}", file=sys.stderr)
            return 1
        targets = [m]

    staged = 0
    for m in targets:
        name = m.name or m.path.stem
        src = source_for(name, sources)
        if src.kind != "modrinth" or not src.id:
            if not args.all:
                print(f"{name}: no Modrinth source configured (kind={src.kind}).", file=sys.stderr)
                return 1
            continue
        try:
            cand = updates.modrinth_latest(src.id, mc)
        except updates.SourceError as exc:
            print(f"  {name}: {exc}", file=sys.stderr)
            if not args.all:
                return 1
            continue
        if cand is None:
            print(f"  {name}: no build for MC {mc} on Modrinth", file=sys.stderr)
            continue
        if not args.force and not updates.is_newer(cand.version_number, m.version or ""):
            if not args.all:
                print(f"{name}: already up to date ({m.version}). Use --force to re-stage.")
            continue
        if _stage_update(m, cand, args.dry_run):
            staged += 1

    if args.dry_run:
        print("\n# dry run - nothing changed.")
    elif staged:
        print(f"\n# staged {staged} update(s) into {update_dir()} - restart the server to apply.")
    else:
        print("# nothing to update.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mcm", description="mcmanager - PaperMC server tooling")
    p.add_argument("--version", action="version", version=f"mcmanager {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("plugins", help="inspect installed plugins")
    plsub = pl.add_subparsers(dest="subcommand", required=True)

    p_list = plsub.add_parser("list", help="list installed plugins")
    p_list.add_argument("--json", action="store_true", help="emit JSON")
    p_list.set_defaults(func=cmd_list)

    p_show = plsub.add_parser("show", help="show one plugin's metadata")
    p_show.add_argument("name", help="plugin name (as declared in plugin.yml)")
    p_show.add_argument("--json", action="store_true", help="emit JSON")
    p_show.set_defaults(func=cmd_show)

    p_doc = plsub.add_parser("doctor", help="check for plugin problems")
    p_doc.set_defaults(func=cmd_doctor)

    p_out = plsub.add_parser("outdated", help="check installed plugins against Modrinth for the server MC version")
    p_out.set_defaults(func=cmd_outdated)

    p_upd = plsub.add_parser("update", help="download+backup+stage a plugin update into the update/ folder")
    p_upd.add_argument("name", nargs="?", help="plugin name (omit with --all)")
    p_upd.add_argument("--all", action="store_true", help="update every Modrinth-sourced plugin that's outdated")
    p_upd.add_argument("--force", action="store_true", help="stage even if not detected as newer")
    p_upd.add_argument("--dry-run", action="store_true", help="show what would happen without downloading")
    p_upd.set_defaults(func=cmd_update)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
