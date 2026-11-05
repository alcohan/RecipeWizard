'''The case-yield editor for one vendor item, shared by the Import
purchases dialog (Map new items) and Configure › Vendor items.

Ingredient (searchable), case holds + unit, yield % or portions per
each, yield notes, then the portions-per-case math and the cost of one
portion at the item's average case price. Emits `changed` on any edit.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox, QCompleter, QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from gui.widgets import config_kit as kit
from utilities import purchase_import as pi


class VendorItemEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ingredients = {}
        self._case_price = None
        self._loading = False

        self.ingredient = QComboBox()
        self.ingredient.setEditable(True)
        self.ingredient.setInsertPolicy(QComboBox.NoInsert)
        self.ingredient.setMinimumWidth(260)
        self.ingredient.lineEdit().setPlaceholderText('Search ingredients…')
        completer = self.ingredient.completer()
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.ingredient.currentIndexChanged.connect(self._on_edit)
        self.portion = QLabel('—')
        self.portion.setStyleSheet(f'color: {kit.MUTED};')

        number = QDoubleValidator(0.0, 1_000_000.0, 4)
        number.setNotation(QDoubleValidator.StandardNotation)
        self.qty = kit.field(90)
        self.qty.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.qty.setValidator(number)
        self.unit = QComboBox()
        self.unit.addItems(list(pi.CASE_UNITS))
        self.unit.setMinimumHeight(32)
        self.third_label = kit.eyebrow('Yield %')
        self.third = kit.field(90)
        self.third.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.third.setValidator(QDoubleValidator(0.0, 100_000.0, 4))
        self.notes = kit.field()
        self.notes.setPlaceholderText('e.g. chopped, 10% trim')
        for w in (self.qty, self.third, self.notes):
            w.textEdited.connect(self._on_edit)
        self.unit.currentIndexChanged.connect(self._on_unit)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.addWidget(kit.eyebrow('Ingredient'), 0, 0, 1, 3)
        grid.addWidget(kit.eyebrow('Portion'), 0, 3)
        grid.addWidget(self.ingredient, 1, 0, 1, 3)
        grid.addWidget(self.portion, 1, 3)
        grid.addWidget(kit.eyebrow('Case holds'), 2, 0)
        grid.addWidget(kit.eyebrow('Unit'), 2, 1)
        grid.addWidget(self.third_label, 2, 2)
        grid.addWidget(kit.eyebrow('Yield notes'), 2, 3)
        grid.addWidget(self.qty, 3, 0)
        grid.addWidget(self.unit, 3, 1)
        grid.addWidget(self.third, 3, 2)
        grid.addWidget(self.notes, 3, 3)
        grid.setColumnStretch(3, 1)

        math = QFrame()
        math.setObjectName('YieldMath')
        math.setStyleSheet(f'QFrame#YieldMath {{ background: {kit.BG}; border-radius: 8px; }}')
        ml = QHBoxLayout(math)
        ml.setContentsMargins(12, 10, 12, 10)
        self.formula = QLabel('')
        self.formula.setWordWrap(True)
        self.formula.setStyleSheet(f'color: {kit.MUTED};')
        self.per_portion = QLabel('')
        self.per_portion.setStyleSheet(f'color: {kit.KALE}; font-size: 15px; font-weight: 650;')
        ml.addWidget(self.formula, stretch=1)
        ml.addWidget(self.per_portion)

        self.pack_note = kit.note('')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(grid)
        layout.addWidget(math)
        layout.addWidget(self.pack_note)

    # --- data ----------------------------------------------------------

    def set_ingredients(self, ingredients):
        self._ingredients = {i['Id']: i for i in ingredients}
        self._loading = True
        self.ingredient.clear()
        self.ingredient.addItem('', None)
        for ing in ingredients:
            self.ingredient.addItem(ing['Name'], ing['Id'])
        self._loading = False

    def set_item(self, item, case_price=None):
        '''Fill from a vendor item dict; `case_price` is what one case
        cost on average (for the per-portion figure).'''
        self._loading = True
        self._case_price = case_price
        idx = self.ingredient.findData(item.get('ingredient_id')) if item.get('ingredient_id') else 0
        self.ingredient.setCurrentIndex(max(idx, 0))
        qty = item.get('case_qty')
        unit = item.get('case_unit')
        pack = pi.parse_pack(item.get('pack_size'))
        if not qty and pack:
            qty, unit = pack['qty'], pack['unit']
        self.qty.setText(_fmt(qty))
        self.unit.setCurrentText(unit or 'lb')
        self._third_values = {'yield': item.get('yield_pct'), 'each': item.get('portions_per_each')}
        self.notes.setText(item.get('notes') or '')
        if pack:
            self.pack_note.setText(f'Pack size “{item.get("pack_size")}” was read as {pack["reading"]}.'
                                   ' Change it if the case is packed differently.')
        elif item.get('pack_size'):
            self.pack_note.setText(f'Pack size “{item.get("pack_size")}” couldn’t be read; enter what a case'
                                   ' holds (for cans, the drained weight).')
        else:
            self.pack_note.setText('')
        self._show_third()
        self._loading = False
        self._refresh()

    def item_values(self):
        '''The edited fields, ready to merge into the vendor item.'''
        each = self.unit.currentText() == 'ea'
        third = _num(self.third.text())
        return {
            'ingredient_id': self.ingredient.currentData(),
            'case_qty': _num(self.qty.text()),
            'case_unit': self.unit.currentText(),
            'yield_pct': 100.0 if each else (third if third is not None else 100.0),
            'portions_per_each': third if each else None,
            'notes': self.notes.text().strip() or None,
        }

    def ingredient_id(self):
        return self.ingredient.currentData()

    def per_portion_cost(self):
        ing = self._ingredients.get(self.ingredient.currentData())
        if not ing or not self._case_price:
            return None
        ppc, _ = pi.portions_per_case(self.item_values(), ing.get('Weight'))
        return self._case_price / ppc if ppc else None

    # --- updates -------------------------------------------------------

    def _show_third(self):
        '''Yield % for weights and volumes, portions per each for counts.'''
        each = self.unit.currentText() == 'ea'
        vals = getattr(self, '_third_values', {})
        self.third_label.setText('PORTIONS PER EA' if each else 'YIELD %')
        value = vals.get('each') if each else vals.get('yield')
        if value is None:
            value = 1 if each else 100
        self.third.setText(_fmt(value))

    def _on_unit(self, *_):
        if self._loading:
            return
        self._loading = True
        self._show_third()
        self._loading = False
        self._refresh()
        self.changed.emit()

    def _on_edit(self, *_):
        if self._loading:
            return
        each = self.unit.currentText() == 'ea'
        vals = getattr(self, '_third_values', {})
        vals['each' if each else 'yield'] = _num(self.third.text())
        self._third_values = vals
        self._refresh()
        self.changed.emit()

    def _refresh(self):
        ing = self._ingredients.get(self.ingredient.currentData())
        if ing is None:
            self.portion.setText('—')
            self.formula.setText('Pick an ingredient to work out portions per case.')
            self.per_portion.setText('')
            return
        grams = ing.get('Weight')
        unit = (ing.get('Unit') or '').strip()
        self.portion.setText(f'{unit} · {_fmt(grams)} g' if grams else f'{unit} · no weight')
        values = self.item_values()
        self.formula.setText(pi.yield_formula(values, grams))
        cost = self.per_portion_cost()
        self.per_portion.setText(f'Per portion {pi.money(cost, 3)}' if cost is not None else '')


def _num(text):
    try:
        return float(str(text).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _fmt(value):
    if value is None or value == '':
        return ''
    try:
        return f'{float(value):g}'
    except (TypeError, ValueError):
        return str(value)
