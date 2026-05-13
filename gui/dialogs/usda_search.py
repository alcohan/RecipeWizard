'''USDA FoodData Central search picker.

Lets the user type a query, see the top matches, and pick which one becomes
the prefill for a new ingredient. Replaces the old "take top hit blindly"
flow — the user is meant to validate before saving.'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
)

import api.usda
import config


class UsdaSearchDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | New From Search')
        self.resize(540, 420)

        self.selected_prefill = None  # set on accept
        self._hits = []

        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText('e.g. "kale", "brown rice"')
        self.query_edit.returnPressed.connect(self._search)

        search_btn = QPushButton('Search')
        search_btn.clicked.connect(self._search)

        query_row = QHBoxLayout()
        query_row.addWidget(self.query_edit, stretch=1)
        query_row.addWidget(search_btn)

        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self._accept_selected)

        self.status_label = QLabel('Enter a search term and press Enter or Search.')
        self.status_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Use Selected')
        buttons.accepted.connect(self._accept_selected)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(query_row)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(buttons)

    def _search(self):
        query = self.query_edit.text().strip()
        if not query:
            return
        self.results.clear()
        self._hits = []
        self.status_label.setText(f'Searching for "{query}"…')
        QApplication.processEvents()
        try:
            hits = api.usda.search(query)
        except Exception as exc:
            self.status_label.setText('')
            QMessageBox.warning(self, 'Search Failed', str(exc))
            return
        self._hits = hits
        for hit in hits:
            description = hit.get('description', '(no description)')
            data_type = hit.get('dataType', '')
            item = QListWidgetItem(f'{description}  —  {data_type}')
            self.results.addItem(item)
        self.status_label.setText(f'{len(hits)} result(s). Double-click or click Use Selected.')
        if hits:
            self.results.setCurrentRow(0)

    def _accept_selected(self, _item=None):
        row = self.results.currentRow()
        if row < 0 or row >= len(self._hits):
            return
        hit = self._hits[row]
        try:
            food = api.usda.get_food_details(hit['fdcId'])
        except Exception as exc:
            QMessageBox.warning(self, 'Fetch Failed', str(exc))
            return
        self.selected_prefill = api.usda.build_prefill(food, fallback_description=hit.get('description'))
        self.accept()
