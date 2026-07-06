"""标题栏图标资源模块。

加载 gui/resources/icons/ 下的 SVG 矢量文件渲染为 QIcon。
美术师可直接用 Illustrator / Inkscape 等工具编辑 SVG 文件。

颜色说明：
    所有图标使用 CSS currentColor，程序加载时注入指定颜色。
    如需修改默认颜色，编辑本文件中 ICON_COLOR 变量即可。

依赖优先级：
    1. QtSvg (QSvgRenderer)  — 从 SVG 文件渲染（推荐）
    2. QPainter 绘制          — 无 QtSvg 或文件缺失时的自动兜底
"""

import os

from PyQt5.QtCore import QSize, Qt, QByteArray
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QPen, QColor, QBrush

try:
    from PyQt5.QtSvg import QSvgRenderer
    _HAS_SVG = True
except ImportError:
    _HAS_SVG = False


_RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_ICONS_DIR = os.path.join(_RESOURCE_DIR, "icons")

ICON_SIZE = QSize(16, 16)
ICON_COLOR = QColor("#c8c8c8")
RESTORE_BG = QColor("#121212")

_HIGHRES_SIZE = QSize(64, 64)


def _render_svg_pixmap(svg_bytes: QByteArray, size: QSize) -> QPixmap:
    pix = QPixmap(size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    renderer = QSvgRenderer(svg_bytes)
    if renderer.isValid():
        renderer.render(p)
    p.end()
    return pix


def _load_svg_icon(filename: str, color: str | None = None) -> QIcon | None:
    if not _HAS_SVG:
        return None
    path = os.path.join(_ICONS_DIR, filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            svg_text = f.read()
        color_css = color or ICON_COLOR.name()
        svg_text = svg_text.replace("currentColor", color_css)
        svg_bytes = QByteArray(svg_text.encode("utf-8"))

        icon = QIcon()
        icon.addPixmap(_render_svg_pixmap(svg_bytes, ICON_SIZE))
        icon.addPixmap(_render_svg_pixmap(svg_bytes, _HIGHRES_SIZE))
        return icon
    except Exception:
        return None


def _make_fallback_icon(draw_fn, color: QColor | None = None) -> QIcon:
    clr = color or ICON_COLOR
    icon = QIcon()

    for sz in [ICON_SIZE, _HIGHRES_SIZE]:
        w, h = sz.width(), sz.height()
        px = QPixmap(w, h)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        scale = w / 16.0
        pen_width = max(1, int(2 * scale))
        p.setPen(QPen(clr, pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        draw_fn(p, w, h, clr, scale)
        p.end()
        icon.addPixmap(px)
    return icon


def _fallback_close(p, w, h, c, scale):
    m = int(5 * scale)
    p.drawLine(m, m, w - m, h - m)
    p.drawLine(w - m, m, m, h - m)


def _fallback_maximize(p, w, h, c, scale):
    p.setBrush(Qt.NoBrush)
    pad = int(3 * scale)
    r = max(1, int(2 * scale))
    p.drawRoundedRect(pad, pad, w - 2 * pad, h - 2 * pad, r, r)


def _fallback_restore(p, w, h, c, scale):
    p.setBrush(QBrush(RESTORE_BG))
    pad1 = int(5 * scale)
    pad2 = int(2 * scale)
    sz = int(8 * scale)
    r = max(1, int(2 * scale))
    p.drawRoundedRect(pad1, pad1, sz, sz, r, r)
    p.drawRoundedRect(pad2, pad2, sz, sz, r, r)


def _fallback_minimize(p, w, h, c, scale):
    m = int(4 * scale)
    y = int(12 * scale)
    p.drawLine(m, y, w - m, y)


def build_close_icon(color: str | None = None) -> QIcon:
    icon = _load_svg_icon("close.svg", color)
    return icon if icon else _make_fallback_icon(_fallback_close, QColor(color) if color else None)


def build_maximize_icon(color: str | None = None) -> QIcon:
    icon = _load_svg_icon("maximize.svg", color)
    return icon if icon else _make_fallback_icon(_fallback_maximize, QColor(color) if color else None)


def build_restore_icon(color: str | None = None) -> QIcon:
    icon = _load_svg_icon("restore.svg", color)
    return icon if icon else _make_fallback_icon(_fallback_restore, QColor(color) if color else None)


def build_minimize_icon(color: str | None = None) -> QIcon:
    icon = _load_svg_icon("minimize.svg", color)
    return icon if icon else _make_fallback_icon(_fallback_minimize, QColor(color) if color else None)


def get_app_icon_path() -> str:
    """获取主程序图标文件的绝对路径。

    图标位于 gui/resources/icons/ico.ico，
    支持 PyInstaller 打包后的运行环境（_MEIPASS）。
    """
    import sys
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    elif getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(base, "ico.ico")
    if os.path.exists(icon_path):
        return icon_path
    icon_path = os.path.join(base, "icons", "ico.ico")
    return icon_path
