# Changelog

All notable changes to MAPLEAD. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [1.2.0] — 2026-10-22

### Added
- **Leads panel** — a card view of the results, opened from the results header,
  the right-click menu or `Ctrl+P`. It renders every selected field (not just
  the table columns), opens websites, Google Maps, e-mail and social profiles
  with one click, and shows `—` for fields the provider did not return.
- **WhatsApp outreach** — a button next to every phone number opens `wa.me` with
  a first message pre-filled from a template you write once. Placeholders such
  as `{nome}`, `{cidade}`, `{site}` and `{saudacao}` are filled from the search
  result itself, so the greeting uses the scraped business name even when the
  WhatsApp profile has none. The template is stored in the app settings and has
  a live preview with the real lead.
- Panel filters (*Has WhatsApp*, *Has phone*, *Has website*, *No website*,
  *Has e-mail*), a debounced search across all selected fields, sorting by
  rating / reviews / name, pagination, per-card TSV copy, and *Send WhatsApp
  message* / *Open in leads panel* in the grid's right-click menu.
- The panel refreshes after each run and keeps its position, filters and saved
  WhatsApp message while the next search is running.

### Changed
- **Exports are now explicit.** Finishing a search no longer writes a file
  automatically; the results stay in the window until the user presses
  **Export** (or `Ctrl+S`). The export section still selects the format
  and suggested path, but no file is created without that action.
- The suggested export name now follows the **latest search** (business + city)
  instead of sticking to the first one; accents are transliterated so
  `São Paulo` becomes `sao-paulo`.
- Both release builds — Linux AppImage and Windows portable `.exe` — bundle the
  new leads panel and contact helpers; the Windows and Linux CI jobs run the
  same headless self-test before publishing.

### Fixed
- Toggling to the light theme and back to dark works again; the second toggle
  no longer talks to the discarded window.
- The **Export** button now writes the file reliably (Qt's `clicked(bool)`
  argument is no longer mistaken for a path).

## [1.1.3] — 2026-10-21

### Added
- **Skip-landline filter** — the *Skip landline phones* checkbox in the GUI and
  `--skip-landlines` in the wizard keep mobile numbers and drop the ones that look
  like landlines. Numbers are classified per country by their prefixes
  (BR, PT, ES, GB, DE, FR, IT, NL, IE, AU, CO, PE, CL); where mobile and landline share
  the same format (US, Canada…) nothing is dropped instead of guessing.
- The offline demo provider now generates plausible mobile **and** landline numbers for
  those countries, so the new filter can be tried without an API key.

## [1.1.2] — 2026-10-20

### Changed
- **Windows now ships one `.exe`, not a ZIP** — `MAPLEAD-<version>-windows-x64.exe`.
  It is the desktop app and the terminal wizard in a single portable file:
  double-click for the window, `MAPLEAD.exe --cli --demo` (or any wizard flag) for
  the terminal. Nothing to unpack, nothing to install, no `_internal/` folder.
- One binary, two interfaces on both platforms: the Windows `.exe` now routes to the
  wizard exactly like the AppImage already did with `--cli`.
- The `.exe` uses the console subsystem on purpose — cmd only waits for, and only
  hands stdin to, console programs (a windowed build would fight cmd for the
  keyboard). The desktop path hides that console window again, unless a shell owns it.

### Removed
- `maplead-cli.exe`, `maplead.cmd`, `install.ps1` and `uninstall.ps1`: a single
  portable file has no folder to install or put on PATH.

## [1.1.1] — 2026-10-20

### Added
- The AppImage runs the terminal wizard with `--cli` (`MAPLEAD-*.AppImage --cli --demo`).
  The release assets now carry a working CLI on both platforms — `maplead-cli.exe` in
  the Windows ZIP, the same AppImage on Linux — without installing Python.

## [1.1.0] — 2026-10-20

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

[Unreleased]: https://github.com/DariusDev16/maplead/compare/v1.2.0...main
[1.2.0]: https://github.com/DariusDev16/maplead/releases/tag/v1.2.0
[1.1.3]: https://github.com/DariusDev16/maplead/releases/tag/v1.1.3
[1.1.2]: https://github.com/DariusDev16/maplead/releases/tag/v1.1.2
[1.1.1]: https://github.com/DariusDev16/maplead/releases/tag/v1.1.1
[1.1.0]: https://github.com/DariusDev16/maplead/releases/tag/v1.1.0
[1.0.0]: https://github.com/DariusDev16/maplead/releases/tag/v1.0.0
