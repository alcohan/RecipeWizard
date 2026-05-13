'''Pick an ingredient or sub-recipe to add as a component.

Uses a filterable QListWidget rather than QCompleter so the full eligible
set is visible up front (mirrors the old PySimpleGUI listbox UX) and so
Enter inside the filter input can't auto-pick the first item — selection
is always explicit.'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QVBoxLayout,
)

import config
import db


class RecipeComponentAddDialog(QDialog):
    def __init__(self, recipe_id, recipe_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | {recipe_name} | > NEW <')
        self.resize(520, 480)

        self.recipe_id = recipe_id
        # `selected` and `qty` are populated on Accept.
        self.selected = None  # tuple (id, mode, name, unit)
        self.qty = None

        # tuples come back as (id, mode, name, unit)
        self._eligible = db.get_eligible_ingredients(recipe_id)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Type to filter…')
        self.filter_edit.textChanged.connect(self._on_filter)

        self.results = QListWidget()
        for row in self._eligible:
            child_id, mode, name, unit = row
            item = QListWidgetItem(f'{name} ({unit}) - {mode}[{child_id}]')
            item.setData(Qt.UserRole, row)
            self.results.addItem(item)
        self.results.currentItemChanged.connect(self._on_selection_changed)
        self.results.itemActivated.connect(self._on_save)  # double-click or Enter on row

        self.qty_edit = QLineEdit('1')
        self.qty_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.unit_label = QLabel('')

        qty_row = QFormLayout()
        qty_row.addRow('Qty', self.qty_edit)
        qty_row.addRow('', self.unit_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        # Same fix as the USDA dialog: don't let Enter in the filter box
        # silently fire the dialog's accept button.
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Add to {recipe_name}'))
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.results, stretch=1)
        layout.addLayout(qty_row)
        layout.addWidget(buttons)

    def _on_filter(self, text):
        needle = text.strip().lower()
        for i in range(self.results.count()):
            item = self.results.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _on_selection_changed(self, current, _previous):
        if current is None:
            self.unit_label.setText('')
            return
        _, _, _, unit = current.data(Qt.UserRole)
        self.unit_label.setText(f'× {unit}')

    def _on_save(self, *_):
        current = self.results.currentItem()
        if current is None or current.isHidden():
            QMessageBox.warning(self, 'No Selection', 'Pick an ingredient or recipe to add.')
            return
        try:
            qty = float(self.qty_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid Qty', 'Qty must be numeric.')
            return
        if qty <= 0:
            QMessageBox.warning(self, 'Invalid Qty', 'Qty must be greater than zero.')
            return
        self.selected = current.data(Qt.UserRole)
        self.qty = qty
        self.accept()
