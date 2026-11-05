'''Live results column for the recipe editor: wedge, cost, food cost
against the target, nutrition per serving and the allergen roll-up.

Everything compares against the baseline — the recipe as it was at
the last save — so the user sees what their unsaved edits do
("+$0.19 vs saved", "Calories 640 +21").
'''
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_RULE = '#f3ece0'
_TRACK = '#efe9de'
_OVER = '#8a4a00'
_OVER_BG = '#fff0dc'
_BAR_MAX = 0.5   # the food-cost bar spans 0–50%

# (key in recipe_info, label, unit suffix)
_NUTRITION = (
    ('Calories', 'Calories', ''),
    ('ProteinGrams', 'Protein', ' g'),
    ('TTLFatGrams', 'Fat', ' g'),
    ('CarbGrams', 'Carbs', ' g'),
    ('FiberGrams', 'Fiber', ' g'),
    ('SodiumMilligrams', 'Sodium', ' mg'),
    ('CholesterolMilligrams', 'Cholesterol', ' mg'),
)


def food_cost_target():
    '''A fraction (0.28), or None when the target is switched off.'''
    from gui.services import food_cost
    return food_cost.target_fraction()


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600;'
                      ' letter-spacing: 1px;')
    return lbl


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class EditorResults(QWidget):
    fullLabelRequested = Signal()

    def __init__(self, wedge, parent=None):
        super().__init__(parent)
        self.setObjectName('EditorResults')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f'QWidget#EditorResults {{ background: #ffffff; }}'
                           f' QLabel {{ color: {_KALE}; }}')

        wedge_col = QVBoxLayout()
        wedge_col.addWidget(wedge, alignment=Qt.AlignHCenter)

        # --- cost ---
        self.cost_label = QLabel('')
        self.cost_label.setStyleSheet(f'color: {_KALE}; font-size: 30px; font-weight: 600;')
        self.cost_delta = QLabel('')
        self.cost_delta.setStyleSheet(f'color: {_KALE}; background: #fff1da; border-radius: 4px;'
                                      ' padding: 1px 6px; font-weight: 600; font-size: 13px;')
        cost_row = QHBoxLayout()
        cost_row.setSpacing(10)
        cost_row.addWidget(self.cost_label)
        cost_row.addWidget(self.cost_delta, alignment=Qt.AlignVCenter)
        cost_row.addStretch()

        self.food_cost_label = QLabel('')
        self.food_cost_label.setTextFormat(Qt.RichText)
        self.margin_label = QLabel('')
        self.margin_label.setTextFormat(Qt.RichText)
        for lbl in (self.food_cost_label, self.margin_label):
            lbl.setStyleSheet(f'color: {_MUTED};')
        fc_row = QHBoxLayout()
        fc_row.addWidget(self.food_cost_label)
        fc_row.addStretch()
        fc_row.addWidget(self.margin_label)

        self.food_cost_bar = _FoodCostBar()
        # Scale under the bar: 0% · target · 50%. The target label sits
        # under the tick (positioned by stretch ratios on refresh).
        self.bar_scale = QWidget()
        self._scale_layout = QHBoxLayout(self.bar_scale)
        self._scale_layout.setContentsMargins(0, 0, 0, 0)
        self._scale_target = QLabel('')
        for text in ('0%', None, f'{_BAR_MAX * 100:.0f}%'):
            lbl = self._scale_target if text is None else QLabel(text)
            lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px;')
            self._scale_layout.addWidget(lbl)

        cost_col = QVBoxLayout()
        cost_col.setSpacing(8)
        cost_col.addWidget(_eyebrow('Cost'))
        cost_col.addLayout(cost_row)
        cost_col.addLayout(fc_row)
        cost_col.addWidget(self.food_cost_bar)
        cost_col.addWidget(self.bar_scale)

        # --- nutrition ---
        self.nutrition_title = _eyebrow('Nutrition')
        full_label = QLabel(f'<a href="#" style="color: {_ROMAINE}">Full label</a>')
        full_label.setStyleSheet('font-size: 12px;')
        full_label.linkActivated.connect(lambda _h: self.fullLabelRequested.emit())
        nut_head = QHBoxLayout()
        nut_head.addWidget(self.nutrition_title)
        nut_head.addStretch()
        nut_head.addWidget(full_label)

        self._nutrition_values = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(0)
        for i, (key, label, _suffix) in enumerate(_NUTRITION):
            cell = QFrame()
            cell.setObjectName('NutCell')
            last_row = i >= len(_NUTRITION) - 2
            cell.setStyleSheet('QFrame#NutCell { border: 0; border-bottom: %s; }'
                               % ('0' if last_row else f'1px solid {_RULE}'))
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 6, 0, 6)
            name = QLabel(label)
            value = QLabel('')
            value.setTextFormat(Qt.RichText)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(value)
            self._nutrition_values[key] = value
            grid.addWidget(cell, i // 2, i % 2)

        nut_col = QVBoxLayout()
        nut_col.setSpacing(8)
        nut_col.addLayout(nut_head)
        nut_col.addLayout(grid)

        # --- allergens ---
        self._allergen_host = QVBoxLayout()
        self._allergen_host.setSpacing(6)
        all_col = QVBoxLayout()
        all_col.setSpacing(8)
        all_col.addWidget(_eyebrow('Allergens · rolled up'))
        all_col.addLayout(self._allergen_host)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(22)
        layout.addLayout(wedge_col)
        layout.addLayout(cost_col)
        layout.addLayout(nut_col)
        layout.addLayout(all_col)
        layout.addStretch()

    def update_results(self, recipe, baseline, allergen_sources):
        '''`recipe` and `baseline` are recipe_info() dicts (current and
        last-saved); `allergen_sources` is [(allergen, [names])].'''
        cost = _num(recipe.get('CostRaw'))
        saved_cost = _num(baseline.get('CostRaw')) if baseline else cost
        self.cost_label.setText(f'${cost:.2f}')
        delta = cost - saved_cost
        if abs(delta) >= 0.005:
            sign = '+' if delta > 0 else '−'
            self.cost_delta.setText(f'{sign}${abs(delta):.2f} vs saved')
            self.cost_delta.show()
        else:
            self.cost_delta.hide()

        price = _num(recipe.get('MenuPrice'))
        target = food_cost_target()
        if price > 0:
            pct = cost / price
            over = target is not None and pct > target
            pct_html = (f'<b style="color: {_OVER}; background: {_OVER_BG}">{pct * 100:.1f}%</b>'
                        if over else f'<b style="color: {_KALE}">{pct * 100:.1f}%</b>')
            self.food_cost_label.setText(f'Food cost {pct_html} of ${price:.2f}')
            self.margin_label.setText(f'Margin <b style="color: {_KALE}">${price - cost:.2f}</b>')
            self.margin_label.show()
            self.food_cost_bar.set_values(pct, target)
            self.food_cost_bar.show()
            self._scale_target.setText(f'target {target * 100:.0f}%' if target is not None else '')
            # Stretch the gaps so the label lands near the tick.
            left = max(1, int((target if target is not None else _BAR_MAX / 2) / _BAR_MAX * 100))
            while self._scale_layout.count() > 3:
                self._scale_layout.takeAt(1)
                self._scale_layout.takeAt(2)
            self._scale_layout.insertStretch(1, left)
            self._scale_layout.insertStretch(3, max(1, 100 - left))
            self.bar_scale.show()
        else:
            self.food_cost_label.setText('Set a menu price to see food cost')
            self.margin_label.hide()
            self.food_cost_bar.hide()
            self.bar_scale.hide()

        self.nutrition_title.setText(f'NUTRITION · PER {str(recipe.get("Unit") or "serving").upper()}')
        for key, _label, suffix in _NUTRITION:
            now = _num(recipe.get(key))
            text = f'<b>{now:,.0f}{suffix}</b>'
            if baseline:
                d = now - _num(baseline.get(key))
                if abs(d) >= 0.5:
                    text += f' <span style="color: {_MUTED}">{"+" if d > 0 else "−"}{abs(d):,.0f}</span>'
            self._nutrition_values[key].setText(text)

        while self._allergen_host.count():
            item = self._allergen_host.takeAt(0)
            if item.layout() is not None:
                while item.layout().count():
                    w = item.layout().takeAt(0).widget()
                    if w is not None:
                        w.deleteLater()
            elif item.widget() is not None:
                item.widget().deleteLater()
        if not allergen_sources:
            none = QLabel('None')
            none.setStyleSheet(f'color: {_MUTED};')
            self._allergen_host.addWidget(none)
        for allergen, sources in allergen_sources:
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(f'<b>{allergen}</b>')
            name.setFixedWidth(80)
            src = QLabel(', '.join(sources))
            src.setWordWrap(True)
            src.setStyleSheet(f'color: {_MUTED};')
            row.addWidget(name, alignment=Qt.AlignTop)
            row.addWidget(src, stretch=1)
            self._allergen_host.addLayout(row)


class _FoodCostBar(QWidget):
    '''10 px track, fill to the food-cost %, a kale tick at the target.
    Fill turns amber over target.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._pct = 0.0
        self._target = None

    def set_values(self, pct, target):
        self._pct, self._target = pct, target
        self.setToolTip(f'Food cost {pct * 100:.1f}%'
                        + (f', target {target * 100:.0f}%' if target is not None else ''))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        track = QRectF(0, 4, w, 10)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_TRACK))
        p.drawRoundedRect(track, 5, 5)
        fill_w = w * max(0.0, min(1.0, self._pct / _BAR_MAX))
        if fill_w > 0:
            over = self._target is not None and self._pct > self._target
            p.setBrush(QColor(_OVER if over else _ROMAINE))
            p.drawRoundedRect(QRectF(0, 4, fill_w, 10), 5, 5)
        if self._target is not None:
            tx = w * max(0.0, min(1.0, self._target / _BAR_MAX))
            p.fillRect(QRectF(tx - 1, 0, 2, 18), QColor(_KALE))
