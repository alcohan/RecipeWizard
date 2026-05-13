from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QVBoxLayout,
)

import config
import db


class SupplierEditDialog(QDialog):
    FIELDS = (
        ('name', 'Name'),
        ('address', 'Address'),
        ('city', 'City'),
        ('state', 'State'),
        ('zip', 'Zip'),
    )

    def __init__(self, supplier_id=None, parent=None):
        super().__init__(parent)
        self.supplier_id = supplier_id
        self.modified = False
        is_new = supplier_id is None

        if is_new:
            row = {key: '' for key, _ in self.FIELDS}
            title_suffix = '> NEW SUPPLIER <'
        else:
            row = db.get_suppliers(supplier_id) or {key: '' for key, _ in self.FIELDS}
            title_suffix = row.get('name') or ''

        self.setWindowTitle(f'{config.APPNAME} | Supplier | {title_suffix}')

        self._inputs = {}
        form = QFormLayout()
        for key, label in self.FIELDS:
            edit = QLineEdit(row.get(key) or '')
            self._inputs[key] = edit
            form.addRow(label, edit)

        button_box = QDialogButtonBox()
        save_btn = button_box.addButton('Save', QDialogButtonBox.AcceptRole)
        save_btn.setShortcut(QKeySequence.Save)
        delete_btn = button_box.addButton('Delete', QDialogButtonBox.DestructiveRole)
        delete_btn.setVisible(not is_new)
        delete_btn.setStyleSheet('background-color: #c0392b; color: white; padding: 4px 10px;')
        cancel_btn = button_box.addButton(
            'Cancel' if is_new else 'Close', QDialogButtonBox.RejectRole,
        )
        save_btn.clicked.connect(self._on_save)
        delete_btn.clicked.connect(self._on_delete)
        cancel_btn.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

    def _values(self):
        return {key: edit.text() for key, edit in self._inputs.items()}

    def _on_save(self):
        values = self._values()
        if not values['name'].strip():
            QMessageBox.warning(self, 'Missing Name', 'Supplier name is required.')
            return
        if self.supplier_id is None:
            db.create_supplier(values)
        else:
            db.update_supplier(self.supplier_id, values)
        self.modified = True
        self.accept()

    def _on_delete(self):
        name = self._inputs['name'].text()
        if QMessageBox.question(
            self, 'Delete', f'Delete {name}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_supplier(self.supplier_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Supplier In Use', str(exc))
            return
        self.modified = True
        self.accept()
