'''Two-pane "New From USDA Search" dialog.

Left pane: the create-ingredient form (the same widget as the blank flow).
Right pane: USDA search box, results list, and a read-only preview of the
currently selected hit.

USDA values are NEVER applied automatically — the user must click
"Use These Values" to copy the preview into the form. This matches the
intended flow: USDA is a quick reference; the user validates everything
before saving.'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QTextEdit, QVBoxLayout,
)

import api.usda
import config
import db
from gui.widgets.ingredient_form import IngredientFormWidget


class IngredientCreateFromUsdaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | > NEW INGREDIENT (USDA Search) <')
        self.resize(1100, 640)
        self.new_id = 0

        self._hits = []
        self._current_prefill = None

        left_box = self._build_left()
        right_box = self._build_right()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_box)
        splitter.addWidget(right_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(buttons)

        self.query_edit.setFocus()

    def _build_left(self):
        box = QGroupBox('New Ingredient')
        self.form = IngredientFormWidget()
        layout = QVBoxLayout(box)
        layout.addWidget(self.form)
        layout.addStretch()
        return box

    def _build_right(self):
        box = QGroupBox('USDA FoodData Central')

        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText('e.g. "kale", "brown rice"')
        self.query_edit.returnPressed.connect(self._search)
        search_btn = QPushButton('Search')
        search_btn.clicked.connect(self._search)

        query_row = QHBoxLayout()
        query_row.addWidget(self.query_edit, stretch=1)
        query_row.addWidget(search_btn)

        self.results = QListWidget()
        self.results.currentRowChanged.connect(self._on_result_selected)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText('Select a result to preview its nutrition data.')

        self.use_btn = QPushButton('←  Use These Values')
        self.use_btn.setEnabled(False)
        self.use_btn.setToolTip('Copy the previewed USDA values into the form on the left.')
        self.use_btn.clicked.connect(self._on_use_prefill)

        layout = QVBoxLayout(box)
        layout.addLayout(query_row)
        layout.addWidget(QLabel('Results:'))
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(QLabel('Preview:'))
        layout.addWidget(self.preview, stretch=1)
        layout.addWidget(self.use_btn)
        return box

    # --- search / preview ---

    def _search(self):
        query = self.query_edit.text().strip()
        if not query:
            return
        self.results.clear()
        self._hits = []
        self._current_prefill = None
        self.use_btn.setEnabled(False)
        self.preview.clear()
        self.preview.setPlaceholderText(f'Searching for "{query}"…')
        QApplication.processEvents()
        try:
            hits = api.usda.search(query)
        except Exception as exc:
            QMessageBox.warning(self, 'Search Failed', str(exc))
            self.preview.setPlaceholderText('Select a result to preview its nutrition data.')
            return
        self._hits = hits
        for hit in hits:
            description = hit.get('description', '(no description)')
            data_type = hit.get('dataType', '')
            self.results.addItem(QListWidgetItem(f'{description}  —  {data_type}'))
        self.preview.setPlaceholderText('Select a result to preview its nutrition data.')
        # Deliberately do NOT auto-select the first row — picking is explicit.
        self.results.setCurrentRow(-1)

    def _on_result_selected(self, row):
        self._current_prefill = None
        self.use_btn.setEnabled(False)
        if row < 0 or row >= len(self._hits):
            self.preview.clear()
            return
        hit = self._hits[row]
        try:
            food = api.usda.get_food_details(hit['fdcId'])
        except Exception as exc:
            QMessageBox.warning(self, 'Fetch Failed', str(exc))
            return
        prefill = api.usda.build_prefill(food, fallback_description=hit.get('description'))
        self._current_prefill = prefill
        self.preview.setPlainText(_format_preview(prefill))
        self.use_btn.setEnabled(True)

    def _on_use_prefill(self):
        if self._current_prefill:
            self.form.apply_prefill(self._current_prefill)

    # --- save ---

    def _on_save(self):
        self.new_id = db.create_ingredient(self.form.collect_values())
        print(f'Created new Ingredient id: {self.new_id}')
        self.accept()


def _format_preview(prefill):
    lines = [
        f"Name:    {prefill.get('Name', '')}",
        f"Unit:    {prefill.get('Unit', '')}",
        f"Weight:  {prefill.get('Weight', '')}",
        '',
    ]
    for key, label in config.nutrition_fields.items():
        lines.append(f'{label:<20} {prefill.get(key, "")}')
    return '\n'.join(lines)
