# mcmanager

Lightweight management tooling for a [PaperMC](https://papermc.io) Minecraft
server. Pure Python standard library plus PyYAML, so it runs directly on the
server host with no virtualenv or `pip install` required.

## Requirements

- Python 3.10+
- PyYAML (`python3 -c "import yaml"` — already present on the server host)

## Usage

Run from the repo directory via the `mcm` launcher:

```bash
./mcm plugins list             # inventory every plugin jar (name, version, kind, api)
./mcm plugins show <name>      # details for one plugin
./mcm plugins doctor           # flag problems: dupes, unmet deps, unparseable jars
./mcm plugins list --json      # machine-readable output

./mcm plugins outdated         # check installed plugins against Modrinth for the server's MC version
./mcm plugins update <name>    # download + back up current + stage the update into plugins/update/
./mcm plugins update --all     # stage every Modrinth-sourced plugin that's outdated
./mcm plugins update <name> --dry-run
```

`outdated`/`update` read the server's Minecraft version from `paper-current.jar`
and consult **Modrinth** for each plugin (mapped in `mcmanager/sources.yml`).
`update` never touches a running server destructively: it downloads the new jar,
verifies it's a real plugin jar, copies the current one into a timestamped backup
under `plugin-backups/mcmanager/`, and drops the new jar into Paper's `plugins/update/`
folder — which swaps it in on the next restart. Plugins built from source
(radawson's own) are marked `local` and skipped; SpigotMC/GitHub/Hangar ones are
reported as manual.

By default it looks at `/home/papercraft/papermc`. Override with environment
variables:

```bash
MCM_SERVER_DIR=/path/to/server ./mcm plugins list
MCM_PLUGINS_DIR=/path/to/plugins ./mcm plugins list
```

Or install it as a console script:

```bash
pip install -e .
mcm plugins list
```

## What `doctor` checks

- Jars whose `plugin.yml` / `paper-plugin.yml` can't be read.
- Duplicate plugin names provided by more than one jar.
- Bukkit plugins declaring no `api-version` (run through legacy conversion).
- Hard `depend:` entries that aren't satisfied by an installed plugin.

## Roadmap

`plugins list/show/doctor` is v1. Planned next:

- **Backup/restore** — snapshot a plugin (and its config dir) before swapping versions.
- **Install/update/disable** — drop-in a jar, park the old one as `*.jar.disabled`, verify it loads.
- **Update checks** — query source APIs (Hangar, Modrinth, SpigotMC) for newer versions.
- **Server control** — thin wrappers over the `minecraft.service` unit and the console FIFO.
- **Config reporting** — surface which worlds each plugin touches, port usage, etc.

## Layout

```
mcmanager/
  mcm                 launcher script
  pyproject.toml      packaging / console-script entry point
  mcmanager/
    cli.py            argparse command surface
    config.py         path resolution (env-overridable)
    jarmeta.py        read plugin.yml / paper-plugin.yml from a jar
    plugins.py        inventory over the plugins directory
```
