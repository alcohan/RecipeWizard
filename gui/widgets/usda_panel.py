'''USDA FoodData Central lookup panel — search, pick a food, see its
nutrition scaled to *our* unit, and hand the values to a form.

Used beside the New ingredient form and inside the Edit ingredient
dialog's "Look up in USDA…". Reference only: nothing is applied until
the user clicks "Use these values".

Scaling: USDA reports nutrients per 100 g. The panel needs the weight
of one of our units (`set_target(unit, weight_g)`, from the form):
  - the form's Weight (g), when it has one — that's our own number;
  - otherwise worked out from the unit and the food's USDA portions
    (api.usda.grams_per_unit: "3 cups" from a cup portion, "2 f.oz"
    converted from one, "1 w.oz" directly);
  - or picked from the food's portions in the "Scale to" list, or
    typed in.
A portion USDA measured that disagrees with the form's weight is
offered as a one-click alternative.

Network calls run on a worker (gui.workers), so a slow or rate-limited
API never freezes the window; failures show inline.
'''
from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QStyle, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

import api.usda as usda
from gui.workers import run_async


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_RULE = '#f3ece0'
_FIELD_BORDER = '#7d8771'
_SELECTED = '#fff1da'
_WARN = '#8a4a00'

_TYPE_STYLE = {   # pill fg, bg
    'Foundation': (_ROMAINE, '#e9f1d9'),
    'SR Legacy': ('#285900', '#eef3e4'),
    'Survey (FNDDS)': ('#285900', '#eef3e4'),
    'Branded': (_MUTED, '#efe9de'),
}
_TYPE_LABEL = {'Survey (FNDDS)': 'Survey'}
_PREVIEW_ROWS = (
    ('Calories', 'Calories', ''), ('ProteinGrams', 'Protein', ' g'),
    ('TTLFatGrams', 'Total fat', ' g'), ('SatFatGrams', 'Sat fat', ' g'),
    ('CarbGrams', 'Carbs', ' g'), ('FiberGrams', 'Fiber', ' g'),
    ('SugarGrams', 'Sugar', ' g'), ('SodiumMilligrams', 'Sodium', ' mg'),
    ('CholesterolMilligrams', 'Cholesterol', ' mg'),
)
_ROLE = Qt.UserRole


def _fmt(value, places=2):
    try:
        return f'{float(value):.{places}f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return ''


class _ResultDelegate(QStyledItemDelegate):
    '''name (+ brand) ........ [Foundation]'''

    def paint(self, painter, option, index):
        food = index.data(_ROLE) or {}
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(2, 1, -2, -1)
        if option.state & QStyle.State_Selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_SELECTED))
            painter.drawRoundedRect(QRectF(rect), 6, 6)
            painter.fillRect(rect.x(), rect.y() + 2, 3, rect.height() - 4, QColor(_ROMAINE))
        dtype = food.get('dataType', '')
        label = _TYPE_LABEL.get(dtype, dtype)
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.85))
        painter.setFont(small)
        fm = painter.fontMetrics()
        pw = fm.horizontalAdvance(label) + 14
        pill = QRectF(rect.right() - pw - 6, rect.center().y() - 9, pw, 18)
        fg, bg = _TYPE_STYLE.get(dtype, (_MUTED, '#efe9de'))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(pill, 9, 9)
        painter.setPen(QColor(fg))
        painter.drawText(pill, Qt.AlignCenter, label)
        name_font = QFont(option.font)
        if option.state & QStyle.State_Selected:
            name_font.setWeight(QFont.DemiBold)
        painter.setFont(name_font)
        painter.setPen(QColor(_KALE))
        text_rect = rect.adjusted(10, 0, -(pw + 16), 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         painter.fontMetrics().elidedText(usda.describe(food), Qt.ElideRight, text_rect.width()))
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width() or 300, 34)


