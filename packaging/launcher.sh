#!/usr/bin/env bash
#
# MAPLEAD launcher.
#
# Runs the AppImage the normal way when the system has FUSE (libfuse.so.2).
# When it does not - containers, servers, distros that ship FUSE 3 only - it
# unpacks the image once into @CACHE@ and runs straight from there, so there
# is no FUSE, no loop device and no root anywhere in the picture.
#
#   maplead                  normal start
#   maplead --selftest       headless self-check
#   MAPLEAD_NO_FUSE=1 ...    always take the unpacked path
#
set -u

APP="@APP@"
CACHE="@CACHE@"

have_fuse() {
    case "${MAPLEAD_NO_FUSE:-0}" in
        1|true|yes|on) return 1 ;;
    esac
    if command -v ldconfig >/dev/null 2>&1; then
        ldconfig -p 2>/dev/null | grep -q 'libfuse\.so\.2' && return 0
        return 1
    fi
    local dir
    for dir in /lib/x86_64-linux-gnu /usr/lib/x86_64-linux-gnu /lib64 /usr/lib64 \
               /usr/local/lib /lib /usr/lib /usr/lib/x86_64-linux-gnu; do
        if [ -e "$dir/libfuse.so.2" ]; then
            return 0
        fi
    done
    return 1
}

unpack() {
    local tmp
    tmp="$(mktemp -d)" || return 1
    ( cd "$tmp" && "$APP" --appimage-extract >/dev/null 2>&1 ) || { rm -rf "$tmp"; return 1; }
    mkdir -p "$(dirname "$CACHE")" || { rm -rf "$tmp"; return 1; }
    rm -rf "$CACHE"
    mv "$tmp/squashfs-root" "$CACHE" || { rm -rf "$tmp"; return 1; }
    rm -rf "$tmp"
    return 0
}

if [ ! -f "$APP" ]; then
    echo "MAPLEAD: app image not found: $APP" >&2
    echo "         rebuild it with:  ~/maplead/build-appimage.sh" >&2
    exit 127
fi

if have_fuse; then
    exec "$APP" "$@"
fi

# no libfuse2: unpack once (fast, ~1s) and reuse the copy afterwards
if [ ! -x "$CACHE/AppRun" ] || [ "$APP" -nt "$CACHE/AppRun" ]; then
    if ! unpack; then
        echo "MAPLEAD: could not unpack $APP" >&2
        exit 1
    fi
fi

exec "$CACHE/AppRun" "$@"