from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QVBoxLayout,
)

import config
import db


class RecipeCreateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | > NEW RECIPE <')
        self.new_id = 0

        self.name_edit = QLineEdit()
        self.unit_edit = QLineEdit()
        self.yield_edit = QLineEdit()
        self.yield_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))

        form = QFormLayout()
        form.addRow('Name', self.name_edit)
        form.addRow('Yield Unit', self.unit_edit)
        form.addRow('Recipe Yield', self.yield_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Missing Name', 'Recipe name is required.')
            return
        try:
            yield_qty = float(self.yield_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid Yield', 'Recipe Yield must be numeric.')
            return
        self.new_id = db.create_recipe(name, self.unit_edit.text(), yield_qty)
        self.accept()
