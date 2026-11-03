'''Analytics chart: one stacked bar per recipe, a slice per ingredient
category in the category colors, on a shared axis, per the Framework
canvas. Each row is the recipe's wedge, its name, the bar and its total;
hovering a slice says what it is. Fed by utilities.compare.build().
'''
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolTip, QVBoxLayout, QWidget

from gui.widgets.elided_label import ElidedLabel
from utilities import compare


_KALE = '#082c00'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_NAME_W = 200
_VALUE_W = 84
_GAP = 2


class CompareChart(QWidget):
    recipeActivated = Signal(int)

    def __init__(self, thumb_factory, parent=None):
        '''thumb_factory(recipe_id, size) returns a widget showing the wedge.'''
        super().__init__(parent)
        self._thumb = thumb_factory
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self.rows = []

    def set_data(self, data):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.rows = []
        pct = data['values'] == 'pct'
        metric = data['metric']
        if pct:
            scale = 100.0
            ticks = [0.0, 25.0, 50.0, 75.0, 100.0]
        else:
            top = max((sum(s[1] for s in r['segments']) for r in data['recipes'] if r['total'] is not None),
                      default=0.0)
            ticks = compare.nice_ticks(top)
            scale = ticks[-1]
        colors = dict(data['categories'])
        for r in data['recipes']:
            missing = 'No menu price' if data['basis'] == 'price' else 'No weight'
            row = _ChartRow(r, colors, scale, metric, pct, self._thumb(r['id'], 36), missing)
            row.activated.connect(self.recipeActivated.emit)
            self._layout.addWidget(row)
            self.rows.append(row)
        axis_text = [compare.fmt_metric(t, metric, 'pct' if pct else 'amount') for t in ticks]
        if not pct and metric == 'cost':
            axis_text = ['$0' if t == 0 else compare.fmt(t, '$') for t in ticks]
        self.axis = _Axis(axis_text)
        axis_row = QHBoxLayout()
        axis_row.setContentsMargins(0, 0, 0, 0)
        axis_row.setSpacing(14)
        axis_row.addSpacing(_NAME_W)
        axis_row.addWidget(self.axis, stretch=1)
        axis_row.addSpacing(_VALUE_W)
        holder = QWidget()
        holder.setLayout(axis_row)
        self._layout.addWidget(holder)


class _ChartRow(QWidget):
    activated = Signal(int)

    def __init__(self, recipe, colors, scale, metric, pct, thumb, missing, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe['id']
        self.setToolTip('Double-click to open')
        name = ElidedLabel(recipe['name'] + (' · archived' if recipe['archived'] else ''))
        name.setStyleSheet(f"color: {_MUTED if recipe['archived'] else _KALE}; font-weight: 500;")
        left = QHBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(10)
        left.addWidget(thumb)
        left.addWidget(name, stretch=1)
        left_w = QWidget()
        left_w.setFixedWidth(_NAME_W)
        left_w.setLayout(left)

        self.bar = _StackedBar(recipe, colors, scale, metric, pct)
        if recipe['total'] is None:
            self.value = QLabel(missing)
            self.value.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        else:
            self.value = QLabel(compare.fmt_metric(recipe['total'], metric))
            self.value.setStyleSheet(f'color: {_KALE}; font-weight: 600;')
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.value.setFixedWidth(_VALUE_W)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(left_w)
        layout.addWidget(self.bar, stretch=1)
        layout.addWidget(self.value)

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self.recipe_id)
        super().mouseDoubleClickEvent(event)


class _StackedBar(QWidget):
    def __init__(self, recipe, colors, scale, metric, pct, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self._recipe = recipe
        self._colors = colors
        self._scale = scale or 1.0
        self._metric = metric
        self._pct = pct
        self._rects = []

    def segments(self):
        '''[(category, value, share)] actually drawn (no basis = none).'''
        if self._recipe['total'] is None and not self._pct:
            return []
        return [s for s in self._recipe['segments'] if s[1]]

    def _layout_rects(self):
        segs = self.segments()
        w = self.width()
        x = 0.0
        rects = []
        for cat, value, share in segs:
            seg_w = max(1.0, value / self._scale * w - _GAP)
            rects.append((QRectF(x, 0, seg_w, self.height()), cat, value, share))
            x += seg_w + _GAP
        return rects

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._rects = self._layout_rects()
        if not self._rects:
            p.setPen(QColor(_BORDER))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 4, 4)
            return
        n = len(self._rects)
        for i, (rect, cat, _v, _s) in enumerate(self._rects):
            path = QPainterPath()
            r = 4.0
            left_r = r if i == 0 else 0.0
            right_r = r if i == n - 1 else 0.0
            _rounded(path, rect, left_r, right_r)
            p.fillPath(path, QColor(self._colors.get(cat, '#888888')))

    def mouseMoveEvent(self, event):
        x = event.position().x()
        for rect, cat, value, share in self._rects:
            if rect.left() <= x <= rect.right() + _GAP:
                items = self._recipe['items'].get(cat, [])
                if self._pct:
                    head = f'{cat} · {value:.1f}% of the total'
                else:
                    head = f'{cat} · {compare.fmt_metric(value, self._metric)} ({share * 100:.0f}%)'
                lines = [head] + [f'  {n}: {compare.fmt_metric(v, self._metric)}' for n, v in items[:8]
                                  if v is not None]
                if len(items) > 8:
                    lines.append(f'  and {len(items) - 8} more')
                QToolTip.showText(event.globalPosition().toPoint(), '\n'.join(lines), self)
                return
        QToolTip.hideText()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


def _rounded(path, rect, left_r, right_r):
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    left_r = min(left_r, w / 2)
    right_r = min(right_r, w / 2)
    path.moveTo(x + left_r, y)
    path.lineTo(x + w - right_r, y)
    if right_r:
        path.quadTo(x + w, y, x + w, y + right_r)
        path.lineTo(x + w, y + h - right_r)
        path.quadTo(x + w, y + h, x + w - right_r, y + h)
    else:
        path.lineTo(x + w, y + h)
    path.lineTo(x + left_r, y + h)
    if left_r:
        path.quadTo(x, y + h, x, y + h - left_r)
        path.lineTo(x, y + left_r)
        path.quadTo(x, y, x + left_r, y)
    else:
        path.lineTo(x, y)
    path.closeSubpath()


class _Axis(QWidget):
    '''A rule with tick labels spread from 0 to the scale's end.'''

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.labels = labels
        self.setFixedHeight(22)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setPen(QColor(_BORDER))
        p.drawLine(0, 0, self.width(), 0)
        font = p.font()
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(QColor(_MUTED))
        n = len(self.labels)
        for i, text in enumerate(self.labels):
            x = self.width() * i / (n - 1) if n > 1 else 0
            align = Qt.AlignLeft if i == 0 else Qt.AlignRight if i == n - 1 else Qt.AlignHCenter
            w = 80
            left = x if i == 0 else x - w if i == n - 1 else x - w / 2
            p.drawText(QRectF(left, 4, w, 16), align | Qt.AlignVCenter, text)
