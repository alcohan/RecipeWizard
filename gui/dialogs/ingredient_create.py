'''Create-ingredient dialog. Captures demographic + nutrition fields and saves
a new Ingredients row. Optionally prefilled from a USDA hit. The full edit
dialog (allergens, image, price history) is opened after creation by the
caller, so the user can validate/complete the data.'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLineEdit, QVBoxLayout,
)

import config
import db


class IngredientCreateDialog(QDialog):
    def __init__(self, parent=None, prefill=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | > NEW INGREDIENT <')
        self.new_id = 0
        prefill = prefill or {}

        self._inputs = {}

        demographic_box = QGroupBox('Demographic')
        demo_form = QFormLayout(demographic_box)
        for key, label in config.ingredient_demographic_fields.items():
            edit = QLineEdit()
            default = '$ 0' if key == 'Cost' else str(prefill.get(key, '') or '')
            edit.setText(default)
            if key in ('Weight', 'Cost'):
                edit.setValidator(_currency_validator() if key == 'Cost' else _number_validator())
            self._inputs[key] = edit
            demo_form.addRow(label, edit)

        nutrition_box = QGroupBox('Nutrition')
        nut_form = QFormLayout(nutrition_box)
        for key, label in config.nutrition_fields.items():
            edit = QLineEdit()
            edit.setText(str(prefill.get(key, '') or ''))
            edit.setValidator(_number_validator())
            self._inputs[key] = edit
            nut_form.addRow(label, edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(demographic_box)
        layout.addWidget(nutrition_box)
        layout.addWidget(buttons)

    def _collect_values(self):
        return {key: edit.text() for key, edit in self._inputs.items()}

    def _on_save(self):
        values = self._collect_values()
        # db.create_ingredient runs the same `sub(r'[^\d.]', '', cost)` strip
        # we used to do client-side, so the leading "$ " in Cost is fine.
        self.new_id = db.create_ingredient(values)
        print(f'Created new Ingredient id: {self.new_id}')
        self.accept()


def _number_validator():
    v = QDoubleValidator(0.0, 1_000_000.0, 4)
    v.setNotation(QDoubleValidator.StandardNotation)
    return v


def _currency_validator():
    # Accept leading "$ " etc. by being permissive on input; the model
    # downstream strips non-digit/period chars anyway.
    v = QDoubleValidator()
    v.setNotation(QDoubleValidator.StandardNotation)
    return v
