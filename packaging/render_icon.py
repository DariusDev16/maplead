"""
Rasterise packaging/maplead.svg into the icon formats the platforms want.

    python packaging/render_icon.py

Produces PNGs (256/512/1024, plus a 256px master) and an .ico for Windows -
PyInstaller on Windows takes an .ico directly, so the build never needs Pillow.
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


def _render(size: int):
    """Render the SVG at `size`x`size` and return (QApplication, QImage)."""
    from PySide6.QtCore import QByteArray, QSize, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from PySide6.QtSvg import QSvgRenderer

    app = QApplication.instance() or QApplication(sys.argv[:1])
    renderer = QSvgRenderer(QByteArray(open(SVG, "rb").read()))
    if not renderer.isValid():
        raise SystemExit(f"invalid SVG: {SVG}")

    image = QImage(QSize(size, size), QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    return app, image


def write_ico() -> str:
    """A Vista+ .ico: one PNG-encoded entry per size (no Pillow needed)."""
    from PySide6.QtCore import QBuffer

    images = []
    for size in ICO_SIZES:
        _, image = _render(size)
        buffer = QBuffer()
        buffer.open(QBuffer.WriteOnly)
        image.save(buffer, "PNG")
        images.append((size, bytes(buffer.data())))
        buffer.close()

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        dim = 0 if size >= 256 else size                 # 0 means 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)

    path = os.path.join(HERE, "maplead.ico")
    with open(path, "wb") as fh:
        fh.write(header + entries + blobs)
    return path


def main() -> int:
    _, image = _render(SIZES[0])
    for size in SIZES:
        _, current = _render(size)
        target = os.path.join(HERE, f"maplead-{size}.png")
        if not current.save(target, "PNG"):
            print(f"failed to write {target}", file=sys.stderr)
            return 1
        print(f"  {target}")
    master = os.path.join(HERE, "maplead.png")
    image.save(master, "PNG")
    print(f"  {master}")
    print(f"  {write_ico()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())