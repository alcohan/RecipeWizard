'''Tag CRUD via inline editing. Tags are simple (name only), so a
QTableWidget with a single editable column is plenty — no need for the
abstract-model + proxy pattern the larger lists use.'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

import config
import db


class TagsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Tags')
        self.resize(420, 420)

        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(['Name'])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        self._refresh()

        new_btn = QPushButton('New Tag')
        new_btn.clicked.connect(self._on_new)
        delete_btn = QPushButton('Delete')
        delete_btn.clicked.connect(self._on_delete)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        hint = QLabel('Double-click a tag to rename. Renames save automatically.')
        hint.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btn_row)

    def _refresh(self):
        # Suppress itemChanged while we rebuild rows from scratch.
        self.table.blockSignals(True)
        try:
            tags = db.get_tags()
            self.table.setRowCount(len(tags))
            for r, tag in enumerate(tags):
                item = QTableWidgetItem(tag['name'] or '')
                item.setData(Qt.UserRole, tag['id'])
                self.table.setItem(r, 0, item)
        finally:
            self.table.blockSignals(False)

    def _on_item_changed(self, item):
        tag_id = item.data(Qt.UserRole)
        if tag_id is None:
            return
        new_name = item.text().strip()
        if not new_name:
            QMessageBox.warning(self, 'Invalid Name', 'Tag name cannot be empty.')
            self._refresh()  # restore the prior name
            return
        db.update_tag(tag_id, new_name)

    def _on_new(self):
        text, ok = QInputDialog.getText(self, 'New Tag', 'Tag name:', text='Tag')
        if not ok or not text.strip():
            return
        db.create_tag(text.strip())
        self._refresh()

    def _on_delete(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        item = self.table.item(current_row, 0)
        if item is None:
            return
        tag_id = item.data(Qt.UserRole)
        name = item.text()
        if QMessageBox.question(
            self, 'Delete', f"Delete tag '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        db.delete_tag(tag_id)
        self._refresh()
