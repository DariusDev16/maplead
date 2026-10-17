"""
Rasterise packaging/maplead.svg into the PNG sizes an AppImage/desktop menu wants.

    python packaging/render_icon.py
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "maplead.svg")
SIZES = (256, 512, 1024)


def main() -> int:
    from PySide6.QtCore import QByteArray, QSize, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtWidgets import QApplication
    from PySide6.QtSvg import QSvgRenderer

    app = QApplication(sys.argv[:1])              # noqa: F841 - needed by Qt
    renderer = QSvgRenderer(QByteArray(open(SVG, "rb").read()))
    if not renderer.isValid():
        print(f"invalid SVG: {SVG}", file=sys.stderr)
        return 1

    for size in SIZES:
        image = QImage(QSize(size, size), QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        target = os.path.join(HERE, f"maplead-{size}.png")
        if not image.save(target, "PNG"):
            print(f"failed to write {target}", file=sys.stderr)
            return 1
        print(f"  {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())