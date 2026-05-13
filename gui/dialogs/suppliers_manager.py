from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLineEdit, QPushButton,
    QTableView, QVBoxLayout,
)

import config
from gui.dialogs.supplier_edit import SupplierEditDialog
from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.models.suppliers_model import SuppliersModel


class SuppliersManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Suppliers')
        self.resize(720, 480)

        self.model = SuppliersModel(self)
        self.proxy = MultiColumnFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('\U0001F50D  Filter suppliers…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.proxy.setFilterText)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.activated.connect(self._on_activated)
        self.model.modelReset.connect(self.table.resizeColumnsToContents)
        self.table.resizeColumnsToContents()

        new_btn = QPushButton('New Supplier')
        new_btn.clicked.connect(self._on_new)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btn_row)

    def _on_activated(self, view_index):
        if not view_index.isValid():
            return
        src_row = self.proxy.mapToSource(view_index).row()
        supplier_id = self.model.id_at_row(src_row)
        dlg = SupplierEditDialog(supplier_id, parent=self)
        dlg.exec()
        if dlg.modified:
            self.model.refresh()

    def _on_new(self):
        dlg = SupplierEditDialog(parent=self)
        dlg.exec()
        if dlg.modified:
            self.model.refresh()
