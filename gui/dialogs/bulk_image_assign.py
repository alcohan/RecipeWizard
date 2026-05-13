'''Bulk image-assignment dialog. One row per ingredient (label + combo box).
Unassigned rows sort first; combo changes auto-save to the DB.'''
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

import config
import db
from gui.images import available_images


class BulkImageAssignDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Bulk Assign Images')
        self.resize(720, 600)

        self._combos = {}  # ingredient_id -> QComboBox

        scroll_widget = QWidget()
        self._scroll_form = QFormLayout(scroll_widget)
        self._populate_rows()

        scroll = QScrollArea()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)

        refresh_btn = QPushButton('Refresh File List')
        refresh_btn.clicked.connect(self._on_refresh_files)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        hint = QLabel('Unassigned ingredients are listed first. Selections save immediately.')
        hint.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(scroll, stretch=1)
        layout.addLayout(btn_row)

    def _populate_rows(self):
        ingredients = db.get_ingredients()
        # Unassigned (False) sort before assigned (True), then alphabetical.
        ingredients.sort(key=lambda r: (bool(r.get('ImageFilename')), (r['Name'] or '').lower()))
        images = available_images()
        for ing in ingredients:
            ing_id = ing['Id']
            current = ing.get('ImageFilename') or ''
            combo = QComboBox()
            combo.addItems(images)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.currentTextChanged.connect(
                lambda filename, iid=ing_id: db.set_ingredient_image(iid, filename)
            )
            self._combos[ing_id] = combo
            self._scroll_form.addRow(ing['Name'], combo)

    def _on_refresh_files(self):
        images = available_images()
        for combo in self._combos.values():
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(images)
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)
