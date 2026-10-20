"""
Rasterise packaging/maplead.svg into the PNG sizes an AppImage/desktop menu wants
and the multi-resolution .ico a Windows .exe needs.

    python packaging/render_icon.py

Pure Qt - no ImageMagick, no Pillow. The ICO container is assembled by hand
(PNG-compressed entries, supported by Windows Vista and later).
"""

from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "maplead.svg")
SIZES = (256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _render(renderer, size):
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QImage, QPainter

    image = QImage(QSize(size, size), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    return image


def _png_bytes(image) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _write_ico(images, target: str) -> bool:
    """Assemble a PNG-compressed .ico (each entry keeps its alpha channel)."""
    entries = []
    for image in images:
        size = image.width()
        entries.append((size, _png_bytes(image)))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    directory = b""
    blobs = b""
    for size, blob in entries:
        side = 0 if size >= 256 else size          # 0 means 256 in the ICO directory
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob

    try:
        with open(target, "wb") as fh:
            fh.write(header + directory + blobs)
    except OSError as exc:
        print(f"failed to write {target}: {exc}", file=sys.stderr)
        return False
    return True


def main() -> int:
    from PySide6.QtCore import QByteArray
    from PySide6.QtWidgets import QApplication
    from PySide6.QtSvg import QSvgRenderer

    app = QApplication(sys.argv[:1])              # needed by Qt (fonts, plugins)
    app.setApplicationName("MAPLEAD")              # noqa: F841 - needed by Qt
    with open(SVG, "rb") as fh:
        renderer = QSvgRenderer(QByteArray(fh.read()))
    if not renderer.isValid():
        print(f"invalid SVG: {SVG}", file=sys.stderr)
        return 1

    for size in SIZES:
        image = _render(renderer, size)
        target = os.path.join(HERE, f"maplead-{size}.png")
        if not image.save(target, "PNG"):
            print(f"failed to write {target}", file=sys.stderr)
            return 1
        print(f"  {target}")

    ico = os.path.join(HERE, "maplead.ico")
    if not _write_ico([_render(renderer, size) for size in ICO_SIZES], ico):
        return 1
    print(f"  {ico}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
