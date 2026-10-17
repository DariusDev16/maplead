# Contributing to MAPLEAD

Thanks for helping out. This is a small, friendly codebase — the bar is "would this
be obvious to the next person reading it in a year?".

## Ground rules

1. **The terminal wizard stays dependency-free.** `maplead.py`, `maplead/cli.py` and
   everything they import must run on a bare Python 3.9+. PySide6 belongs in
   `maplead/gui/` only. A CI job enforces this.
2. **`engine.py` stays UI-agnostic.** It takes a plan, calls providers, returns
   `(leads, report)`. Progress and cancellation are callbacks.
3. **Never commit secrets.** `.env` is gitignored. Keys belong in
   `~/.config/maplead/.env` (mode 600) or in the environment.
4. **No new runtime dependencies** in the engine/exporters. The xlsx writer, the HTTP
   client and the TUI are all hand-rolled on the standard library for exactly this
   reason.

## Getting set up

```bash
git clone https://github.com/DariusDev16/maplead.git && cd maplead

# terminal wizard: nothing to install
./maplead.py --demo

# desktop app
python3 -m venv .venv-gui
.venv-gui/bin/python -m pip install PySide6-Essentials pyinstaller
./maplead-gui.py
```

## Before you push

```bash
# 1. compiles + engine end-to-end
python3 -m compileall -q maplead
./maplead.py --demo --country Germany --city Berlin --business dentist \
             --fields rec --limit 40 --format xlsx --outdir /tmp/maplead-check

# 2. GUI self-test (headless is fine)
QT_QPA_PLATFORM=offscreen ./maplead-gui.py --selftest

# 3. optional: build and smoke-test the AppImage
./build-appimage.sh
```

Both commands must print `OK`. If you touched the field catalogue, the exporters or a
provider, also try the affected path with `--provider demo` and with a real key you
have locally.

## Pull requests

- one topic per PR;
- say what you changed and how you verified it;
- screenshots for UI changes (dark theme at least);
- update `docs/` and the README when behaviour changes;
- keep commits readable (`git rebase -i` over `git merge`).

## Reporting bugs

Please include: MAPLEAD version, Linux distro, how you launched it, the provider used,
and the output of:

```bash
maplead --selftest
MAPLEAD_DEBUG=1 ./maplead.py --demo ...   # whatever reproduces it
```

## Legal note

This tool reads public business listings through third-party APIs. Do not add
features that circumvent a provider's limits or terms, and do not add scraping that
bypasses a site's access controls. PRs that do will not be merged.

## License

By contributing you agree that your work is licensed under the [MIT License](../LICENSE).