'''Ingredient-category tag manager.

Single dialog for ingredient-kind tags (the colored badges on the
ingredients table and recipe components). Recipe-format templates live in
their own master/detail manager (`TemplatesManagerDialog` in
template_editor.py) so the identity, items, and overrides for a template
all live in one screen — they used to be split between this dialog and a
sub-editor, which made every edit a two-window dance.

Tags can't move between kinds after creation (would orphan their
mappings), so kind is fixed at New-time.'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QDialog, QHBoxLayout, QInputDialog,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import config
import db


_DEFAULT_COLOR = '#64748b'


class _IngredientTagSection(QWidget):
    '''Table of ingredient-kind tags + New/Delete buttons. Inline edits to
    name and color save on commit.'''

    def __init__(self, title, parent=None):
        super().__init__(parent)

        heading = QLabel(title)
        heading.setStyleSheet('font-weight: bold; padding: 2px 0;')

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['Color', 'Name'])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 64)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemChanged.connect(self._on_item_changed)

        new_btn = QPushButton('New')
        new_btn.clicked.connect(self._on_new)
        delete_btn = QPushButton('Delete')
        delete_btn.clicked.connect(self._on_delete)

        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(heading)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        self.table.blockSignals(True)
        try:
            tags = db.get_tags(kind='ingredient')
            self.table.setRowCount(len(tags))
            for r, tag in enumerate(tags):
                color_btn = QPushButton()
                color_btn.setFixedHeight(22)
                color = tag.get('color') or _DEFAULT_COLOR
                self._style_color_button(color_btn, color)
                color_btn.clicked.connect(
                    lambda _checked=False, tid=tag['id'], btn=color_btn: self._on_pick_color(tid, btn),
                )
                self.table.setCellWidget(r, 0, color_btn)

                name_item = QTableWidgetItem(tag['name'] or '')
                name_item.setData(Qt.UserRole, tag['id'])
                self.table.setItem(r, 1, name_item)
        finally:
            self.table.blockSignals(False)

    def _style_color_button(self, btn, hex_color):
        color = QColor(hex_color)
        if not color.isValid():
            color = QColor(_DEFAULT_COLOR)
        btn.setStyleSheet(
            f'background-color: {color.name()}; border: 1px solid #888; border-radius: 4px;'
        )
        btn.setProperty('current_color', color.name())

    def _on_pick_color(self, tag_id, btn):
        initial = QColor(btn.property('current_color') or _DEFAULT_COLOR)
        picked = QColorDialog.getColor(initial, self, 'Pick tag color')
        if not picked.isValid():
            return
        hex_color = picked.name()
        db.update_tag(tag_id, color=hex_color)
        self._style_color_button(btn, hex_color)

    def _on_item_changed(self, item):
        tag_id = item.data(Qt.UserRole)
        if tag_id is None:
            return
        new_name = item.text().strip()
        if not new_name:
            QMessageBox.warning(self, 'Invalid Name', 'Tag name cannot be empty.')
            self.refresh()
            return
        db.update_tag(tag_id, name=new_name)

    def _on_new(self):
        text, ok = QInputDialog.getText(self, 'New Tag', 'Tag name:', text='Tag')
        if not ok or not text.strip():
            return
        db.create_tag(text.strip(), kind='ingredient', color=_DEFAULT_COLOR)
        self.refresh()

    def _on_delete(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        item = self.table.item(current_row, 1)
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
        self.refresh()


class IngredientTagsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Ingredient Tags')
        self.resize(560, 460)

        hint = QLabel(
            'Categories show up as colored badges on the ingredients '
            'table and recipe components. Double-click a name to rename, '
            'click the swatch to pick a color. Changes save automatically.'
        )
        hint.setEnabled(False)
        hint.setWordWrap(True)

        section = _IngredientTagSection('Ingredient Categories')

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(section, stretch=1)
        layout.addLayout(bottom_row)
