#!/usr/bin/env bash
#
# Build MAPLEAD Desktop into a single-file AppImage (Linux x86_64).
#
#   ./build-appimage.sh              build + smoke test
#   ./build-appimage.sh --no-test    build only
#
# Requires: python3 >= 3.10, ~1.5 GB of disk for the Qt bundle.
# Everything is installed into the project-local .venv-gui - no sudo, no
# system packages touched.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.venv-gui"
PY="$VENV/bin/python"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
APPDIR="$BUILD/maplead.AppDir"
# The AppImage is a *product*, not source: it is written OUTSIDE the project so
# `git clean`, `rm -rf` or a stray cleanup never eat it.
OUTDIR="${MAPLEAD_OUTDIR:-$HOME/Apps}"
# where --install puts the launcher and the menu entry (also used in the summary)
bin="${XDG_BIN_HOME:-$HOME/.local/bin}"
apps="${XDG_DATA_HOME:-$HOME/.local/share}"
NAME="MAPLEAD"
BIN_NAME="maplead"
ICON_NAME="maplead"
ARCH="${ARCH:-x86_64}"
DESKTOP_ID="io.github.maplead.Desktop"
TOOLS="$BUILD/tools"
APPIMAGETOOL="$TOOLS/appimagetool-x86_64.AppImage"

VERSION="$(python3 - <<'PY'
import re, pathlib
print(re.search(r'VERSION = "([^"]+)"',
                pathlib.Path("maplead/art.py").read_text()).group(1))
PY
)"

RUN_TEST=1
DO_INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --no-test) RUN_TEST=0 ;;
    --install) DO_INSTALL=1 ;;
  esac
done

say() { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }

# locate a shared library by soname without ldconfig (not present in minimal images)
find_lib() {
  local so="$1"
  for dir in /lib/"$(uname -m)"-linux-gnu /usr/lib/"$(uname -m)"-linux-gnu \
             /lib64 /usr/lib64 /usr/lib /lib /usr/local/lib; do
    if [[ -e "$dir/$so" ]]; then
      printf '%s' "$dir/$so"
      return 0
    fi
  done
  return 1
}

# --------------------------------------------------------------------------- #
say "1/7  python environment"
# --------------------------------------------------------------------------- #
if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV" || true
  if ! "$PY" -m pip --version >/dev/null 2>&1; then
    # Debian splits ensurepip into python3-venv; bootstrap pip by hand
    tmp="$(mktemp -d)"
    curl -sSL -o "$tmp/get-pip.py" https://bootstrap.pypa.io/get-pip.py
    "$PY" "$tmp/get-pip.py" -q
    rm -rf "$tmp"
  fi
fi
if ! "$PY" -c "import PySide6" >/dev/null 2>&1; then
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q "PySide6-Essentials>=6.8" pyinstaller
fi
"$PY" -c "import PySide6; from PySide6 import QtCore; print('    PySide6', QtCore.__version__)"

# --------------------------------------------------------------------------- #
say "2/7  icons"
# --------------------------------------------------------------------------- #
mkdir -p packaging
QT_QPA_PLATFORM=offscreen "$PY" packaging/render_icon.py
cp packaging/maplead-512.png packaging/maplead.png

# --------------------------------------------------------------------------- #
say "3/7  desktop entry"
# --------------------------------------------------------------------------- #
mkdir -p "$BUILD"
# inside an AppDir the launcher is AppRun - the desktop tools swap it for the
# real AppImage path when the file is installed
sed -e "s|^Exec=.*|Exec=AppRun|" \
    -e "s|^Icon=.*|Icon=$ICON_NAME|" \
    -e "s|^TryExec=.*|TryExec=AppRun|" \
    packaging/maplead.desktop > "$BUILD/$ICON_NAME.desktop"

