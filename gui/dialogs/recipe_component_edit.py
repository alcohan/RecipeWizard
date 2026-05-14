'''Edit qty or remove an existing recipe component. The caller maps the
result_action ("update" | "delete") into a SetComponentQtyCommand or
RemoveComponentCommand pushed onto the recipe dialog's undo stack.'''
from PySide6.QtGui import QDoubleValidator, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox,
    QVBoxLayout,
)

import config


class RecipeComponentEditDialog(QDialog):
    def __init__(self, recipe_name, component, parent=None):
        super().__init__(parent)
        self.component = component
        self.result_action = None  # 'update' or 'delete'
        self.new_qty = None

        name = component['Name']
        qty = component['Quantity']
        unit = component['Unit']
        self.setWindowTitle(f'{config.APPNAME} | {recipe_name} | {name}')

        self.qty_edit = QLineEdit(str(qty))
        self.qty_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))

        form = QFormLayout()
        form.addRow(QLabel(f'Editing {name} in {recipe_name}'))
        form.addRow(f'Qty ({unit})', self.qty_edit)

        button_box = QDialogButtonBox()
        save_btn = button_box.addButton('Save', QDialogButtonBox.AcceptRole)
        save_btn.setShortcut(QKeySequence.Save)
        delete_btn = button_box.addButton('Delete', QDialogButtonBox.DestructiveRole)
        delete_btn.setStyleSheet('background-color: #c0392b; color: white; padding: 4px 10px;')
        cancel_btn = button_box.addButton('Cancel', QDialogButtonBox.RejectRole)
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)
        cancel_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def _on_save(self):
        try:
            self.new_qty = float(self.qty_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid Qty', 'Quantity must be numeric.')
            return
        if self.new_qty <= 0:
            QMessageBox.warning(self, 'Invalid Qty', 'Quantity must be greater than zero.')
            return
        self.result_action = 'update'
        self.accept()

    def _on_delete(self):
        self.result_action = 'delete'
        self.accept()
