'''Standalone "New From Blank" create dialog. The combined "New From USDA"
flow lives in ingredient_create_from_usda; both share IngredientFormWidget.'''
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout

import config
import db
from gui.widgets.ingredient_form import IngredientFormWidget


class IngredientCreateDialog(QDialog):
    def __init__(self, parent=None, prefill=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | > NEW INGREDIENT <')
        self.new_id = 0
        self.status_message = ''

        self.form = IngredientFormWidget(prefill=prefill)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setShortcut(QKeySequence.Save)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.form)
        layout.addWidget(buttons)

    def _on_save(self):
        values = self.form.collect_values()
        self.new_id = db.create_ingredient(values)
        self.status_message = f"Created '{values.get('Name', '') or 'ingredient'}'"
        print(f'Created new Ingredient id: {self.new_id}')
        self.accept()
