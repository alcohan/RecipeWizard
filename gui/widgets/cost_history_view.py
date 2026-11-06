'''The recipe tab's Cost over time view: today's recipe at past prices,
one point per week (utilities.cost_history does the numbers).

Headline tiles, a step chart (cost on the left axis, food cost % on the
right when there's a menu price, the target as a dashed line, purchase
imports marked), "What moved it" between two weeks picked by dragging
across the chart, and the ingredients that have no price yet.
'''
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

import db
from gui.services import food_cost
from gui.widgets import config_kit as kit
from gui.widgets.toolbar_controls import SegmentedSwitch
from utilities import cost_history as ch

_RULE = '#f3ece0'
_UP = '#8a4a00'
_UP_BG = '#fff0dc'
_DOWN = '#347200'
_PILL_BG = '#efe9de'


def _day(d):
    return f'{d:%b} {d.day}'


def _money(v, signed=False):
    sign = ('+' if v > 0 else '−' if v < 0 else '') if signed else ('−' if v < 0 else '')
    return f'{sign}${abs(v):.2f}'


class CostChart(QWidget):
    '''Weekly step chart. Drag across it to pick two weeks; hovering
    shows that week's cost.'''

    selectionChanged = Signal(int, int)

    L, T, B = 58, 14, 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.CrossCursor)
        self._weeks, self._costs, self._batches = [], [], {}
        self._menu = None
        self._target = None
        self._sel = (0, 0)
        self._hover = None
        self._drag_from = None

    def set_data(self, weeks, costs, batches, menu_price=None, target=None, selection=None):
        self._weeks, self._costs, self._batches = list(weeks), list(costs), dict(batches)
        self._menu = menu_price or None
        self._target = target if self._menu else None
        n = len(self._weeks)
        self._sel = selection if selection else (0, max(0, n - 1))
        self._hover = None
        self.update()

    def selection(self):
        return tuple(sorted(self._sel))

    # --- geometry ---

    def _right(self):
        return 56 if self._menu else 16

    def _plot(self):
        return QRectF(self.L, self.T, max(10, self.width() - self.L - self._right()),
                      max(10, self.height() - self.T - self.B))

    def _yrange(self):
        vals = list(self._costs)
        if self._target:
            vals.append(self._target * self._menu)
        lo, hi = min(vals), max(vals)
        pad = max((hi - lo) * 0.15, hi * 0.04, 0.05)
        lo = max(0.0, lo - pad)
        hi = hi + pad
        return lo, hi

    def _x(self, i):
        p = self._plot()
        n = len(self._weeks)
        return p.left() + (p.width() * i / (n - 1) if n > 1 else p.width() / 2)

    def _y(self, v, lo, hi):
        p = self._plot()
        return p.top() + p.height() * (hi - v) / (hi - lo if hi > lo else 1)

    def _index_at(self, x):
        n = len(self._weeks)
        if n < 2:
            return 0 if n else None
        p = self._plot()
        i = round((x - p.left()) / p.width() * (n - 1))
        return max(0, min(n - 1, i))

    # --- mouse ---

    def mousePressEvent(self, event):
        i = self._index_at(event.position().x())
        if i is None or event.button() != Qt.LeftButton:
            return
        self._drag_from = i
        self._sel = (i, i)
        self.update()

    def mouseMoveEvent(self, event):
        i = self._index_at(event.position().x())
        self._hover = i
        if self._drag_from is not None and i is not None:
            self._sel = (self._drag_from, i)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag_from is None:
            return
        self._drag_from = None
        a, b = sorted(self._sel)
        if a == b:     # a click picks that week against the latest
            a, b = a, len(self._weeks) - 1
            if a == b:
                a = 0
        self._sel = (a, b)
        self.update()
        self.selectionChanged.emit(a, b)

    def leaveEvent(self, _event):
        self._hover = None
        self.update()

    # --- paint ---

    def paintEvent(self, _event):
        if not self._weeks:
            return
        g = QPainter(self)
        g.setRenderHint(QPainter.Antialiasing)
        p = self._plot()
        lo, hi = self._yrange()
        small = QFont(self.font())
        small.setPixelSize(11)
        g.setFont(small)
        muted = QColor(kit.MUTED)

        # grid and axes
        steps = 4
        for k in range(steps + 1):
            v = lo + (hi - lo) * k / steps
            y = self._y(v, lo, hi)
            g.setPen(QPen(QColor(_RULE), 1))
            g.drawLine(QPointF(p.left(), y), QPointF(p.right(), y))
            g.setPen(muted)
            g.drawText(QRectF(0, y - 8, self.L - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f'${v:.2f}')
            if self._menu:
                g.drawText(QRectF(p.right() + 8, y - 8, self._right() - 8, 16), Qt.AlignLeft | Qt.AlignVCenter,
                           f'{v / self._menu * 100:.1f}%')

        # selection band
        a, b = sorted(self._sel)
        if b > a and (a, b) != (0, len(self._weeks) - 1):
            band = QColor(kit.ROMAINE)
            band.setAlphaF(0.06)
            g.fillRect(QRectF(self._x(a), p.top(), self._x(b) - self._x(a), p.height()), band)

        # import markers
        seen = set()
        for i in sorted(self._batches):
            new = [n for n in self._batches[i] if n not in seen]
            seen.update(new)
            if not new:
                continue   # an import's later weeks: marked once, at its first
            x = self._x(i)
            g.setPen(QPen(QColor('#c9c2b2'), 1, Qt.DashLine))
            g.drawLine(QPointF(x, p.top()), QPointF(x, p.bottom()))
            tag = '#' + ', #'.join(str(n) for n in new)
            w = g.fontMetrics().horizontalAdvance(tag) + 12
            pill = QRectF(x - w / 2, p.bottom() - 18, w, 16)
            g.setPen(Qt.NoPen)
            g.setBrush(QColor(_PILL_BG))
            g.drawRoundedRect(pill, 8, 8)
            g.setPen(muted)
            g.drawText(pill, Qt.AlignCenter, tag)

        # target
        if self._target:
            ty = self._y(self._target * self._menu, lo, hi)
            g.setPen(QPen(QColor(_UP), 1.5, Qt.DashLine))
            g.drawLine(QPointF(p.left(), ty), QPointF(p.right(), ty))
            g.setPen(QColor(_UP))
            g.drawText(QRectF(p.left(), ty - 18, p.width() - 4, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f'Target {self._target * 100:.0f}%')

        # the step line and its fill
        path = QPainterPath(QPointF(self._x(0), self._y(self._costs[0], lo, hi)))
        for i in range(1, len(self._costs)):
            path.lineTo(self._x(i), self._y(self._costs[i - 1], lo, hi))
            path.lineTo(self._x(i), self._y(self._costs[i], lo, hi))
        if len(self._costs) == 1:
            path.lineTo(self._x(0) + 1, self._y(self._costs[0], lo, hi))
        fill = QPainterPath(path)
        fill.lineTo(self._x(len(self._costs) - 1), p.bottom())
        fill.lineTo(self._x(0), p.bottom())
        fill.closeSubpath()
        tint = QColor(kit.ROMAINE)
        tint.setAlphaF(0.08)
        g.setPen(Qt.NoPen)
        g.setBrush(tint)
        g.drawPath(fill)
        g.setBrush(Qt.NoBrush)
        g.setPen(QPen(QColor(kit.ROMAINE), 2.5))
        g.drawPath(path)

        # selection ends
        if b > a:
            for i, solid in ((a, False), (b, True)):
                g.setPen(QPen(QColor(kit.ROMAINE), 2))
                g.setBrush(QColor(kit.ROMAINE) if solid else QColor('#ffffff'))
                g.drawEllipse(QPointF(self._x(i), self._y(self._costs[i], lo, hi)), 4.5, 4.5)

        # x labels
        n = len(self._weeks)
        every = max(1, round(n / 7))
        g.setPen(muted)
        for i in range(n):
            if i % every == 0 or i == n - 1:
                if i != n - 1 and n - 1 - i < every * 0.6:
                    continue
                g.drawText(QRectF(self._x(i) - 30, p.bottom() + 6, 60, 16), Qt.AlignCenter, _day(self._weeks[i]))

        # hover
        h = self._hover
        if h is not None and self._drag_from is None:
            x, y = self._x(h), self._y(self._costs[h], lo, hi)
            g.setPen(QPen(QColor(kit.KALE), 1))
            g.drawLine(QPointF(x, y), QPointF(x, p.bottom()))
            g.setBrush(QColor(kit.KALE))
            g.drawEllipse(QPointF(x, y), 3.5, 3.5)
            lines = [f'{_day(self._weeks[h])} · ${self._costs[h]:.2f}']
            second = []
            if self._menu:
                second.append(f'{self._costs[h] / self._menu * 100:.1f}%')
            if h in self._batches:
                second.append('import #' + ', #'.join(str(n) for n in self._batches[h]))
            if second:
                lines.append(' · '.join(second))
            bold = QFont(small)
            bold.setBold(True)
            fm = g.fontMetrics()
            w = max(fm.horizontalAdvance(t) for t in lines) + 20
            hgt = 18 * len(lines) + 10
            bx = min(max(x - w / 2, p.left()), p.right() - w)
            by = max(p.top(), y - hgt - 12)
            g.setPen(Qt.NoPen)
            g.setBrush(QColor(kit.KALE))
            g.drawRoundedRect(QRectF(bx, by, w, hgt), 6, 6)
            g.setPen(QColor('#fff1da'))
            for k, t in enumerate(lines):
                g.setFont(bold if k == 0 else small)
                g.drawText(QRectF(bx + 10, by + 5 + 18 * k, w - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, t)
        g.end()


def _tile():
    frame = QFrame()
    frame.setObjectName('CostTile')
    frame.setStyleSheet(f'QFrame#CostTile {{ background: #ffffff; border: 1px solid {kit.BORDER};'
                        ' border-radius: 8px; }')
    col = QVBoxLayout(frame)
    col.setContentsMargins(14, 10, 14, 10)
    col.setSpacing(2)
    label = kit.eyebrow('')
    value = QLabel('')
    value.setStyleSheet(f'color: {kit.KALE}; font-size: 22px; font-weight: 650;')
    sub = QLabel('')
    sub.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
    for w in (label, value, sub):
        col.addWidget(w)
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return frame, label, value, sub


class CostHistoryView(QWidget):
    '''Cost over time for one recipe. Call refresh() when it's shown or
    the recipe changes.'''

    ingredientRequested = Signal(int)

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._range = ch.DEFAULT_RANGE
        self._hist = None
        self._menu = None
        self._target = None

        self.range_switch = SegmentedSwitch([(k, label) for k, label, _d in ch.RANGES])
        self.range_switch.set_current(self._range)
        self.range_switch.changed.connect(self._on_range)

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self._tiles = {}
        for key in ('now', 'change', 'range', 'room'):
            frame, label, value, sub = _tile()
            self._tiles[key] = (frame, label, value, sub)
            tiles.addWidget(frame)

        chart_card, cc = kit.card()
        self.chart_title = kit.subheading('Cost per serving')
        chart_head = QHBoxLayout()
        chart_head.addWidget(self.chart_title)
        chart_head.addStretch()
        chart_head.addWidget(self.range_switch)
        cc.addLayout(chart_head)
        self.chart = CostChart()
        self.chart.selectionChanged.connect(lambda _a, _b: self._fill_movers())
        cc.addWidget(self.chart)

        movers_card, mc = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading('What moved it'))
        self.movers_span = QLabel('')
        self.movers_span.setTextFormat(Qt.RichText)
        self.movers_span.setStyleSheet(f'color: {kit.MUTED}; font-size: 13px;')
        head.addWidget(self.movers_span)
        head.addStretch()
        mc.addLayout(head)
        self.movers_grid = QGridLayout()
        self.movers_grid.setHorizontalSpacing(16)
        self.movers_grid.setVerticalSpacing(6)
        self.movers_grid.setColumnStretch(0, 1)
        mc.addLayout(self.movers_grid)
        self.weeks_link = QLabel('')
        self.weeks_link.setTextFormat(Qt.RichText)
        self.weeks_link.linkActivated.connect(self._toggle_weeks)
        mc.addWidget(self.weeks_link)
        self.weeks_grid = QGridLayout()
        self.weeks_grid.setHorizontalSpacing(24)
        self.weeks_grid.setVerticalSpacing(4)
        self.weeks_box = QWidget()
        self.weeks_box.setLayout(self.weeks_grid)
        self.weeks_box.hide()
        mc.addWidget(self.weeks_box)

        self.unpriced = QFrame()
        self.unpriced.setObjectName('Unpriced')
        self.unpriced.setStyleSheet(f'QFrame#Unpriced {{ background: {_UP_BG}; border: 1px solid #e3cfa6;'
                                    ' border-radius: 8px; }')
        ul = QVBoxLayout(self.unpriced)
        ul.setContentsMargins(14, 10, 14, 12)
        ul.setSpacing(4)
        title = QLabel('No price yet')
        title.setStyleSheet(f'color: {_UP}; font-weight: 600;')
        ul.addWidget(title)
        self.unpriced_list = QLabel('')
        self.unpriced_list.setTextFormat(Qt.RichText)
        self.unpriced_list.setWordWrap(True)
        self.unpriced_list.linkActivated.connect(lambda href: self.ingredientRequested.emit(int(href)))
        ul.addWidget(self.unpriced_list)
        self.unpriced.setFixedWidth(260)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        bottom.addWidget(movers_card, stretch=1, alignment=Qt.AlignTop)
        bottom.addWidget(self.unpriced, alignment=Qt.AlignTop)

        self.empty = kit.note('No price history yet')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addLayout(tiles)
        layout.addWidget(chart_card)
        layout.addLayout(bottom)
        layout.addWidget(self.empty)
        self._content = [chart_card, movers_card] + [t[0] for t in self._tiles.values()]

    # --- data ---

    def _on_range(self, key):
        self._range = key
        self.refresh()

    def refresh(self):
        inputs = db.recipe_cost_history_inputs(self.recipe_id)
        if inputs is None:
            return
        comps, prices = ch.from_inputs(inputs)
        recipe = inputs['recipe']
        try:
            self._menu = float(recipe.get('MenuPrice')) if recipe.get('MenuPrice') not in (None, '') else None
        except (TypeError, ValueError):
            self._menu = None
        self._target = food_cost.target_fraction()
        unit = (recipe.get('Unit') or 'serving').strip() or 'serving'
        self.chart_title.setText(f'Cost per {unit}')
        self._hist = ch.build(comps, prices, since=ch.range_start(self._range))
        has = len(self._hist) > 0
        for w in self._content:
            w.setVisible(has)
        self.empty.setVisible(not has)
        self._fill_unpriced()
        if not has:
            return
        n = len(self._hist)
        self.chart.set_data(self._hist.weeks, self._hist.costs, self._hist.batches, self._menu, self._target,
                            selection=(0, n - 1))
        self._fill_movers()
        self._fill_weeks()

    def _fill_unpriced(self):
        items = self._hist.unpriced if self._hist else []
        self.unpriced.setVisible(bool(items))
        link = f'color: {kit.ROMAINE}'
        self.unpriced_list.setText('<br>'.join(
            f'<a href="{c.ingredient_id}" style="{link}">{_esc(c.name)}</a>' for c in items))

    def _fill_tiles(self, a, b):
        s = ch.summary(self._hist, a, b, self._menu, self._target)
        weeks = self._hist.weeks

        def put(key, label, value, sub, sub_color=kit.MUTED, show=True):
            frame, l, v, sl = self._tiles[key]
            frame.setVisible(show)
            l.setText(label.upper())
            v.setText(value)
            sl.setText(sub)
            sl.setStyleSheet(f'color: {sub_color}; font-size: 12px;')

        put('now', f'Now · week of {_day(s.now_week)}', f'${s.now:.2f}',
            f'{s.food_cost * 100:.1f}% food cost' if s.food_cost is not None else '')
        pct = f'{s.change_pct * 100:+.1f}%'.replace('-', '−') if s.change_pct is not None else ''
        put('change', f'Change since {_day(weeks[a])}', _money(s.change, signed=True), pct,
            _UP if s.change > 0.004 else kit.MUTED)
        put('range', 'Range', f'${s.low:.2f} – ${s.high:.2f}', '')
        if s.room is not None:
            over = s.room < 0
            put('room', 'Over target' if over else 'Room to target', f'${abs(s.room):.2f}',
                f'past the {self._target * 100:.0f}% target' if over else f'to the {self._target * 100:.0f}% target',
                _UP if over else kit.MUTED)
        else:
            put('room', '', '', '', show=False)

    def _fill_movers(self):
        a, b = self.chart.selection()
        if b == a and len(self._hist) > 1:
            a, b = 0, len(self._hist) - 1
        self._fill_tiles(a, b)
        weeks = self._hist.weeks
        total = self._hist.costs[b] - self._hist.costs[a]
        color = _UP if total > 0.004 else _DOWN if total < -0.004 else kit.MUTED
        self.movers_span.setText(f'<b style="color: {kit.KALE}">{_day(weeks[a])}</b> → '
                                 f'<b style="color: {kit.KALE}">{_day(weeks[b])}</b> · '
                                 f'<b style="color: {color}">{_money(total, signed=True)}</b>')
        rows, _unchanged = ch.movers(self._hist, a, b)
        _clear(self.movers_grid)
        if not rows:
            self.movers_grid.addWidget(kit.note('No changes'), 0, 0)
            return
        biggest = max(abs(m.change) for m in rows) or 1
        link = f'color: {kit.KALE}'
        for r, m in enumerate(rows):
            dot = m.color or '#c9c2b2'
            name = QLabel(f'<span style="color: {dot}">●</span>&nbsp; '
                          f'<a href="{m.ingredient_id}" style="{link}">{_esc(m.name)}</a>')
            name.setTextFormat(Qt.RichText)
            name.linkActivated.connect(lambda href: self.ingredientRequested.emit(int(href)))
            unit = QLabel(f'${m.price_from:.3f} → ${m.price_to:.3f} / {_esc(m.unit)}')
            unit.setStyleSheet(f'color: {kit.MUTED};')
            qty = QLabel(f'{_qty(m.qty)} {_esc(m.unit)}')
            qty.setStyleSheet(f'color: {kit.MUTED};')
            qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            up = m.change > 0
            change = QLabel(_money(m.change, signed=True))
            change.setStyleSheet(f'color: {_UP if up else _DOWN}; font-weight: 600;')
            change.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bar = QFrame()
            bar.setFixedHeight(6)
            bar.setFixedWidth(max(3, round(140 * abs(m.change) / biggest)))
            bar.setStyleSheet(f'background: {_UP if up else _DOWN}; border-radius: 3px;')
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(bar)
            hl.addStretch()
            holder.setFixedWidth(150)
            for c, w in enumerate((name, unit, qty, change, holder)):
                self.movers_grid.addWidget(w, r, c)

    def _fill_weeks(self):
        open_ = not self.weeks_box.isHidden()
        self.weeks_link.setText(f'<a href="toggle" style="color: {kit.ROMAINE}">'
                                f'{"Hide weeks" if open_ else "Show every week"}</a>')
        _clear(self.weeks_grid)
        heads = ['Week', 'Cost'] + (['Food cost'] if self._menu else []) + ['Import']
        for c, h in enumerate(heads):
            lab = kit.eyebrow(h.upper())
            self.weeks_grid.addWidget(lab, 0, c)
        for r, i in enumerate(reversed(range(len(self._hist))), start=1):
            cells = [_day(self._hist.weeks[i]), f'${self._hist.costs[i]:.2f}']
            if self._menu:
                cells.append(f'{self._hist.costs[i] / self._menu * 100:.1f}%')
            cells.append(', '.join(f'#{n}' for n in self._hist.batches.get(i, [])))
            for c, t in enumerate(cells):
                self.weeks_grid.addWidget(QLabel(t), r, c)

    def _toggle_weeks(self, _href):
        self.weeks_box.setVisible(self.weeks_box.isHidden())
        self._fill_weeks()


def _clear(grid):
    while grid.count():
        item = grid.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()


def _esc(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _qty(v):
    return f'{v:.2f}'.rstrip('0').rstrip('.') if v else '0'
