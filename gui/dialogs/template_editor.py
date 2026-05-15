'''Recipe-format templates manager — master/detail UI.

Left pane lists every recipe-kind tag (one per template). The right pane
edits the selected template's identity (name, color, shape), shows a live
silhouette preview, and lets the user manage its auto-add items and any
non-1.0 category multipliers ("portion overrides").

Replaces the older split between RecipeTemplatesDialog (the all-templates
list) and TemplateEditorDialog (per-template items + multipliers); putting
identity, items, and overrides in one screen avoids bouncing between
dialogs to make a single conceptual change.

Writes are immediate — no Save button. Items + overrides write through
db.* helpers directly; recipes already tagged with a template do NOT get
re-applied here (that happens lazily via db.reconcile_recipe_template
when the recipe is opened, plus the existing transition flow when the
format changes).'''
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QDoubleValidator, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QStyledItemDelegate, QTableWidget, QTableWidgetItem, QSplitter,
    QToolButton, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.widgets.tag_badge import TagBadgeCellDelegate, TagColorRole
from utilities.wedge_renderer import render_recipe


_DEFAULT_COLOR = '#64748b'

# (db value, display label). Each must match a branch in
# utilities/wedge_renderer._paint_silhouette and an entry in
# wedge_renderer._KNOWN_SHAPES.
_SHAPE_CHOICES = (
    ('none', '(none)'),
    ('ring', 'Ring'),
    ('bowl', 'Bowl'),
    ('plate', 'Plate (wide rim)'),
    ('wrap', 'Wrap (tilted)'),
    ('tray', 'Tray (rounded square)'),
    ('box', 'Box (sharp square)'),
    ('jar', 'Jar (tall)'),
    ('cone', 'Cone (taco / hand-held)'),
)

_SILHOUETTE_SIZE = 120


class _QuantityDelegate(QStyledItemDelegate):
    '''Numeric editor for the items table's Quantity column.'''

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        v = QDoubleValidator(0.0001, 1_000_000.0, 4, editor)
        v.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(v)
        return editor


