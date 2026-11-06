'''New price for one ingredient: supplier, case price and what a case
yields, the per-unit price worked out live, and the date it takes
effect. When a vendor item feeds the ingredient, its last case price
and yield are offered with one click.

Saving adds a row to ingredient_prices (one per ingredient per day: the
same date replaces that day's price); the AFTER INSERT trigger updates
Ingredients.Cost, so callers refresh on Accepted.
'''
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QDoubleValidator, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDateEdit, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout,
)

import db
from gui.widgets import config_kit as kit
from gui.widgets.toolbar_controls import ToolbarCombo
from utilities import purchase_import as pi

_UP = '#8a4a00'
_UP_BG = '#fff0dc'
_DOWN_BG = '#e9f1d9'


def _num_text(value):
    if value is None or value == '':
        return ''
    try:
        return f'{float(value):g}'
    except (TypeError, ValueError):
        return str(value)


def _day(iso):
    try:
        d = QDate.fromString(str(iso)[:10], 'yyyy-MM-dd')
        return d.toString('MMM d, yyyy') if d.isValid() else str(iso)
    except Exception:
        return str(iso)


class IngredientPriceEditDialog(QDialog):
    def __init__(self, ingredient_id, parent=None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id
        self.ingredient = db.get_ingredients(ingredient_id)
        self.unit = (self.ingredient.get('Unit') or 'unit').strip() or 'unit'
        self.latest = db.ingredient_price_latest(ingredient_id) or {}
        self._dates = {str(p['effective_date'])[:10] for p in db.get_ingredient_prices(ingredient_id)}
        self.setWindowTitle('New price')
        self.setMinimumWidth(460)
        self.setStyleSheet(f'QDialog {{ background: {kit.BG}; }}'
                           f' QLineEdit, QDateEdit {{ border: 1px solid {kit.FIELD_BORDER}; border-radius: 4px;'
                           f' background: #ffffff; padding: 4px 8px; min-height: 24px; color: {kit.KALE}; }}'
                           f' QLineEdit:focus, QDateEdit:focus {{ border: 2px solid {kit.ROMAINE}; }}')

        title = kit.heading(f'New price · {self.ingredient["Name"]}')
        title.setWordWrap(True)
        now = ''
        if self.latest.get('unit_price') is not None:
            now = (f'Now ${float(self.latest["unit_price"]):.3f} per {self.unit}'
                   f' · {_day(self.latest.get("effective_date"))}')
        sub = kit.note(now or 'No price yet')

        self.supplier = ToolbarCombo()
        self.supplier.addItem('No supplier', None)
        for s in db.get_suppliers():
            self.supplier.addItem(s['name'] or '', s['id'])
        if self.latest.get('supplier_id') is not None:
            self.supplier.setCurrentIndex(max(0, self.supplier.findData(self.latest['supplier_id'])))

        money = QDoubleValidator(0.0, 1_000_000.0, 4)
        self.case_price = QLineEdit(_num_text(self.latest.get('case_price')))
        self.case_price.setValidator(money)
        self.case_price.setAlignment(Qt.AlignRight)
        self.case_price.setFixedWidth(110)
        self.yields = QLineEdit(_num_text(self.latest.get('units_per_case')))
        self.yields.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.yields.setAlignment(Qt.AlignRight)
        self.yields.setFixedWidth(110)
        yields_unit = QLabel(f'× {self.unit}')
        yields_unit.setStyleSheet(f'color: {kit.MUTED};')
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat('MMM d, yyyy')
        self.notes = QLineEdit()
        self.notes.setPlaceholderText('Optional')
        for w in (self.case_price, self.yields):
            w.textChanged.connect(self._update)
        self.date.dateChanged.connect(lambda _d: self._update())

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        grid.addWidget(kit.eyebrow('Supplier'), 0, 0, 1, 2)
        grid.addWidget(self.supplier, 1, 0, 1, 2)
        grid.addWidget(kit.eyebrow('Case price'), 2, 0)
        grid.addWidget(kit.eyebrow('Case yields'), 2, 1)
        price_row = QHBoxLayout()
        price_row.setSpacing(6)
        dollar = QLabel('$')
        dollar.setStyleSheet(f'color: {kit.MUTED};')
        price_row.addWidget(dollar)
        price_row.addWidget(self.case_price)
        price_row.addStretch()
        grid.addLayout(price_row, 3, 0)
        yield_row = QHBoxLayout()
        yield_row.setSpacing(6)
        yield_row.addWidget(self.yields)
        yield_row.addWidget(yields_unit)
        yield_row.addStretch()
        grid.addLayout(yield_row, 3, 1)
        grid.addWidget(kit.eyebrow('Effective'), 4, 0)
        grid.addWidget(kit.eyebrow('Notes'), 4, 1)
        grid.addWidget(self.date, 5, 0)
        grid.addWidget(self.notes, 5, 1)
        grid.setColumnStretch(1, 1)

        # Vendor item: last case price and yield, one click.
        self.vendor_line = QLabel('')
        self.vendor_line.setTextFormat(Qt.RichText)
        self.vendor_line.setWordWrap(True)
        self.vendor_line.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
        self.vendor_line.linkActivated.connect(lambda _h: self._use_vendor_item())
        self._vendor = self._best_vendor_item()
        if self._vendor is not None:
            v, ppc = self._vendor
            self.vendor_line.setText(
                f'{v["description"]} · ${float(v["last_case_price"]):.2f} a case · {ppc:,.1f} {self.unit} &nbsp;'
                f'<a href="use" style="color: {kit.ROMAINE}">Use</a>')
        self.vendor_line.setVisible(self._vendor is not None)

        # Result: per-unit price and change.
        self.per_unit = QLabel('')
        self.per_unit.setStyleSheet(f'color: {kit.KALE}; font-size: 26px; font-weight: 650;')
        self.change = QLabel('')
        self.per_label = kit.eyebrow(f'Per {self.unit}')
        result = QHBoxLayout()
        result.setSpacing(12)
        result_col = QVBoxLayout()
        result_col.setSpacing(0)
        result_col.addWidget(self.per_label)
        result_col.addWidget(self.per_unit)
        result.addLayout(result_col)
        result.addWidget(self.change, alignment=Qt.AlignBottom)
        result.addStretch()
        self.problem = kit.note('')

        cancel = kit.button('Cancel')
        cancel.clicked.connect(self.reject)
        self.save_btn = kit.button('Save   Ctrl+S', primary=True)
        self.save_btn.clicked.connect(self._on_save)
        QShortcut(QKeySequence.Save, self, activated=self._on_save)
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(cancel)
        foot.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addSpacing(6)
        layout.addLayout(grid)
        layout.addWidget(self.vendor_line)
        layout.addSpacing(6)
        layout.addLayout(result)
        layout.addWidget(self.problem)
        layout.addSpacing(6)
        layout.addLayout(foot)
        self._update()
        self.case_price.setFocus()
        self.case_price.selectAll()

    # --- vendor item ---

    def _best_vendor_item(self):
        '''The mapped vendor item for this ingredient bought most
        recently, with its portions per case, or None.'''
        best = None
        for v in pi.get_vendor_items():
            if v.get('ingredient_id') != self.ingredient_id or v.get('status') != 'mapped':
                continue
            if not v.get('last_case_price'):
                continue
            ppc, _why = pi.portions_per_case(v, v.get('portion_grams'))
            if not ppc:
                continue
            if best is None or (v.get('last_seen') or '') > (best[0].get('last_seen') or ''):
                best = (v, ppc)
        return best

    def _use_vendor_item(self):
        if self._vendor is None:
            return
        v, ppc = self._vendor
        self.case_price.setText(f'{float(v["last_case_price"]):g}')
        self.yields.setText(f'{round(ppc, 4):g}')
        from utilities.purchase_import import match_supplier
        sid = match_supplier(v.get('vendor_name') or '', [{'id': self.supplier.itemData(i), 'name': self.supplier.itemText(i)}
                                                          for i in range(1, self.supplier.count())])
        if sid is not None:
            self.supplier.setCurrentIndex(self.supplier.findData(sid))

    # --- live result ---

    def _values(self):
        try:
            case = float(self.case_price.text())
            per_case = float(self.yields.text())
        except ValueError:
            return None
        if case < 0 or per_case <= 0:
            return None
        return case, per_case

    def _update(self):
        values = self._values()
        problem = ''
        if values is None:
            self.per_unit.setText('—')
            self.change.setText('')
            self.change.setStyleSheet('')
            if self.case_price.text() and self.yields.text():
                problem = 'Case yields must be more than 0'
        else:
            unit_price = values[0] / values[1]
            self.per_unit.setText(f'${unit_price:.3f}')
            old = self.latest.get('unit_price')
            if old:
                pct = (unit_price - float(old)) / float(old) * 100
                if abs(pct) < 0.05:
                    self.change.setText('No change')
                    self.change.setStyleSheet(f'color: {kit.MUTED};')
                else:
                    up = pct > 0
                    self.change.setText(f'{"▲" if up else "▼"} {abs(pct):.1f}%')
                    self.change.setStyleSheet(f'color: {_UP if up else kit.ROMAINE}; background: {_UP_BG if up else _DOWN_BG};'
                                              ' border-radius: 9px; padding: 1px 8px; font-weight: 600;')
            else:
                self.change.setText('')
                self.change.setStyleSheet('')
        day = self.date.date().toString('yyyy-MM-dd')
        if not problem and day in self._dates:
            problem = f'Replaces the {self.date.date().toString("MMM d")} price'
        self.problem.setText(problem)
        self.problem.setVisible(bool(problem))
        self.save_btn.setEnabled(values is not None)

    def _on_save(self):
        values = self._values()
        if values is None:
            return
        db.ingredient_price_new(
            self.ingredient_id,
            (self.supplier.currentData(), values[0], values[1], self.date.date().toString('yyyy-MM-dd'),
             self.notes.text().strip()),
        )
        self.accept()
