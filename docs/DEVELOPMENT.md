# MAPLEAD — Development

How the project is put together, how to build it, and how a release is cut.

- [Architecture](#architecture)
- [Layout](#layout)
- [Running from source](#running-from-source)
- [Building the AppImage](#building-the-appimage)
- [The no-FUSE launcher](#the-no-fuse-launcher)
- [Self-test](#self-test)
- [CI and releases](#ci-and-releases)
- [Adding a provider](#adding-a-provider)
- [Regenerating the screenshots](#regenerating-the-screenshots)

---

## Architecture

One engine, two front-ends.

```
                 ┌──────────────┐        ┌──────────────┐
   terminal  ───▶│ maplead.cli  │        │ maplead.gui  │───▶ Qt6 window
                 │ (stdlib TUI) │        │ (PySide6)    │
                 └──────┬───────┘        └──────┬───────┘
                        │                       │ QThread
                        └───────────┬───────────┘
                                    ▼
                            maplead.engine        query planning, harvest, dedupe, filters
                                    │
             ┌──────────────────────┼──────────────────────┐
             ▼                      ▼                      ▼
      maplead.providers      maplead.data          maplead.exporters
   Google/Outscraper/SerpApi  countries, cities,   csv tsv json xlsx txt html
   DataForSEO/demo           verticals, fields    (xlsx written by hand)
                                    │
                              maplead.net         urllib client: retries, backoff
```

Rules that keep it honest:

- **`engine.py` knows nothing about pixels.** It takes a `SearchPlan`, calls a
  provider, and returns `(leads, HarvestReport)`. Progress is a callback; cancellation
  is a `should_stop()` callback. That is the whole contract with both front-ends.
- **Providers normalise.** Every provider returns the same lead dict shape
  (`providers._blank()`), so exporters and the table never special-case a source.
- **Field availability is declared, not guessed.** Each field in `data/fields.py`
  lists the providers that can return it; both front-ends use that list to grey out
  what is impossible instead of silently exporting empty columns.
- **The CLI keeps zero dependencies.** `maplead.py` must run on a bare Python 3.9+
  with nothing installed. Only `maplead/gui/` may import PySide6.

## Layout

```
maplead.py              terminal launcher
maplead-gui.py          desktop launcher
maplead/
  cli.py                terminal wizard, flags, reporting
  engine.py             query planning, harvesting, dedupe, filters
  providers.py          Google / Outscraper / SerpApi / DataForSEO / demo
  exporters.py          csv tsv json xlsx txt html (hand-rolled xlsx writer)
  net.py                urllib JSON client: retries, backoff, error extraction
  ui.py                 terminal prompts, multi-column lists, tables, progress
  art.py                ASCII/Unicode art, colours, gradients
  paths.py              XDG config/data locations, .env load/save/clear
  data/                 countries · cities · verticals · field catalogue
  gui/
    app.py              entry point, theme bootstrap, --selftest
    main_window.py      window: form, stats, table, activity log
    widgets.py          cards, searchable combo, field picker, table model
    keys.py             API key manager (paste · verify live · save)
    worker.py           harvest + key validation on a QThread
    icons.py            inline SVG icon set (no image files)
    theme.py            dark/light palettes and the stylesheet
packaging/              icon (svg+png), .desktop file, PyInstaller spec, launcher
tools/screenshots.py    regenerates docs/screenshots/*
build-appimage.sh       one-command AppImage build (+ optional --install)
docs/                   user guide, development notes and screenshots
```

## Running from source

```bash
python3 -m venv .venv-gui && .venv-gui/bin/python -m pip install PySide6-Essentials

./maplead.py --demo        # terminal wizard (needs no venv at all)
./maplead-gui.py           # desktop
./maplead-gui.py --selftest
```

On Debian, `python3 -m venv` sometimes ships without `ensurepip`; bootstrap pip with
`get-pip.py` (the build script does this for you).

## Building the AppImage

```bash
./build-appimage.sh                 # build + smoke test
./build-appimage.sh --install       # …and install to ~/.local/bin + app menu
./build-appimage.sh --no-test       # skip the smoke test
MAPLEAD_OUTDIR=~/bin ./build-appimage.sh      # somewhere else
```

What it does, in order:

1. creates/updates `.venv-gui` (PySide6-Essentials + PyInstaller);
2. renders the PNG icons from `packaging/maplead.svg` (Qt does the rasterising — no
   ImageMagick, no Pillow);
3. generates the `.desktop` entry (`Exec=AppRun`, replaced at install time);
4. runs PyInstaller with `packaging/maplead.spec` — a `onedir` build, because startup
   speed matters more than a single file once we are already inside a squashfs;
5. assembles an AppDir (`usr/lib/maplead`, icons, desktop file) and copies the small
   X11/GL libraries desktops tend to lack;
6. runs `appimagetool` to produce `~/Apps/MAPLEAD-<version>-x86_64.AppImage`;
7. runs the self-test **inside** the produced image.

### Trimming the bundle

`packaging/maplead.spec` excludes the Qt modules the app never imports (QML, Quick,
WebEngine, Multimedia, 3D, Charts, Sql, …), which takes the bundle from ~300 MB to
~160 MB uncompressed. Add to `EXCLUDES` freely; re-run the self-test afterwards to be
sure nothing was needed after all.

## The no-FUSE launcher

`packaging/launcher.sh` becomes `~/Apps/maplead`. It checks for `libfuse.so.2`
(`ldconfig -p`, then the usual library directories), and when it is missing unpacks the
AppImage once with `--appimage-extract` into `~/.maplead-runtime/` and runs its
`AppRun`. The cache is invalidated by comparing timestamps against the image.

## Self-test

`maplead-gui --selftest` runs headless (`QT_QPA_PLATFORM=offscreen` works, a real
display is optional) and verifies: the window builds, the demo engine returns leads,
the xlsx is written, the table model matches the result set, the searchable combo
filters, the field picker applies presets and locks unavailable fields, and the keys
dialog renders every provider. This is what CI runs and what the build script runs
against the finished AppImage.

```bash
QT_QPA_PLATFORM=offscreen ./maplead-gui.py --selftest
MAPLEAD_DEBUG=1 ./maplead-gui.py --selftest     # full tracebacks
```

## Publishing without a system git

Locked-down desktops sometimes have neither a system git nor an SSH client, and
`git push` over HTTPS needs `libcurl-gnutls` matching the local glibc. In that
situation `tools/publish.py` pushes over the REST API with `curl` alone:

```bash
read -rs TOKEN && printf '%s' "$TOKEN" > ~/.maplead-github-token && chmod 600 ~/.maplead-github-token
python3 tools/publish.py --repo maplead      # creates the repo if needed, then pushes
rm -f ~/.maplead-github-token
```

It uploads the files git is tracking (blobs for binaries, inline content for text),
creates the commit and points `main` at it. Re-running is safe.

## CI and releases

- **CI** (`.github/workflows/ci.yml`): on push and pull requests — compile-check every
  module, run the terminal demo end to end, and run the GUI self-test with
  `PySide6-Essentials` on Linux.
- **Release** (`.github/workflows/release.yml`): on a `v*` tag — build the AppImage and
  attach it to a GitHub Release. Bump `VERSION` in `maplead/art.py` first; everything
  else (file name, window title, About box) reads from there.

## Adding a provider

1. Subclass `Provider` in `providers.py`: `name`, `label`, `env_keys`, `homepage`,
   `per_query_cap`, `validate()` (a cheap live call) and `search()` returning
   `SearchResult(leads=[...])` filled through `_blank()`.
2. Register it in `PROVIDERS` and `ORDER`.
3. Add its id to the provider tuples in `data/fields.py` for the fields it can return.
4. Nothing else: both front-ends read those three places.

Keep `providers.py` free of printing — the front-ends own all output.

## Regenerating the screenshots

```bash
./.venv-gui/bin/python tools/screenshots.py        # needs a display (DISPLAY=:0)
```

It restores your saved window state afterwards and replaces real API keys with a fake
one before grabbing, so regenerating the docs never leaks a key and never disturbs your
session. Terminal screenshots are produced separately with an `xterm` fullscreen run
piped through `script -qec` (which keeps the colours).