# --------------------------------------------------------------------------- #
say "4/7  pyinstaller (this is the slow part)"
# --------------------------------------------------------------------------- #
rm -rf "$DIST/maplead" "$ROOT/build/maplead"
"$PY" -m PyInstaller --noconfirm --clean \
    --distpath "$DIST" --workpath "$BUILD/work" \
    packaging/maplead.spec

# --------------------------------------------------------------------------- #
say "5/7  AppDir"
# --------------------------------------------------------------------------- #
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
         "$APPDIR/usr/share/maplead"

cp -a "$DIST/maplead" "$APPDIR/usr/lib/$BIN_NAME"
cp packaging/maplead.svg "$APPDIR/usr/share/maplead/"
cp packaging/maplead.png "$APPDIR/$ICON_NAME.png"
cp packaging/maplead-256.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/$ICON_NAME.png"
cp packaging/maplead-512.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/$ICON_NAME.png"
cp "$BUILD/$ICON_NAME.desktop" "$APPDIR/$ICON_NAME.desktop"
ln -sf "../$ICON_NAME.desktop" "$APPDIR/usr/share/applications/$ICON_NAME.desktop"

# --------------------------------------------------------------------------- #
say "5b/7 bundling the small libs desktops tend to be missing"
# --------------------------------------------------------------------------- #
# Qt loads its X11/wayland plugins through libqxcb.so, whose DT_NEEDED list is
# not satisfied on a bare Ubuntu/Fedora box. These are all tiny, permissively
# licensed and identical across distros, so ship them inside the AppImage.
LIBDIR="$APPDIR/usr/lib/$BIN_NAME/lib"
mkdir -p "$LIBDIR"
BUNDLED=0
for so in libEGL.so.1 libGL.so.1 libGLdispatch.so.0 libGLX.so.0 \
          libxcb-cursor.so.0 libxcb-icccm.so.4 libxcb-image.so.0 libxcb-keysyms.so.1 \
          libxcb-randr.so.0 libxcb-render-util.so.0 libxcb-shape.so.0 \
          libxcb-xinerama.so.0 libxcb-xkb.so.1 libxkbcommon-x11.so.0 \
          libX11-xcb.so.1 libb2.so.1 libmd4c.so.0 libdrm.so.2; do
  src="$(find_lib "$so" || true)"
  if [[ -n "$src" ]]; then
    cp -L "$src" "$LIBDIR/$so"
    BUNDLED=$((BUNDLED + 1))
  fi
done
echo "    $BUNDLED extra libraries bundled"

# nothing critical left dangling?
if command -v ldd >/dev/null; then
  missing=$(LD_LIBRARY_PATH="$APPDIR/usr/lib/$BIN_NAME:$LIBDIR" \
            ldd "$APPDIR/usr/lib/$BIN_NAME/PySide6/Qt/plugins/platforms/libqxcb.so" 2>/dev/null \
            | awk '/not found/ {print $1}' | sort -u || true)
  if [[ -n "$missing" ]]; then
    echo "    note: still resolved from the host system: $(echo "$missing" | tr '\n' ' ')"
  fi
fi

