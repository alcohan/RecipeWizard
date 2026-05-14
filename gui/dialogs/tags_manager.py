'''Tag-management dialogs — two separate screens, one per kind.

Both dialogs reuse the private `_TagSection` widget bound to one kind.
The two flows split out because the recipe-template editor has a
substantially different feel (shape selector, per-template Items editor)
from the ingredient-category editor (just color + name), and putting
them side-by-side in one window meant each got cramped.

Single-kind constraint: a tag cannot move between kinds after creation
(would orphan its mappings), so kind is fixed at New-time.'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDialog, QHBoxLayout,
    QInputDialog, QLabel, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
import db


_DEFAULT_COLOR = '#64748b'

# (value stored in DB, label shown in the combo). Only meaningful for
# recipe-kind tags; ingredient tags don't render silhouettes.
_SHAPE_CHOICES = (
    ('none', '(none)'),
    ('ring', 'Ring'),
    ('bowl', 'Bowl'),
    ('wrap', 'Wrap (tilted)'),
    ('tray', 'Tray (rounded square)'),
)


class _TagSection(QWidget):
    '''One table + button row for a single tag kind. Used twice in the
    dialog (recipe-kind tags on the left, ingredient-kind on the right).'''

    def __init__(self, kind, title, parent=None):
        super().__init__(parent)
        self.kind = kind
        # Recipe-kind tags get extra columns: shape selector + items button.
        self._has_shape = (kind == 'recipe')

        heading = QLabel(title)
        heading.setStyleSheet('font-weight: bold; padding: 2px 0;')

        if self._has_shape:
            headers = ['Color', 'Shape', 'Name', 'Items']
        else:
            headers = ['Color', 'Name']
        # Name is always the last data column but for recipe-kind there's
        # an Items button column past it.
        self._name_col = headers.index('Name')
        self._shape_col = 1 if self._has_shape else None
        self._items_col = headers.index('Items') if self._has_shape else None

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 64)
        if self._has_shape:
            self.table.setColumnWidth(1, 170)
            # Items column hosts the "Edit…" button — fixed width keeps it
            # from stealing space from the Name column.
            self.table.setColumnWidth(self._items_col, 110)
            self.table.horizontalHeader().setStretchLastSection(False)
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
        # Suppress itemChanged while we rebuild rows from scratch.
        self.table.blockSignals(True)
        try:
            tags = db.get_tags(kind=self.kind)
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

                if self._has_shape:
                    shape_combo = QComboBox()
                    for value, label in _SHAPE_CHOICES:
                        shape_combo.addItem(label, value)
                    current_shape = tag.get('shape') or 'none'
                    idx = shape_combo.findData(current_shape)
                    if idx >= 0:
                        shape_combo.setCurrentIndex(idx)
                    shape_combo.currentIndexChanged.connect(
                        lambda _i, tid=tag['id'], cb=shape_combo: self._on_shape_changed(tid, cb),
                    )
                    self.table.setCellWidget(r, self._shape_col, shape_combo)

                name_item = QTableWidgetItem(tag['name'] or '')
                name_item.setData(Qt.UserRole, tag['id'])
                self.table.setItem(r, self._name_col, name_item)

                if self._has_shape:
                    items_btn = QPushButton('Edit…')
                    items_btn.clicked.connect(
                        lambda _checked=False, t=dict(tag): self._on_edit_items(t),
                    )
                    self.table.setCellWidget(r, self._items_col, items_btn)
        finally:
            self.table.blockSignals(False)

    def _on_edit_items(self, tag):
        # Lazy import: avoids a circular import if template_editor ever
        # needs anything from this module.
        from gui.dialogs.template_editor import TemplateEditorDialog
        TemplateEditorDialog(tag, parent=self).exec()

    def _on_shape_changed(self, tag_id, combo):
        shape = combo.currentData()
        if shape is None:
            return
        db.update_tag(tag_id, shape=shape)

    def _style_color_button(self, btn, hex_color):
        '''Render the swatch button as a flat solid color. Stored as button
        text=''; the color itself is the swatch.'''
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
        # Only the Name column is editable; the color column hosts a widget,
        # not a QTableWidgetItem, so we'll never get an itemChanged for it.
        tag_id = item.data(Qt.UserRole)
        if tag_id is None:
            return
        new_name = item.text().strip()
        if not new_name:
            QMessageBox.warning(self, 'Invalid Name', 'Tag name cannot be empty.')
            self.refresh()  # restore the prior name
            return
        db.update_tag(tag_id, name=new_name)

    def _on_new(self):
        text, ok = QInputDialog.getText(self, 'New Tag', 'Tag name:', text='Tag')
        if not ok or not text.strip():
            return
        db.create_tag(text.strip(), kind=self.kind, color=_DEFAULT_COLOR)
        self.refresh()

    def _on_delete(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        item = self.table.item(current_row, self._name_col)
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


class _SingleSectionDialog(QDialog):
    '''Shared chrome for the split dialogs — title, hint, one _TagSection,
    bottom Close button. Subclasses just pass kind + copy.'''

    def __init__(self, kind, title, section_title, hint_text, size, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | {title}')
        self.resize(*size)

        hint = QLabel(hint_text)
        hint.setEnabled(False)
        hint.setWordWrap(True)

        section = _TagSection(kind, section_title)

        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.reject)
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        bottom_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addWidget(section, stretch=1)
        layout.addLayout(bottom_row)


class IngredientTagsDialog(_SingleSectionDialog):
    def __init__(self, parent=None):
        super().__init__(
            kind='ingredient',
            title='Ingredient Tags',
            section_title='Ingredient Categories',
            hint_text=(
                'Categories show up as colored badges on the ingredients '
                'table and recipe components. Double-click a name to rename, '
                'click the swatch to pick a color. Changes save automatically.'
            ),
            size=(560, 460),
            parent=parent,
        )


class RecipeTemplatesDialog(_SingleSectionDialog):
    def __init__(self, parent=None):
        super().__init__(
            kind='recipe',
            title='Recipe Templates',
            section_title='Recipe Formats',
            hint_text=(
                'Templates control the silhouette behind a recipe\'s preview '
                'and the items + portion multipliers applied when a recipe '
                'uses that format. Click "Edit…" in a row to set its items.'
            ),
            size=(780, 460),
            parent=parent,
        )
