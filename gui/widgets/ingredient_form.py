'''Reusable demographic + nutrition input form. Shared by the standalone
"New From Blank" dialog and the two-pane "New From USDA" dialog so both
flows go through the same field validation and value-collection code.'''
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget

import config


class IngredientFormWidget(QWidget):
    def __init__(self, prefill=None, parent=None):
        super().__init__(parent)
        prefill = prefill or {}
        self._inputs = {}

        demographic_box = QGroupBox('Demographic')
        demo_form = QFormLayout(demographic_box)
        for key, label in config.ingredient_demographic_fields.items():
            edit = QLineEdit()
            default = '$ 0' if key == 'Cost' else _str(prefill.get(key))
            edit.setText(default)
            if key == 'Weight':
                edit.setValidator(_number_validator())
            self._inputs[key] = edit
            demo_form.addRow(label, edit)

        nutrition_box = QGroupBox('Nutrition')
        nut_form = QFormLayout(nutrition_box)
        for key, label in config.nutrition_fields.items():
            edit = QLineEdit(_str(prefill.get(key)))
            edit.setValidator(_number_validator())
            self._inputs[key] = edit
            nut_form.addRow(label, edit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(demographic_box)
        layout.addWidget(nutrition_box)

    def apply_prefill(self, prefill):
        '''Overwrite current values from a prefill dict. Cost is left alone
        since USDA doesn't supply price data; only keys present in the prefill
        are touched, so partial prefills don't clobber unrelated fields.'''
        if not prefill:
            return
        for key, value in prefill.items():
            edit = self._inputs.get(key)
            if edit is not None:
                edit.setText(_str(value))

    def collect_values(self):
        return {key: edit.text() for key, edit in self._inputs.items()}


def _str(value):
    return '' if value is None else str(value)


def _number_validator():
    v = QDoubleValidator(0.0, 1_000_000.0, 4)
    v.setNotation(QDoubleValidator.StandardNotation)
    return v
