# Changelog

All notable changes to MAPLEAD. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- **Windows 10/11 x64 build** — `build-windows.ps1` produces
  `%USERPROFILE%\Apps\MAPLEAD-<version>-win64.zip`: one portable folder with
  `MAPLEAD.exe` (windowed Qt app), `maplead-cli.exe` (terminal wizard, no Qt) and
  a `maplead.cmd` shim, sharing a single `_internal/` runtime, plus a version
  resource and a multi-resolution `maplead.ico`.
- **Windows installer** — `install.ps1` / `uninstall.ps1`: Start Menu shortcut,
  user PATH (`maplead`), *Apps & features* entry, no admin rights.
- `maplead/host.py` — platform glue: Windows console UTF-8 + virtual-terminal
  mode with an ASCII fallback, `sys.stdout is None` guards for windowed builds,
  `os.startfile`, and the taskbar AppUserModelID.
- `--doctor` — prints version, console mode, encoding, whether colour/Unicode are
  live, and every resolved folder; the first thing to attach to a bug report.
- CI builds and smoke-tests the Windows bundle; releases attach the Windows ZIP
  next to the AppImage.

### Changed
- On Windows the config, state and export folders follow the platform
  (`%APPDATA%\maplead`, `%LOCALAPPDATA%\maplead`, and the OneDrive-aware
  Documents folder) instead of XDG paths.
- Colour no longer requires `TERM` to be set, so Windows terminals get ANSI
  colours and Unicode box drawing out of the box.
- The export summary box now degrades to ASCII together with the rest of the art
  when output is plain, instead of mixing `#` pixels with `╔═╗` frames.

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

[Unreleased]: https://github.com/DariusDev16/maplead/compare/v1.0.0...main
[1.0.0]: https://github.com/DariusDev16/maplead/releases/tag/v1.0.0