# AppRun: keep the Qt plugins on the library path, then exec the frozen app
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
# MAPLEAD Desktop - AppImage entry point
HERE="$(dirname "$(readlink -f "${0}")")"
APPDIR="$HERE/usr/lib/maplead"
export PATH="${APPDIR}:${PATH}"
export LD_LIBRARY_PATH="${APPDIR}/lib:${APPDIR}:${LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="${APPDIR}/PySide6/plugins:${QT_PLUGIN_PATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export QT_AUTO_SCREEN_SCALE_FACTOR="${QT_AUTO_SCREEN_SCALE_FACTOR:-1}"
exec "${APPDIR}/maplead" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# --------------------------------------------------------------------------- #
say "6/7  appimagetool"
# --------------------------------------------------------------------------- #
mkdir -p "$TOOLS"
if [[ ! -x "$APPIMAGETOOL" ]]; then
  echo "    downloading appimagetool…"
  curl -sSL -o "$APPIMAGETOOL" \
    https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$APPIMAGETOOL"
fi

mkdir -p "$OUTDIR"
OUT="$OUTDIR/${NAME}-${VERSION}-${ARCH}.AppImage"

# appimagetool needs FUSE; containers usually do not, so fall back to extract+run
run_appimagetool() {
  ARCH="$ARCH" "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUT"
}
if ! run_appimagetool 2>"$BUILD/appimage.log"; then
  echo "    retrying without FUSE…"
  APPIMAGE_EXTRACT_AND_RUN=1 run_appimagetool
fi
chmod +x "$OUT"

# --------------------------------------------------------------------------- #
say "7/7  smoke test"
# --------------------------------------------------------------------------- #
ls -lh "$OUT"
if [[ "$RUN_TEST" == "1" ]]; then
  run_app() { "$@" --selftest; }
  if ! run_app "$OUT" >"$BUILD/selftest.log" 2>&1; then
    if ! APPIMAGE_EXTRACT_AND_RUN=1 run_app "$OUT" >"$BUILD/selftest.log" 2>&1; then
      echo "!! selftest failed:"; tail -30 "$BUILD/selftest.log"; exit 1
    fi
  fi
  tail -12 "$BUILD/selftest.log"

  # the same file also carries the terminal wizard (`--cli`)
  run_cli() {
    "$@" --cli --demo --country Germany --city Berlin --business dentist \
         --fields rec --limit 5 --format csv --outdir "$BUILD/cli-leads"
  }
  if ! run_cli "$OUT" >"$BUILD/selftest-cli.log" 2>&1; then
    if ! APPIMAGE_EXTRACT_AND_RUN=1 run_cli "$OUT" >>"$BUILD/selftest-cli.log" 2>&1; then
      echo "!! CLI selftest failed:"; tail -30 "$BUILD/selftest-cli.log"; exit 1
    fi
  fi
  tail -3 "$BUILD/selftest-cli.log"
fi

say "done"

if [[ "$DO_INSTALL" == "1" ]]; then
  # --- launcher + PATH + application menu -------------------------------- #
  mkdir -p "$bin" "$apps/applications" \
           "$apps/icons/hicolor/512x512/apps" "$apps/icons/hicolor/256x256/apps"

  # a wrapper that copes with machines that have no libfuse2
  LAUNCHER="$OUTDIR/$BIN_NAME"
  sed -e "s|@APP@|$OUT|g" -e "s|@CACHE@|$OUTDIR/.$BIN_NAME-runtime|g" \
      packaging/launcher.sh > "$LAUNCHER"
  chmod +x "$LAUNCHER"

  # symlink, not a copy: one single file to keep up to date
  rm -f "$bin/$BIN_NAME"
  ln -s "$LAUNCHER" "$bin/$BIN_NAME"

  sed -e "s|^Exec=.*|Exec=$LAUNCHER|" \
      -e "s|^TryExec=.*|TryExec=$LAUNCHER|" \
      packaging/maplead.desktop > "$apps/applications/$DESKTOP_ID.desktop"
  install -m 644 packaging/maplead-512.png "$apps/icons/hicolor/512x512/apps/$ICON_NAME.png"
  install -m 644 packaging/maplead-256.png "$apps/icons/hicolor/256x256/apps/$ICON_NAME.png"
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps/applications" >/dev/null 2>&1 || true
  fi
  echo "  instalado:  $OUT"
  echo "  lançador:   $LAUNCHER"
  echo "  no PATH:    $bin/$BIN_NAME -> $LAUNCHER"
  echo "  no menu:    MAPLEAD"
fi

cat <<EOF

  $OUT

  rodar:     $bin/$BIN_NAME     (após --install)
            ou dê dois cliques no atalho MAPLEAD do menu
  sem FUSE:  o lançador descompacta o AppImage em $OUTDIR/.$BIN_NAME-runtime
            e roda dali - nenhuma permissão especial necessária
  chaves:    ~/.config/maplead/.env
  exports:   ~/Documents/maplead/

EOF