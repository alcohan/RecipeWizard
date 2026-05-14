'''Edit a recipe-format template — the per-tag list of auto-add items and
the per-category portion multipliers.

When the user changes a recipe's Format in the recipe-edit dialog, the
template's items are added to the recipe (skipping anything already there)
and its multipliers scale matching ingredient categories. See
db.transition_recipe_format for the apply/unapply flow.

Layout: items table on the left, ingredient-category multipliers on the
right. Mutations write through immediately — there's no Save button.'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.widgets.tag_badge import TagBadgeCellDelegate, TagColorRole


class _QuantityDelegate(QStyledItemDelegate):
    '''Numeric editor for the items table's Quantity column — same shape
    as the recipe edit dialog's, but local so we don't add a public
    cross-dialog dependency for one trivial widget.'''

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        v = QDoubleValidator(0.0001, 1_000_000.0, 4, editor)
        v.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(v)
        return editor


class TemplateEditorDialog(QDialog):
    def __init__(self, tag, parent=None):
        '''`tag` is a dict from db.get_tags() with id/name/color/shape/kind.
        Must be a kind='recipe' tag.'''
        super().__init__(parent)
        self.tag = tag
        self.tag_id = tag['id']
        self.setWindowTitle(f"{config.APPNAME} | Template: {tag['name']}")
        self.resize(820, 560)

        items_box = self._build_items_box()
        multipliers_box = self._build_multipliers_box()

        columns = QHBoxLayout()
        columns.addWidget(items_box, stretch=2)
        columns.addWidget(multipliers_box, stretch=1)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self.accept)

        header = QLabel(
            f"<b>{tag['name']}</b> — items added when this format is applied; "
            'multipliers scale matching ingredient categories.'
        )
        header.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addLayout(columns, stretch=1)
        layout.addWidget(button_box)

        self._refresh_items()

    # --- items section ---

    def _build_items_box(self):
        box = QGroupBox('Items')
        self.items_table = QTableWidget(0, 3)
        self.items_table.setHorizontalHeaderLabels(['Name', 'Type', 'Quantity'])
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed,
        )
        self.items_table.horizontalHeader().setStretchLastSection(False)
        self.items_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.items_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.items_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.items_table.setItemDelegateForColumn(1, TagBadgeCellDelegate(self.items_table))
        self.items_table.setItemDelegateForColumn(2, _QuantityDelegate(self.items_table))
        self.items_table.itemChanged.connect(self._on_item_changed)

        add_btn = QPushButton('+ Add Item')
        add_btn.clicked.connect(self._on_add)
        remove_btn = QPushButton('Remove')
        remove_btn.clicked.connect(self._on_remove)

        button_row = QHBoxLayout()
        button_row.addWidget(add_btn)
        button_row.addWidget(remove_btn)
        button_row.addStretch()

        layout = QVBoxLayout(box)
        layout.addWidget(self.items_table, stretch=1)
        layout.addLayout(button_row)
        return box

    def _refresh_items(self):
        self.items_table.blockSignals(True)
        try:
            rows = db.get_tag_components(self.tag_id)
            self.items_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                name_item = QTableWidgetItem(row['Name'] or '')
                # Hold the tag_component id on the Name cell; one cell per
                # row is enough since itemChanged for any cell can look it
                # up here.
                name_item.setData(Qt.UserRole, row['id'])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)

                type_item = QTableWidgetItem(row['Type'] or '')
                # Match the components table's badge palette — sub-recipes
                # get the violet 'recipe' label, ingredients keep their
                # category color (if any) for consistency with the recipe
                # edit dialog.
                if row['Type'] == 'ingredient':
                    cat = db.get_ingredient_tag(row['child_ingredient']) if row['child_ingredient'] else None
                    if cat:
                        type_item.setText(cat['name'])
                        type_item.setData(TagColorRole, cat['color'])
                    else:
                        type_item.setData(TagColorRole, '#94a3b8')
                else:
                    type_item.setText('recipe')
                    type_item.setData(TagColorRole, '#7c3aed')
                type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)

                qty_item = QTableWidgetItem(_fmt_qty(row['quantity']))
                qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                self.items_table.setItem(r, 0, name_item)
                self.items_table.setItem(r, 1, type_item)
                self.items_table.setItem(r, 2, qty_item)
        finally:
            self.items_table.blockSignals(False)

    def _on_item_changed(self, item):
        # Only the Quantity column is editable; bail otherwise.
        if item.column() != 2:
            return
        name_item = self.items_table.item(item.row(), 0)
        if name_item is None:
            return
        tag_component_id = name_item.data(Qt.UserRole)
        try:
            qty = float(item.text())
        except (TypeError, ValueError):
            self._refresh_items()
            return
        if qty <= 0:
            self._refresh_items()
            return
        db.update_tag_component_quantity(tag_component_id, qty)

    def _on_add(self):
        # Reuse the recipe component picker. recipe_id=0 effectively means
        # "no cycle exclusions" — get_eligible_ingredients filters out
        # recipes whose tree reaches the given parent, and no recipe has
        # Id=0, so every ingredient/recipe is offered.
        dlg = RecipeComponentAddDialog(0, f"Template: {self.tag['name']}", parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        child_id, mode, _name, _unit, *_ = dlg.selected
        # Skip if this template already has the same item — adding twice
        # would create duplicate auto-add rows.
        existing = db.get_tag_components(self.tag_id)
        for row in existing:
            if mode == 'ingredient' and row['child_ingredient'] == child_id:
                QMessageBox.information(self, 'Already Added', 'This template already includes that item.')
                return
            if mode == 'recipe' and row['child_recipe'] == child_id:
                QMessageBox.information(self, 'Already Added', 'This template already includes that item.')
                return
        db.add_tag_component(self.tag_id, mode, child_id, dlg.qty)
        self._refresh_items()

    def _on_remove(self):
        r = self.items_table.currentRow()
        if r < 0:
            return
        name_item = self.items_table.item(r, 0)
        if name_item is None:
            return
        tag_component_id = name_item.data(Qt.UserRole)
        db.delete_tag_component(tag_component_id)
        self._refresh_items()

    # --- multipliers section ---

    def _build_multipliers_box(self):
        box = QGroupBox('Portion multipliers by category')
        info = QLabel(
            'A multiplier of 1.0 keeps quantities as-is. 0.3 means "scale '
            'matching ingredients to 30% when this format is applied."'
        )
        info.setEnabled(False)
        info.setWordWrap(True)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        # Render each ingredient-category as: [colored swatch + name] [spinbox]
        for row in db.get_tag_category_multipliers(self.tag_id):
            label_widget = _CategoryLabel(row['category_name'], row['category_color'])

            spin = QDoubleSpinBox()
            spin.setRange(0.0, 100.0)
            spin.setSingleStep(0.1)
            spin.setDecimals(2)
            spin.setValue(float(row['multiplier']))
            cat_id = row['category_tag_id']
            spin.valueChanged.connect(
                lambda value, c=cat_id: db.set_tag_category_multiplier(self.tag_id, c, value),
            )
            form.addRow(label_widget, spin)

        layout = QVBoxLayout(box)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addStretch()
        return box


class _CategoryLabel(QLabel):
    '''Small label widget that paints a colored chip + category name as the
    left column of the multipliers form. Self-contained so the form can
    sit in a regular QFormLayout.'''

    def __init__(self, name, color):
        super().__init__(name)
        # The swatch lives in the label's background as a chip via paint
        # event — keeps the form column light. We get away with just
        # styling the QLabel since text doesn't need to share space with
        # the chip (the chip is shown via stylesheet padding + background).
        from PySide6.QtGui import QColor as _QC
        c = _QC(color or '#64748b')
        if not c.isValid():
            c = _QC('#64748b')
        self.setStyleSheet(
            f'padding: 2px 8px; border-left: 6px solid {c.name()};'
            'background: transparent;'
        )


def _fmt_qty(value):
    if value is None:
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:.4f}'.rstrip('0').rstrip('.')
