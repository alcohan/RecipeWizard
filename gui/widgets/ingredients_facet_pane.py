'''Left filter pane for the Ingredients place: Category, Needs
attention, Supplier, Allergens — checkboxes with counts, per the
Framework canvas.

Two kinds of section:
- "include" (Category, Supplier): everything starts checked;
  unchecking hides those ingredients.
- "any" (Needs attention, Allergens): everything starts unchecked;
  checking shows only ingredients with any checked item.

Sections collapse (Supplier and Allergens start collapsed; the choice
is remembered). A collapsed section that's filtering says so in its
header, so a hidden filter never hides rows silently. Sections with
more than five options — categories are user-defined, so there can be
many — get an All / None toggle.

Counts are totals over the whole library, so they don't jump as other
filters change. `set_library(rows)` rebuilds the lists from the
model's rows, keeping each checkbox's state by key.
'''
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

from gui.models.ingredients_model import ATTENTION_KEYS, NO_ALLERGENS


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_WARN = '#8a4a00'

_ATTENTION_LABELS = {
    'price_up': ('Price up 5%+ (90 days)', '#8a4a00'),
    'no_price': ('No price', '#b80700'),
    'no_nutrition': ('No nutrition', _MUTED),
    'no_photo': ('No photo', _MUTED),
    'unused': ('Not used in any recipe', _MUTED),
}

# key, title, mode, open by default
_SECTIONS = (
    ('category', 'Category', 'include', True),
    ('attention', 'Needs attention', 'any', True),
    ('supplier', 'Supplier', 'include', False),
    ('allergen', 'Allergens', 'any', False),
)
_ALL_TOGGLE_MIN = 6   # show All / None when a section has more than five options
_SETTINGS_PREFIX = 'ingredients/facetOpen/'


class _Section(QWidget):
    '''Header (arrow, title, filtered marker, All/None) over a body of
    checkbox rows.'''

    toggledAll = Signal(bool)    # True = check all

    def __init__(self, key, title, mode, default_open, parent=None):
        super().__init__(parent)
        self.key, self.mode = key, mode
        self._title = title
        self._filtering = False
        saved = QSettings().value(_SETTINGS_PREFIX + key, default_open, type=bool)

        self.arrow = QToolButton()
        self.arrow.setAutoRaise(True)
        self.arrow.setCursor(Qt.PointingHandCursor)
        self.arrow.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.arrow.setStyleSheet(f'QToolButton {{ border: 0; color: {_MUTED}; font-size: 11px;'
                                 ' font-weight: 600; letter-spacing: 1px; padding: 0; }')
        self.arrow.clicked.connect(self.toggle_open)
        self.marker = QLabel('filtered')
        self.marker.setStyleSheet(f'color: {_WARN}; background: #fff0dc; border-radius: 8px;'
                                  ' padding: 0 6px; font-size: 11px; font-weight: 600;')
        self.marker.hide()
        self.all_btn = QPushButton('All')
        self.all_btn.setFlat(True)
        self.all_btn.setCursor(Qt.PointingHandCursor)
        self.all_btn.setStyleSheet(f'QPushButton {{ color: {_ROMAINE}; border: 0; padding: 0 2px;'
                                   ' font-size: 12px; } QPushButton:hover { text-decoration: underline; }')
        self.all_btn.clicked.connect(lambda: self.toggledAll.emit(self.all_btn.text() == 'All'))
        self.all_btn.hide()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        head.addWidget(self.arrow)
        head.addWidget(self.marker)
        head.addStretch()
        head.addWidget(self.all_btn)

        self.body_widget = QWidget()
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(0, 4, 0, 0)
        self.body.setSpacing(7)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(head)
        layout.addWidget(self.body_widget)
        self._set_open(saved, persist=False)

    def is_open(self):
        return self.body_widget.isVisibleTo(self)

    def toggle_open(self):
        self._set_open(not self.body_widget.isVisibleTo(self))

    def _set_open(self, open_, persist=True):
        self.body_widget.setVisible(open_)
        self.arrow.setText(f'{"▾" if open_ else "▸"}  {self._title.upper()}')
        self.arrow.setToolTip('Collapse' if open_ else 'Expand')
        self.marker.setVisible(self._filtering and not open_)
        if persist:
            QSettings().setValue(_SETTINGS_PREFIX + self.key, open_)

    def sync(self, boxes, filtering):
        '''Refresh the All/None label and the filtered marker.'''
        many = len(boxes) >= _ALL_TOGGLE_MIN
        self.all_btn.setVisible(many)
        if many:
            all_on = all(cb.isChecked() for cb in boxes.values())
            self.all_btn.setText('None' if all_on else 'All')
            self.all_btn.setToolTip('Uncheck every option' if all_on else 'Check every option')
        self._filtering = filtering
        self.marker.setVisible(filtering and not self.is_open())


