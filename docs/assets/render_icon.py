from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs" / "assets" / "mediasift.svg"
PNG = ROOT / "docs" / "assets" / "mediasift.png"
ICO = ROOT / "docs" / "assets" / "mediasift.ico"
APP_PNG = ROOT / "mediasift" / "assets" / "mediasift.png"


def render() -> None:
    renderer = QSvgRenderer(QByteArray(SOURCE.read_bytes()))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {SOURCE}")
    image = QImage(QSize(512, 512), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Qt could not render icon PNG")
    PNG.write_bytes(bytes(buffer.data()))
    APP_PNG.parent.mkdir(parents=True, exist_ok=True)
    APP_PNG.write_bytes(PNG.read_bytes())

    with Image.open(PNG) as source:
        source.save(ICO, format="ICO", sizes=[(size, size) for size in (16, 32, 48, 64, 128, 256)])
    print(f"Rendered {PNG}, {ICO}, and {APP_PNG}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render MediaSift SVG into PNG and Windows ICO assets")
    parser.parse_args()
    render()