class _SilhouettePreview(QLabel):
    '''Small wedge preview showing just the template's silhouette + color.

    Reuses `render_recipe([])` so the silhouette path stays consistent with
    what the home gallery and recipe edit dialog draw. An empty component
    list renders the silhouette behind a plain grey outline circle.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_SILHOUETTE_SIZE, _SILHOUETTE_SIZE)
        self.setAlignment(Qt.AlignCenter)
        self._show_empty()

    def update_preview(self, shape, color):
        png = render_recipe(
            [], size=_SILHOUETTE_SIZE,
            shape=shape, shape_color=color,
        )
        if not png:
            self._show_empty()
            return
        image = QImage()
        if not image.loadFromData(png) or image.isNull():
            self._show_empty()
            return
        self.setPixmap(QPixmap.fromImage(image))

    def _show_empty(self):
        # Cheap placeholder when PIL isn't available or render fails.
        self.setText('')


class TemplatesManagerDialog(QDialog):
    '''Master-detail editor for every recipe-format template.

    Open via Manage → Recipe Templates. Closing returns to the home gallery.
    The Manage menu's wrapping refresh() picks up any silhouette / color
    changes so the homepage cards reflect them.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Recipe Templates')
        self.resize(960, 620)

        self.current_tag_id = None

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self._build_list_pane())
        self.splitter.addWidget(self._build_editor_pane())
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([240, 720])

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter, stretch=1)
        layout.addWidget(button_box)

        self._refresh_list()
        # Select the first template so the right pane has something to show
        # on open — otherwise the editor looks broken.
        if self.tag_list.count() > 0:
            self.tag_list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)

    # --- left pane: template list ---

    def _build_list_pane(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 6, 0)

        self.tag_list = QListWidget()
        self.tag_list.setIconSize(QSize(16, 16))
        self.tag_list.setUniformItemSizes(False)
        self.tag_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tag_list.currentItemChanged.connect(self._on_tag_selected)

        new_btn = QPushButton('New')
        new_btn.clicked.connect(self._on_new)
        del_btn = QPushButton('Delete')
        del_btn.clicked.connect(self._on_delete)
        btn_row = QHBoxLayout()
        btn_row.addWidget(new_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()

        layout.addWidget(self.tag_list, stretch=1)
        layout.addLayout(btn_row)
        return wrap

    def _refresh_list(self):
        '''Rebuild the template list from db. Tries to keep the currently
        selected tag selected; otherwise selects the first row.'''
        self.tag_list.blockSignals(True)
        try:
            self.tag_list.clear()
            for tag in db.get_tags(kind='recipe'):
                item = self._make_list_item(tag)
                self.tag_list.addItem(item)
                if tag['id'] == self.current_tag_id:
                    self.tag_list.setCurrentItem(item)
        finally:
            self.tag_list.blockSignals(False)
        # If no item is current (e.g. after delete), pick the first row so
        # the editor pane never sits with stale data from a deleted tag.
        if self.tag_list.currentRow() < 0 and self.tag_list.count() > 0:
            self.tag_list.setCurrentRow(0)
            return
        # If a current item exists but signals were blocked during refresh,
        # re-emit so the editor pane re-syncs against any name/color edits.
        cur = self.tag_list.currentItem()
        if cur is not None:
            self._on_tag_selected(cur, None)

    def _make_list_item(self, tag):
        items_count = len(db.get_tag_components(tag['id']))
        overrides_count = sum(
            1 for m in db.get_tag_category_multipliers(tag['id'])
            if abs(m['multiplier'] - 1.0) > 1e-9
        )
        used_by = db.query(
            'SELECT COUNT(*) AS c FROM recipe_tags_mapping WHERE tag_id=?;',
            (tag['id'],), one=True,
        )['c']
        # Use rich text so the subline reads as muted secondary info.
        #   (nbsp) keeps the swatch + name from line-wrapping awkwardly.
        sub_parts = [f"{items_count} item{'' if items_count == 1 else 's'}"]
        if overrides_count:
            sub_parts.append(
                f"{overrides_count} override{'' if overrides_count == 1 else 's'}"
            )
        sub_parts.append(
            f"used by {used_by} recipe{'' if used_by == 1 else 's'}"
        )
        text = f"{tag['name']}\n{' · '.join(sub_parts)}"
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, tag['id'])
        # Colored swatch as the icon column.
        item.setData(Qt.DecorationRole, _swatch_pixmap(tag.get('color')))
        return item

    # --- right pane: editor ---

    def _build_editor_pane(self):
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(8, 0, 0, 0)

        # Header: name, color, shape combo, silhouette preview
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_committed)

        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(28, 22)
        self.color_btn.clicked.connect(self._on_pick_color)

        self.shape_combo = QComboBox()
        for value, label in _SHAPE_CHOICES:
            self.shape_combo.addItem(label, value)
        self.shape_combo.currentIndexChanged.connect(self._on_shape_changed)

        self.silhouette = _SilhouettePreview()

        identity_form = QFormLayout()
        identity_form.setLabelAlignment(Qt.AlignRight)
        identity_form.addRow('Name', self.name_edit)
        color_row = QHBoxLayout()
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        color_wrap = QWidget()
        color_wrap.setLayout(color_row)
        identity_form.addRow('Color', color_wrap)
        identity_form.addRow('Shape', self.shape_combo)

        header_row = QHBoxLayout()
        header_row.addLayout(identity_form, stretch=1)
        header_row.addWidget(self.silhouette)
        layout.addLayout(header_row)

        layout.addWidget(_divider())

        # Items table
        items_box = QGroupBox('Items')
        self.items_table = QTableWidget(0, 3)
        self.items_table.setHorizontalHeaderLabels(['Name', 'Type', 'Quantity'])
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed,
        )
        hh = self.items_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.items_table.setItemDelegateForColumn(1, TagBadgeCellDelegate(self.items_table))
        self.items_table.setItemDelegateForColumn(2, _QuantityDelegate(self.items_table))
        self.items_table.itemChanged.connect(self._on_item_changed)

        add_item_btn = QPushButton('+ Add Item')
        add_item_btn.clicked.connect(self._on_add_item)
        remove_item_btn = QPushButton('Remove')
        remove_item_btn.clicked.connect(self._on_remove_item)
        items_btn_row = QHBoxLayout()
        items_btn_row.addWidget(add_item_btn)
        items_btn_row.addWidget(remove_item_btn)
        items_btn_row.addStretch()
        items_layout = QVBoxLayout(items_box)
        items_layout.addWidget(self.items_table, stretch=1)
        items_layout.addLayout(items_btn_row)
        layout.addWidget(items_box, stretch=2)

        # Portion overrides — only non-1.0 multipliers; "+ Add override" picks
        # an unused category and sets its multiplier. 1.0 is implicit.
        overrides_box = QGroupBox('Portion overrides')
        info = QLabel(
            'Each override scales matching ingredients of one category '
            'when this template is applied. 1.0 is the implicit default.'
        )
        info.setEnabled(False)
        info.setWordWrap(True)

        self.overrides_layout = QVBoxLayout()
        self.overrides_layout.setSpacing(2)

        self.add_override_btn = QPushButton('+ Add Override')
        self.add_override_btn.clicked.connect(self._on_add_override)
        ov_btn_row = QHBoxLayout()
        ov_btn_row.addWidget(self.add_override_btn)
        ov_btn_row.addStretch()

        overrides_outer = QVBoxLayout(overrides_box)
        overrides_outer.addWidget(info)
        overrides_outer.addLayout(self.overrides_layout)
        overrides_outer.addLayout(ov_btn_row)
        layout.addWidget(overrides_box, stretch=1)

        return wrap

    def _set_editor_enabled(self, enabled):
        '''Grey out the editor pane when no template is selected (e.g. after
        the last template was deleted). Avoids the visual lie of an editor
        whose fields don't bind to anything.'''
        self.name_edit.setEnabled(enabled)
        self.color_btn.setEnabled(enabled)
        self.shape_combo.setEnabled(enabled)
        self.items_table.setEnabled(enabled)
        self.add_override_btn.setEnabled(enabled)

    # --- selection / load ---

    def _on_tag_selected(self, current, _previous):
        if current is None:
            self.current_tag_id = None
            self._set_editor_enabled(False)
            self._refresh_items()
            self._refresh_overrides()
            self.silhouette.update_preview(None, None)
            return
        self.current_tag_id = current.data(Qt.UserRole)
        self._set_editor_enabled(True)
        # Re-read the tag rather than trusting the cached list item — the
        # name/color/shape may have been edited and saved through this same
        # dialog without a list rebuild yet.
        tag = self._current_tag()
        if not tag:
            return
        self.name_edit.blockSignals(True)
        self.name_edit.setText(tag['name'] or '')
        self.name_edit.blockSignals(False)
        _style_swatch(self.color_btn, tag.get('color'))

        self.shape_combo.blockSignals(True)
        idx = self.shape_combo.findData(tag.get('shape') or 'none')
        if idx >= 0:
            self.shape_combo.setCurrentIndex(idx)
        self.shape_combo.blockSignals(False)

        self.silhouette.update_preview(tag.get('shape'), tag.get('color'))

        self._refresh_items()
        self._refresh_overrides()

    def _current_tag(self):
        if not self.current_tag_id:
            return None
        for t in db.get_tags(kind='recipe'):
            if t['id'] == self.current_tag_id:
                return t
        return None

    # --- identity edits ---

    def _on_name_committed(self):
        if not self.current_tag_id:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            tag = self._current_tag()
            if tag:
                self.name_edit.blockSignals(True)
                self.name_edit.setText(tag['name'] or '')
                self.name_edit.blockSignals(False)
            return
        tag = self._current_tag()
        if tag and tag.get('name') == new_name:
            return
        db.update_tag(self.current_tag_id, name=new_name)
        self._refresh_list_item_in_place()

    def _on_pick_color(self):
        if not self.current_tag_id:
            return
        tag = self._current_tag()
        initial = QColor(tag.get('color') if tag else _DEFAULT_COLOR)
        if not initial.isValid():
            initial = QColor(_DEFAULT_COLOR)
        picked = QColorDialog.getColor(initial, self, 'Pick template color')
        if not picked.isValid():
            return
        db.update_tag(self.current_tag_id, color=picked.name())
        _style_swatch(self.color_btn, picked.name())
        self.silhouette.update_preview(
            self.shape_combo.currentData(), picked.name(),
        )
        self._refresh_list_item_in_place()

    def _on_shape_changed(self, _index):
        if not self.current_tag_id:
            return
        shape = self.shape_combo.currentData()
        db.update_tag(self.current_tag_id, shape=shape)
        tag = self._current_tag()
        self.silhouette.update_preview(shape, tag.get('color') if tag else None)

    # --- items ---

    def _refresh_items(self):
        self.items_table.blockSignals(True)
        try:
            self.items_table.setRowCount(0)
            if not self.current_tag_id:
                return
            rows = db.get_tag_components(self.current_tag_id)
            self.items_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                name_item = QTableWidgetItem(row['Name'] or '')
                name_item.setData(Qt.UserRole, row['id'])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)

                type_item = QTableWidgetItem(row['Type'] or '')
                if row['Type'] == 'ingredient':
                    cat = (
                        db.get_ingredient_tag(row['child_ingredient'])
                        if row['child_ingredient'] else None
                    )
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

    def _on_add_item(self):
        if not self.current_tag_id:
            return
        tag = self._current_tag()
        if not tag:
            return
        # ingredients_only: templates can only hold ingredients. Allowing a
        # sub-recipe creates a cycle as soon as a recipe in the template's
        # subtree is itself tagged with this template (the recursive CTE in
        # RecipesWithNutrition loops forever and the app hangs).
        dlg = RecipeComponentAddDialog(
            0, f"Template: {tag['name']}", parent=self, ingredients_only=True,
        )
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        child_id, mode, _name, _unit, *_ = dlg.selected
        existing = db.get_tag_components(self.current_tag_id)
        for row in existing:
            if mode == 'ingredient' and row['child_ingredient'] == child_id:
                QMessageBox.information(self, 'Already Added', 'This template already includes that item.')
                return
            if mode == 'recipe' and row['child_recipe'] == child_id:
                QMessageBox.information(self, 'Already Added', 'This template already includes that item.')
                return
        db.add_tag_component(self.current_tag_id, mode, child_id, dlg.qty)
        self._refresh_items()
        self._refresh_list_item_in_place()

    def _on_remove_item(self):
        r = self.items_table.currentRow()
        if r < 0:
            return
        name_item = self.items_table.item(r, 0)
        if name_item is None:
            return
        tag_component_id = name_item.data(Qt.UserRole)
        db.delete_tag_component(tag_component_id)
        self._refresh_items()
        self._refresh_list_item_in_place()

    # --- overrides ---

    def _refresh_overrides(self):
        # Tear down any existing rows; rebuild from db. Each row's widgets
        # capture the category id in their lambda closures so we don't need
        # to track them separately.
        _clear_layout(self.overrides_layout)
        if not self.current_tag_id:
            return
        active = [
            m for m in db.get_tag_category_multipliers(self.current_tag_id)
            if abs(m['multiplier'] - 1.0) > 1e-9
        ]
        if not active:
            empty = QLabel('No overrides — every category scales 1.0×.')
            empty.setEnabled(False)
            self.overrides_layout.addWidget(empty)
            return
        for m in active:
            self.overrides_layout.addLayout(self._build_override_row(m))

    def _build_override_row(self, m):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        chip = _CategoryChip(m['category_name'], m['category_color'])
        row.addWidget(chip)

        spin = QDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(2)
        spin.setValue(float(m['multiplier']))
        cat_id = m['category_tag_id']
        spin.valueChanged.connect(
            lambda value, c=cat_id: self._on_override_value_changed(c, value),
        )
        row.addWidget(spin)

        remove_btn = QToolButton()
        remove_btn.setText('×')
        remove_btn.setToolTip('Remove this override')
        remove_btn.clicked.connect(
            lambda _checked=False, c=cat_id: self._on_remove_override(c),
        )
        row.addWidget(remove_btn)
        row.addStretch()
        return row

    def _on_override_value_changed(self, category_tag_id, value):
        if not self.current_tag_id:
            return
        db.set_tag_category_multiplier(self.current_tag_id, category_tag_id, value)
        # If the user dragged the value back to 1.0, the DB row gets deleted
        # (see db.set_tag_category_multiplier) and we should drop the row
        # from the UI too. Rebuild rather than surgically remove — the row
        # count is small and the rebuild is cheap.
        if abs(value - 1.0) < 1e-9:
            self._refresh_overrides()
            self._refresh_list_item_in_place()

    def _on_remove_override(self, category_tag_id):
        # Setting multiplier back to 1.0 is how db represents "no override".
        db.set_tag_category_multiplier(self.current_tag_id, category_tag_id, 1.0)
        self._refresh_overrides()
        self._refresh_list_item_in_place()

    def _on_add_override(self):
        if not self.current_tag_id:
            return
        # Offer only categories that don't already have an override.
        all_cats = db.get_tag_category_multipliers(self.current_tag_id)
        available = [
            m for m in all_cats
            if abs(m['multiplier'] - 1.0) < 1e-9
        ]
        if not available:
            QMessageBox.information(
                self, 'No Categories Left',
                'Every ingredient category already has an override.',
            )
            return
        names = [m['category_name'] for m in available]
        choice, ok = QInputDialog.getItem(
            self, 'Add Override', 'Category:', names, 0, False,
        )
        if not ok or not choice:
            return
        chosen = next((m for m in available if m['category_name'] == choice), None)
        if not chosen:
            return
        value, ok = QInputDialog.getDouble(
            self, 'Multiplier', f'Scale {choice} by:',
            0.5, 0.0, 100.0, 2,
        )
        if not ok or abs(value - 1.0) < 1e-9:
            return  # 1.0 means "no override" — don't store
        db.set_tag_category_multiplier(self.current_tag_id, chosen['category_tag_id'], value)
        self._refresh_overrides()
        self._refresh_list_item_in_place()

    # --- new/delete template ---

    def _on_new(self):
        text, ok = QInputDialog.getText(self, 'New Template', 'Template name:', text='Template')
        if not ok or not text.strip():
            return
        new_id = db.create_tag(text.strip(), kind='recipe', color=_DEFAULT_COLOR)
        self.current_tag_id = new_id
        self._refresh_list()

    def _on_delete(self):
        if not self.current_tag_id:
            return
        tag = self._current_tag()
        if not tag:
            return
        used_by = db.query(
            'SELECT COUNT(*) AS c FROM recipe_tags_mapping WHERE tag_id=?;',
            (self.current_tag_id,), one=True,
        )['c']
        msg = f"Delete template '{tag['name']}'?"
        if used_by:
            msg += (
                f"\n\n{used_by} recipe{'' if used_by == 1 else 's'} currently "
                'use this template. Their format mapping will be cleared, '
                'but their existing items remain.'
            )
        if QMessageBox.question(
            self, 'Delete', msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        db.delete_tag(self.current_tag_id)
        self.current_tag_id = None
        self._refresh_list()
        if self.tag_list.count() == 0:
            self._set_editor_enabled(False)

    # --- list-item updates ---

    def _refresh_list_item_in_place(self):
        '''Re-render the currently-selected list item's swatch + subtitle
        without rebuilding the whole list. Used after edits that change the
        item-count / override-count / color / name in the subtitle.'''
        row = self.tag_list.currentRow()
        if row < 0:
            return
        tag = self._current_tag()
        if not tag:
            return
        self.tag_list.blockSignals(True)
        try:
            new_item = self._make_list_item(tag)
            # Replace in place. Swapping the QListWidgetItem requires removing
            # the old one and inserting a new one at the same index.
            self.tag_list.takeItem(row)
            self.tag_list.insertItem(row, new_item)
            self.tag_list.setCurrentRow(row)
        finally:
            self.tag_list.blockSignals(False)


# --- Backwards-compat: old name kept so importing callers don't break ---
# tags_manager.py used to instantiate TemplateEditorDialog for a single tag.
# The new manager is the entry point for everything, so callers should use
# TemplatesManagerDialog directly. The alias is left here only briefly so
# any stale import doesn't break the dialog; remove once all call sites
# are migrated.
TemplateEditorDialog = TemplatesManagerDialog


# ---------- module-level helpers ----------

class _CategoryChip(QLabel):
    '''Colored chip + category name. Used in the overrides list. Matches
    the style of the (now-removed) per-category multipliers form: a label
    with a colored left border so the chip + name read as one unit.'''

    def __init__(self, name, color):
        super().__init__(name)
        c = QColor(color or _DEFAULT_COLOR)
        if not c.isValid():
            c = QColor(_DEFAULT_COLOR)
        self.setStyleSheet(
            f'padding: 2px 8px; border-left: 6px solid {c.name()};'
            'background: transparent;'
        )
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)


def _divider():
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


def _swatch_pixmap(color_hex, size=14):
    '''Tiny solid-color square for the list-item decoration icon.'''
    pm = QPixmap(size, size)
    c = QColor(color_hex or _DEFAULT_COLOR)
    if not c.isValid():
        c = QColor(_DEFAULT_COLOR)
    pm.fill(c)
    return pm


def _style_swatch(btn, color_hex):
    '''Render the color-picker button as a flat solid-color rectangle.'''
    c = QColor(color_hex or _DEFAULT_COLOR)
    if not c.isValid():
        c = QColor(_DEFAULT_COLOR)
    btn.setStyleSheet(
        f'background-color: {c.name()}; border: 1px solid #888; border-radius: 4px;'
    )


def _clear_layout(layout):
    '''Remove every child widget / sublayout from `layout`. Recurses so
    nested rows (chip + spinbox + remove) are fully torn down between
    refreshes — without this, removing an override row leaves orphan
    widgets behind that grow each rebuild.'''
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            _clear_layout(sub)


def _fmt_qty(value):
    if value is None:
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:.4f}'.rstrip('0').rstrip('.')
