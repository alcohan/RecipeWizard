'''Add a new price-history row for an ingredient. The AFTER INSERT trigger
on `ingredient_prices` updates `Ingredients.Cost` to the latest effective
unit price, so the parent dialog should refresh its Cost field on Accept.'''
from PySide6.QtCore import QDate
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
    QMessageBox, QPlainTextEdit, QVBoxLayout,
)

import config
import db


class IngredientPriceEditDialog(QDialog):
    def __init__(self, ingredient_id, parent=None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id
        self.ingredient = db.get_ingredients(ingredient_id)
        self.suppliers = db.get_suppliers()
        latest = db.ingredient_price_latest(ingredient_id) or {}

        self.setWindowTitle(f"{config.APPNAME} | Price: {self.ingredient['Name']}")

        ingredient_field = QLineEdit(self.ingredient['Name'])
        ingredient_field.setReadOnly(True)

        self.supplier_combo = QComboBox()
        self.supplier_combo.addItem('(none)', None)
        for s in self.suppliers:
            self.supplier_combo.addItem(f"{s['name']} [{s['id']}]", s['id'])
        if latest.get('supplier_id') is not None:
            idx = self.supplier_combo.findData(latest['supplier_id'])
            if idx >= 0:
                self.supplier_combo.setCurrentIndex(idx)

        self.case_price = QLineEdit(_fmt_number(latest.get('case_price')))
        self.case_price.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.case_price.textChanged.connect(self._update_unit_price)

        self.units_per_case = QLineEdit(_fmt_number(latest.get('units_per_case')))
        self.units_per_case.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.units_per_case.textChanged.connect(self._update_unit_price)

        self.notes = QPlainTextEdit(latest.get('notes') or '')
        self.notes.setFixedHeight(60)

        self.unit_price_label = QLineEdit()
        self.unit_price_label.setReadOnly(True)

        self.effective_date = QDateEdit()
        self.effective_date.setCalendarPopup(True)
        self.effective_date.setDisplayFormat('yyyy-MM-dd')
        # Default to today; populating from existing latest would re-edit the
        # latest record rather than create a new history row, which doesn't
        # match the "add a new price" intent.
        self.effective_date.setDate(QDate.currentDate())

        form = QFormLayout()
        form.addRow('Ingredient', ingredient_field)
        form.addRow('Supplier', self.supplier_combo)
        form.addRow('Case Price', self.case_price)
        form.addRow(f"Yield (× {self.ingredient['Unit']})", self.units_per_case)
        form.addRow('Yield Calc Notes', self.notes)
        form.addRow('Unit Price', self.unit_price_label)
        form.addRow('Effective Date', self.effective_date)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._update_unit_price()

    def _update_unit_price(self):
        try:
            cp = float(self.case_price.text() or 0)
            upc = float(self.units_per_case.text() or 0)
        except ValueError:
            self.unit_price_label.setText('$ -')
            return
        if upc > 0:
            self.unit_price_label.setText('$ {:.4f}'.format(cp / upc))
        else:
            self.unit_price_label.setText('$ -')

    def _on_save(self):
        try:
            case_price = float(self.case_price.text() or 0)
            units_per_case = float(self.units_per_case.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid Input', 'Case Price and Yield must be numeric.')
            return
        if units_per_case <= 0:
            QMessageBox.warning(self, 'Invalid Input', 'Yield must be greater than zero.')
            return
        supplier_id = self.supplier_combo.currentData()
        effective_date_str = self.effective_date.date().toString('yyyy-MM-dd')
        notes = self.notes.toPlainText()
        db.ingredient_price_new(
            self.ingredient_id,
            (supplier_id, case_price, units_per_case, effective_date_str, notes),
        )
        self.accept()


def _fmt_number(value):
    if value is None or value == '':
        return ''
    try:
        return '{:g}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)
