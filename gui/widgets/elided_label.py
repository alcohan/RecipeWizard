'''A one-line label that shortens its text with "…" to whatever width
the layout gives it, and shows the full text as a tooltip when cut.

Eliding happens at paint time against the label's real font and width
(a stylesheet font applies only once the widget is polished, so
measuring up front cuts at the wrong place). Its minimum width is
tiny, so a long name never pushes its layout wider than the panel.
'''
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QSizePolicy

from gui.widgets.text_fit import elide, overflows


class ElidedLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self._full = ''
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setText(text)

    def setText(self, text):
        self._full = text or ''
        super().setText(self._full)
        self._sync_tooltip()

    def full_text(self):
        return self._full

    def minimumSizeHint(self):
        return QSize(16, super().minimumSizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_tooltip()

    def _sync_tooltip(self):
        cut = overflows(self.font(), self._full, self.contentsRect().width())
        self.setToolTip(self._full if cut else '')

    def paintEvent(self, _event):
        painter = QPainter(self)
        rect = self.contentsRect()
        text = elide(self.font(), self._full, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment() | Qt.TextSingleLine), text)
