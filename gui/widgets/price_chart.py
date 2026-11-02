'''Step chart of an ingredient's unit price over time — the inspector's
sparkline and the Edit ingredient dialog's price chart.

A price holds until the next one takes effect, so the line steps
rather than slopes. Dates are spaced by time; the last point gets a
dot. Painted directly (no matplotlib), so it costs nothing to build.
'''
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget


_ROMAINE = '#347200'
_RULE = '#ebe1cd'


class PriceStepChart(QWidget):
    def __init__(self, height=40, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._points = []

    def set_prices(self, prices):
        '''`prices`: iterable of (iso date, unit price), any order.'''
        pts = []
        for d, p in prices:
            try:
                pts.append((date.fromisoformat(str(d)[:10]), float(p)))
            except (TypeError, ValueError):
                continue
        self._points = sorted(pts)
        self.setToolTip(', '.join(f'${p:.3f} {d:%b %d}' for d, p in self._points[-6:]))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 4
        p.setPen(QPen(QColor(_RULE), 1))
        p.drawLine(0, h - 2, w, h - 2)
        if not self._points:
            return
        pts = list(self._points)
        today = date.today()
        if pts[-1][0] < today:
            pts.append((today, pts[-1][1]))   # the current price holds to today
        t0, t1 = pts[0][0].toordinal(), pts[-1][0].toordinal()
        lo = min(v for _d, v in pts)
        hi = max(v for _d, v in pts)
        span_t = max(1, t1 - t0)
        span_v = hi - lo

        def xy(d, v):
            x = pad + (d.toordinal() - t0) / span_t * (w - 2 * pad)
            y = (h / 2) if span_v < 1e-9 else pad + (hi - v) / span_v * (h - 2 * pad - 2)
            return QPointF(x, y)

        path = QPainterPath(xy(*pts[0]))
        for i in range(1, len(pts)):
            prev = xy(*pts[i - 1])
            cur = xy(*pts[i])
            path.lineTo(QPointF(cur.x(), prev.y()))
            path.lineTo(cur)
        p.setPen(QPen(QColor(_ROMAINE), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        last = xy(*self._points[-1])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_ROMAINE))
        p.drawEllipse(QRectF(last.x() - 3, last.y() - 3, 6, 6))
