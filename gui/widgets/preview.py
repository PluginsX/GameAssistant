"""预览控件。

提供宽度自适应、高度按比例自动计算的游戏画面预览组件。
"""

from PyQt5.QtCore import Qt, QRect, QSize
from PyQt5.QtGui import QImage, QPainter, QPen, QColor
from PyQt5.QtWidgets import QSizePolicy, QWidget


class PreviewWidget(QWidget):
    """宽度随窗口变化，高度自动根据游戏画面比例调整的预览控件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 宽度 Expanding 撑满布局，高度 Preferred 以匹配 heightForWidth 建议值
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setStyleSheet(
            "PreviewWidget { background: #0a0a0a; border: none; }"
        )

        self._qimage = QImage()
        self._error_text: str | None = None
        self._aspect_ratio = 16.0 / 9.0  # 默认无图时的宽高比

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width: int) -> int:
        return int(width / self._aspect_ratio)

    def sizeHint(self):
        w = self.width() if self.width() > 0 else 400
        return QSize(w, int(w / self._aspect_ratio))

    def set_image(self, qimage: QImage):
        self._qimage = qimage
        self._error_text = None

        # 获取最新的真实比例并更新布局
        if not qimage.isNull() and qimage.height() > 0:
            new_ratio = qimage.width() / qimage.height()
            if abs(new_ratio - self._aspect_ratio) > 0.01:
                self._aspect_ratio = new_ratio
                self.updateGeometry()

        self.update()

    def set_error(self, message: str):
        self._qimage = QImage()
        self._error_text = message
        self.update()

    def current_image(self) -> QImage:
        return self._qimage

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()
        painter.fillRect(rect, QColor("#0a0a0a"))

        if self._error_text:
            painter.setPen(QPen(QColor("#FF6666")))
            painter.drawText(rect, Qt.AlignCenter, self._error_text)
            return

        if self._qimage.isNull():
            return

        img_w = self._qimage.width()
        img_h = self._qimage.height()
        view_w = rect.width()
        view_h = rect.height()

        scale = min(view_w / img_w, view_h / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        x = (view_w - new_w) // 2
        y = (view_h - new_h) // 2

        painter.drawImage(QRect(x, y, new_w, new_h), self._qimage)
