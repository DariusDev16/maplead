# Changelog

All notable changes to MAPLEAD. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-10-17

### Added
- **Qt6 desktop app** (`maplead/gui/`) — the nine wizard answers as one form,
  live stat tiles, a sortable/filterable results grid, a colour-coded activity log,
  a searchable 35-field picker that locks fields the chosen provider cannot return,
  and dark/light themes.
- **API key manager window** — paste a key, verify it with a real API call, save it to
  `~/.config/maplead/.env` (mode 600), or remove it. Per-provider status everywhere.
- **AppImage build** — `./build-appimage.sh [--install]` produces a single
  `~/Apps/MAPLEAD-<version>-x86_64.AppImage`, bundles the small X11 libraries desktops
  often lack, and smoke-tests the result.
- **No-FUSE launcher** — `~/Apps/maplead` unpacks the image once into
  `~/.maplead-runtime/` and runs it from there when `libfuse.so.2` is missing.
- `--gui` on the CLI launcher; `maplead-gui.py`; `--selftest` for a headless check.
- `maplead/paths.py` — XDG-aware config/data locations shared by both front-ends.
- User guide, development notes, contributing guide and CI.

### Changed
- API keys are read from a new XDG location when no `.env` sits next to the tool;
  an existing local `.env` keeps working exactly as before.
- Real environment variables still take precedence over the config file.
- The left-hand form now scrolls and pins the **Run/Stop** button, so the primary
  action is never scrolled out of reach on a small screen.
- Restored window geometry is clamped to the screen it is opened on.

### Fixed
- GUI labels no longer paint a background slab over their card.
- Columns are sized to their content, headers are short, and empty/unmatched states
  have their own message.
- Long lists in the terminal wizard keep their multi-column layout.

### Notes
- Linux x86_64 is the only packaged platform for now; the terminal wizard still runs
  anywhere Python 3.9+ does.

[1.0.0]: https://github.com/DariusDev16/maplead/releases/tag/v1.0.0