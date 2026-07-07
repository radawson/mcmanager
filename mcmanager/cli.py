"""Command-line interface for mcmanager (``mcm``)."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .config import plugins_dir
from .jarmeta import PluginMeta
from .plugins import find_disabled, scan_plugins


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

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