class IngredientsFacetPane(QScrollArea):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(f'QScrollArea {{ border: 0; border-right: 1px solid {_BORDER};'
                           ' background: #fffaf2; }')
        host = QWidget()
        host.setObjectName('FacetHost')
        host.setStyleSheet(f'QWidget#FacetHost {{ background: #fffaf2; }}'
                           f' QCheckBox {{ color: {_KALE}; spacing: 8px; }}')
        self._layout = QVBoxLayout(host)
        self._layout.setContentsMargins(18, 20, 18, 20)
        self._layout.setSpacing(18)
        self.setWidget(host)

        self._groups = {}
        self._state = {}   # (group, key) → checked
        for key, title, mode, default_open in _SECTIONS:
            section = _Section(key, title, mode, default_open)
            section.toggledAll.connect(lambda on, k=key: self._set_all(k, on))
            self._layout.addWidget(section)
            self._groups[key] = {'section': section, 'boxes': {}, 'mode': mode}
        self._layout.addStretch()

    # --- building ------------------------------------------------------

    def set_library(self, rows):
        cats = {}
        for r in rows:
            key = r.get('TagId')
            entry = cats.setdefault(key, {'name': r.get('TagName') or 'Uncategorized',
                                          'color': r.get('TagColor') or '#a7ad9c',
                                          'sort': r.get('TagSort', 1000), 'n': 0})
            entry['n'] += 1
        self._fill('category', [
            (k, v['name'], v['color'], v['n'], None)
            for k, v in sorted(cats.items(), key=lambda kv: (kv[1]['sort'], kv[1]['name']))
        ])

        counts = {k: sum(1 for r in rows if r['Flags'][k]) for k in ATTENTION_KEYS}
        self._fill('attention', [
            (k, _ATTENTION_LABELS[k][0], None, counts[k], _ATTENTION_LABELS[k][1] if counts[k] else _MUTED)
            for k in ATTENTION_KEYS
        ])

        sups = {}
        for r in rows:
            key = r.get('SupplierId')
            entry = sups.setdefault(key, {'name': r.get('SupplierName') or 'No supplier', 'n': 0})
            entry['n'] += 1
        self._fill('supplier', [
            (k, v['name'], None, v['n'], None)
            for k, v in sorted(sups.items(), key=lambda kv: (kv[0] is None, kv[1]['name'].lower()))
        ])

        # Allergens in the canonical order they appear in rows (each
        # row's list is already sorted that way), then "No allergens".
        order, counts = [], {}
        for r in rows:
            for name in r['AllergenList']:
                if name not in counts:
                    order.append(name)
                    counts[name] = 0
                counts[name] += 1
        none_n = sum(1 for r in rows if not r['AllergenList'])
        self._fill('allergen', [(name, name, None, counts[name], None) for name in order]
                   + [(NO_ALLERGENS, 'No allergens', None, none_n, None)])

    def _fill(self, group, items):
        g = self._groups[group]
        body = g['section'].body
        default = g['mode'] == 'include'
        while body.count():
            w = body.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        g['boxes'] = {}
        for key, label, dot, count, count_color in items:
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            cb = QCheckBox()
            cb.setChecked(self._state.get((group, key), default))
            cb.toggled.connect(lambda checked, gk=(group, key): self._on_toggled(gk, checked))
            hl.addWidget(cb)
            if dot:
                d = QLabel()
                d.setFixedSize(10, 10)
                d.setStyleSheet(f'background: {dot}; border-radius: 5px;')
                hl.addWidget(d)
            text = QLabel(label)
            text.setStyleSheet(f'color: {_KALE};')
            # Clicking the label toggles too, like a <label for>.
            text.mousePressEvent = lambda _e, c=cb: c.toggle()
            hl.addWidget(text, stretch=1)
            n = QLabel(str(count))
            weight = '600' if count_color and count_color != _MUTED else '400'
            n.setStyleSheet(f'color: {count_color or _MUTED}; font-weight: {weight};')
            hl.addWidget(n)
            body.addWidget(row)
            g['boxes'][key] = cb
        self._sync_section(group)

    # --- changes -------------------------------------------------------

    def _on_toggled(self, group_key, checked):
        self._state[group_key] = checked
        self._sync_section(group_key[0])
        self.changed.emit()

    def _set_all(self, group, on):
        '''All / None: one filter update, not one per checkbox.'''
        for key, cb in self._groups[group]['boxes'].items():
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
            self._state[(group, key)] = on
        self._sync_section(group)
        self.changed.emit()

    def _filtering(self, group):
        g = self._groups[group]
        checked = [cb.isChecked() for cb in g['boxes'].values()]
        return (not all(checked)) if g['mode'] == 'include' else any(checked)

    def _sync_section(self, group):
        g = self._groups[group]
        g['section'].sync(g['boxes'], self._filtering(group))

    # --- reading -------------------------------------------------------

    def selection(self):
        '''(categories, attention, suppliers, allergens) for
        IngredientsFacetProxy. An include section with everything
        checked returns None (no filter); an any section returns the
        set of checked keys (empty = no filter).'''
        def included(group):
            boxes = self._groups[group]['boxes']
            on = {k for k, cb in boxes.items() if cb.isChecked()}
            return None if len(on) == len(boxes) else on

        def any_of(group):
            return {k for k, cb in self._groups[group]['boxes'].items() if cb.isChecked()}

        return included('category'), any_of('attention'), included('supplier'), any_of('allergen')

    def clear(self):
        for group, g in self._groups.items():
            on = g['mode'] == 'include'
            for key, cb in g['boxes'].items():
                cb.blockSignals(True)
                cb.setChecked(on)
                cb.blockSignals(False)
                self._state[(group, key)] = on
            self._sync_section(group)
        self.changed.emit()