class UsdaLookupPanel(QFrame):
    valuesChosen = Signal(dict, float, str)   # nutrition per unit, grams per unit, basis note

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('UsdaPanel')
        self.setStyleSheet(f'QFrame#UsdaPanel {{ background: #ffffff; }} QLabel {{ color: {_KALE}; }}'
                           f' QCheckBox {{ color: {_MUTED}; }}')
        self._unit = ''
        self._form_weight = None
        self._food = None
        self._per_100 = None
        self._portions = []
        self._derived = (None, '')   # grams per unit worked out from USDA portions
        self._note = ''
        self._search_token = 0
        self._detail_token = 0

        title = QLabel('USDA FoodData Central')
        title.setStyleSheet(f'color: {_KALE}; font-size: 15px; font-weight: 600;')
        ref = QLabel('Reference only')
        ref.setStyleSheet(f'color: {_MUTED}; background: #efe9de; border-radius: 9px;'
                          ' padding: 1px 8px; font-size: 11px;')
        head = QHBoxLayout()
        head.addWidget(title)
        head.addWidget(ref)
        head.addStretch()

        self.query = QLineEdit()
        self.query.setPlaceholderText('Search USDA, e.g. "kale, raw"')
        self.query.setStyleSheet(f'QLineEdit {{ height: 32px; padding: 0 10px; border: 1px solid {_FIELD_BORDER};'
                                 f' border-radius: 4px; }} QLineEdit:focus {{ border: 2px solid {_ROMAINE}; padding: 0 9px; }}')
        self.query.returnPressed.connect(self.search)
        search_btn = QPushButton('Search')
        search_btn.setAutoDefault(False)
        search_btn.setStyleSheet(f'QPushButton {{ min-height: 32px; padding: 0 14px; border: 1px solid {_FIELD_BORDER};'
                                 f' border-radius: 8px; background: #ffffff; color: {_KALE}; }}'
                                 ' QPushButton:hover { background: #f3ece0; }')
        search_btn.clicked.connect(self.search)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.query, stretch=1)
        row.addWidget(search_btn)
        self.branded = QCheckBox('Include branded products')
        self.branded.setChecked(True)
        self.branded.toggled.connect(lambda _v: self.query.text().strip() and self.search())

        self.status = QLabel('')
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')

        self.results = QListWidget()
        self.results.setItemDelegate(_ResultDelegate(self.results))
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.setStyleSheet(f'QListWidget {{ border: 1px solid {_BORDER}; border-radius: 8px;'
                                   ' background: #ffffff; padding: 4px; }')
        self.results.setMinimumHeight(150)
        # Names are elided to fit; a sideways scrollbar would only add noise.
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.currentItemChanged.connect(self._on_pick)

        # --- detail card ---
        self.detail = QFrame()
        self.detail.setObjectName('UsdaDetail')
        self.detail.setStyleSheet(f'QFrame#UsdaDetail {{ border: 1px solid {_BORDER}; border-radius: 8px;'
                                  ' background: #fffaf2; }')
        self.food_name = QLabel('')
        self.food_name.setWordWrap(True)
        self.food_name.setStyleSheet(f'color: {_KALE}; font-weight: 600;')
        self.basis = QLabel('')
        self.basis.setWordWrap(True)
        self.basis.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')

        self.scale_combo = QComboBox()
        self.scale_combo.currentIndexChanged.connect(self._on_scale_choice)
        self.grams = QLineEdit()
        self.grams.setValidator(QDoubleValidator(0.0, 100000.0, 3))
        self.grams.setAlignment(Qt.AlignRight)
        self.grams.setFixedWidth(80)
        self.grams.setPlaceholderText('grams')
        self.grams.textEdited.connect(lambda _t: self._update_preview(note='Typed weight'))
        scale_row = QHBoxLayout()
        scale_row.setSpacing(6)
        self.scale_label = QLabel('')
        self.scale_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        scale_row.addWidget(self.scale_label)
        scale_row.addWidget(self.grams)
        scale_row.addWidget(QLabel('g'))
        scale_row.addStretch()

        self.suggest = QLabel('')
        self.suggest.setWordWrap(True)
        self.suggest.setTextFormat(Qt.RichText)
        self.suggest.setStyleSheet(f'color: {_WARN}; font-size: 12px;')
        self.suggest.linkActivated.connect(self._use_suggestion)

        self._value_labels = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(2)
        for i, (key, label, _s) in enumerate(_PREVIEW_ROWS):
            name = QLabel(label)
            value = QLabel('')
            value.setAlignment(Qt.AlignRight)
            value.setStyleSheet(f'color: {_KALE}; font-weight: 600;')
            grid.addWidget(name, i // 2, (i % 2) * 2)
            grid.addWidget(value, i // 2, (i % 2) * 2 + 1)
            self._value_labels[key] = value
        self.use_btn = QPushButton('←  Use these values')
        self.use_btn.setAutoDefault(False)
        self.use_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 14px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}'
            ' QPushButton:disabled { background: #c9d1bf; color: #f4f1ea; }')
        self.use_btn.clicked.connect(self._on_use)

        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(12, 12, 12, 12)
        dl.setSpacing(8)
        dl.addWidget(self.food_name)
        dl.addWidget(self.basis)
        scale_head = QLabel('SCALE TO')
        scale_head.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
        dl.addWidget(scale_head)
        dl.addWidget(self.scale_combo)
        dl.addLayout(scale_row)
        dl.addWidget(self.suggest)
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet(f'background: {_RULE};')
        dl.addWidget(rule)
        dl.addLayout(grid)
        dl.addWidget(self.use_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        layout.addLayout(head)
        layout.addLayout(row)
        layout.addWidget(self.branded)
        layout.addWidget(self.status)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(self.detail)
        self.detail.hide()
        if usda.is_using_demo_key():
            self.status.setText('Using the shared demo key (30 lookups an hour). '
                                'Add your own free key in Tools › Preferences.')

    # --- inputs --------------------------------------------------------

    def set_query(self, text):
        self.query.setText(text or '')

    def set_target(self, unit_text, weight_g):
        '''The form's unit and weight per unit (None/0 = not set).'''
        self._unit = (unit_text or '').strip()
        try:
            self._form_weight = float(weight_g) if weight_g not in (None, '') and float(weight_g) > 0 else None
        except (TypeError, ValueError):
            self._form_weight = None
        if self._food is not None:
            self._rebuild_scale_options()

    # --- search --------------------------------------------------------

    def search(self):
        text = self.query.text().strip()
        if not text:
            return
        self._search_token += 1
        token = self._search_token
        self.status.setText(f'Searching USDA for "{text}"…')
        self.results.clear()
        self._clear_detail()
        include_branded = self.branded.isChecked()
        run_async(lambda: usda.search(text, include_branded),
                  lambda foods: self._on_results(token, text, foods),
                  lambda msg: self._on_search_error(token, msg))

    def _on_results(self, token, text, foods):
        if token != self._search_token:
            return   # a newer search superseded this one
        self.results.clear()
        for food in foods:
            item = QListWidgetItem(usda.describe(food))
            item.setData(_ROLE, food)
            item.setToolTip(f'{food.get("dataType")} · FDC {food.get("fdcId")}'
                            + (f' · {food.get("foodCategory")}' if food.get('foodCategory') else ''))
            self.results.addItem(item)
        n = len(foods)
        self.status.setText(f'{n} result{"s" if n != 1 else ""} for “{text}”')
        if foods:
            self.results.setCurrentRow(0)

    def _on_search_error(self, token, message):
        if token != self._search_token:
            return
        self.status.setText(message if message != 'No results' else 'No matches')

    # --- detail --------------------------------------------------------

    def _on_pick(self, current, _previous):
        if current is None:
            self._clear_detail()
            return
        hit = current.data(_ROLE)
        self._detail_token += 1
        token = self._detail_token
        self.detail.show()
        self.food_name.setText(usda.describe(hit))
        self.basis.setText('Loading portions and nutrients…')
        self.use_btn.setEnabled(False)
        run_async(lambda: usda.get_food_details(hit['fdcId']),
                  lambda food: self._on_detail(token, food),
                  lambda msg: self._on_detail_error(token, msg))

    def _on_detail(self, token, food):
        if token != self._detail_token:
            return
        self._food = food
        self._per_100 = usda.nutrients_per_100g(food)
        self._portions = usda.portions(food)
        self.food_name.setText(usda.describe(food))
        self._rebuild_scale_options()

    def _on_detail_error(self, token, message):
        if token != self._detail_token:
            return
        self.basis.setText(message)

    def _clear_detail(self):
        self._food = None
        self._per_100 = None
        self._portions = []
        self.detail.hide()

    def _rebuild_scale_options(self):
        '''Options: our unit (weight from the form or worked out from
        USDA portions), each USDA portion, per 100 g.'''
        unit = self._unit or 'unit'
        derived, why = usda.grams_per_unit(self._unit, self._portions) if self._unit else (None, '')
        self._derived = (derived, why)
        self.scale_combo.blockSignals(True)
        self.scale_combo.clear()
        if self._form_weight:
            self.scale_combo.addItem(f'1 × {unit} — your weight, {_fmt(self._form_weight)} g',
                                     ('ours', self._form_weight, f'your weight per {unit}'))
        elif derived:
            self.scale_combo.addItem(f'1 × {unit} — {_fmt(derived)} g from USDA', ('ours', derived, why))
        else:
            self.scale_combo.addItem(f'1 × {unit} — enter its weight', ('ours', None, why))
        for p in self._portions:
            self.scale_combo.addItem(f'USDA: {p["label"]} — {_fmt(p["grams"])} g',
                                     ('portion', p['grams'], f'USDA portion "{p["label"]}"'))
        self.scale_combo.addItem('Per 100 g (USDA basis)', ('portion', 100.0, 'per 100 g'))
        self.scale_combo.setCurrentIndex(0)
        self.scale_combo.blockSignals(False)
        self._on_scale_choice(0)

    def _on_scale_choice(self, index):
        data = self.scale_combo.itemData(index)
        if not data:
            return
        kind, grams, note = data
        self.grams.setText(_fmt(grams, 3) if grams else '')
        unit = self._unit or 'unit'
        self.scale_label.setText(f'Weight of 1 × {unit}' if kind == 'ours' else 'Weight')
        # A USDA portion that disagrees with the form's weight is worth
        # surfacing, not silently overriding.
        derived = self._derived[0]
        if kind == 'ours' and self._form_weight and derived and abs(derived - self._form_weight) / self._form_weight > 0.1:
            self.suggest.setText(
                f'USDA portions put 1 × {unit} at {_fmt(derived)} g, not {_fmt(self._form_weight)} g. '
                f'<a href="use" style="color: {_ROMAINE}">Use {_fmt(derived)} g</a>')
            self.suggest.show()
        elif kind == 'ours' and not grams:
            self.suggest.setText(self._derived[1])
            self.suggest.show()
        else:
            self.suggest.hide()
        self._update_preview(note=note)

    def _use_suggestion(self, _href):
        derived, why = self._derived
        self.grams.setText(_fmt(derived, 3))
        self.suggest.hide()
        self._update_preview(note=why)

    def _current_grams(self):
        try:
            g = float(self.grams.text())
        except ValueError:
            return None
        return g if g > 0 else None

    def _update_preview(self, note=''):
        self._note = note
        grams = self._current_grams()
        unit = self._unit or 'unit'
        if self._per_100 is None:
            return
        if grams is None:
            self.basis.setText(f'Per 100 g. Enter the weight of 1 × {unit} to scale.')
            values = self._per_100
            self.use_btn.setEnabled(False)
        else:
            self.basis.setText(f'Per 1 × {unit} · {_fmt(grams)} g — {note}' if note else
                               f'Per 1 × {unit} · {_fmt(grams)} g')
            values = usda.scale(self._per_100, grams)
            self.use_btn.setEnabled(True)
        for key, _label, suffix in _PREVIEW_ROWS:
            self._value_labels[key].setText(f'{_fmt(values.get(key, 0), 1) or "0"}{suffix}')

    def _on_use(self):
        grams = self._current_grams()
        if grams is None or self._per_100 is None:
            return
        unit = self._unit or 'unit'
        name = usda.describe(self._food or {})
        note = f'Filled from USDA "{name}", scaled to 1 × {unit} ({_fmt(grams)} g).'
        self.valuesChosen.emit(usda.scale(self._per_100, grams), grams, note)

