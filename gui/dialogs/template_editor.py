'''Formats & templates, per the Framework canvas: a Formats list (each
format's silhouette, shape, auto-add item count and how many recipes
use it) beside the selected format's editor — a large silhouette
preview, Name, Shape (one button per silhouette), Shape tint (the
palette swatches plus Custom…), an Auto-add items card and a Portion
rules card (utilities/portions.py: how the format sizes a category).

TemplatesEditor is the Configure page; TemplatesManagerDialog wraps it
for the New recipe dialog's "Edit template" link.

Writes are immediate — no Save button. Every item or rule change is
applied straight away to every recipe in the format
(db.apply_template_to_recipes), and a banner says what changed with an
Undo that puts the template and those recipes back. The banner gathers
the edits made to one format; it's dropped (the edits kept) when
another format is picked or the page is left.'''
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QDoubleValidator, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QScrollArea, QStyledItemDelegate, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.widgets import config_kit as kit
from utilities import portions
from utilities.wedge_renderer import render_recipe


_DEFAULT_COLOR = '#347200'

# (db value, label). Each must match a branch in
# utilities/wedge_renderer._paint_silhouette and _KNOWN_SHAPES.
_SHAPE_CHOICES = (
    ('none', 'None'),
    ('ring', 'Ring'),
    ('bowl', 'Bowl'),
    ('plate', 'Plate'),
    ('wrap', 'Wrap'),
    ('tray', 'Tray'),
    ('box', 'Box'),
    ('jar', 'Jar'),
    ('cone', 'Cone'),
)
_SHAPE_LABELS = dict(_SHAPE_CHOICES)

# Evergreens palette, per the canvas's Shape tint row.
_TINTS = (
    ('#347200', 'Romaine'),
    ('#ff8c00', 'Sweet Potato'),
    ('#d9b26a', 'Toasted gold'),
    ('#c9007a', 'Pickled Onion'),
    ('#bbca00', 'Avocado'),
    ('#ffa98b', 'Red Wine Vini'),
)

# Portion rule modes as the editor names them.
_MODE_LABELS = (('base', 'Shared base'), ('fixed', 'Each'))
_MEASURE_LABELS = {'cup': 'cup', 'f.oz': 'f.oz', 'tbsp': 'tbsp', 'tsp': 'tsp'}

_PREVIEW = 140
_LIST_ICON = 40
_SHAPE_ICON = 30


def _silhouette(shape, color, size):
    '''A silhouette pixmap (or a dashed circle for no shape).'''
    if shape and shape != 'none':
        png = render_recipe([], size=size, shape=shape, shape_color=color)
        image = QImage()
        if png and image.loadFromData(png) and not image.isNull():
            return QPixmap.fromImage(image)
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(kit.FIELD_BORDER), 1.2)
    pen.setDashPattern([3, 3])
    p.setPen(pen)
    m = max(2, size // 10)
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    p.end()
    return pix


class _QuantityDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setValidator(QDoubleValidator(0.0001, 100000.0, 4, editor))
        editor.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return editor


class TemplatesManagerDialog(QDialog):
    '''TemplatesEditor in a dialog, for the New recipe dialog's "Edit
    template" link (Configure › Formats & templates hosts it inline).'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Formats & templates')
        self.resize(1080, 700)
        self.editor = TemplatesEditor()
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.addWidget(self.editor, stretch=1)
        layout.addWidget(button_box)


class TemplatesEditor(QWidget):
    '''Formats list + the selected format's editor. Changes save as you
    make them; the host refreshes the Library afterwards.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tag_id = None
        # Edits to one format since the banner appeared: the template and
        # each changed recipe as they were before the first edit, plus the
        # format's costs then. None when there's nothing to undo.
        self._pending = None
        self.setObjectName('TemplatesEditor')
        self.setStyleSheet(f'QWidget#TemplatesEditor {{ background: {kit.BG}; }}')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_list_pane())
        layout.addWidget(self._build_editor_pane(), stretch=1)

        self._refresh_list()
        if self.tag_list.count() > 0:
            self.tag_list.setCurrentRow(0)
        else:
            self._set_editor_enabled(False)

    # --- formats list ----------------------------------------------------

    def _build_list_pane(self):
        wrap = QWidget()
        wrap.setObjectName('FormatsList')
        wrap.setFixedWidth(300)
        wrap.setStyleSheet(f'QWidget#FormatsList {{ border-right: 1px solid {kit.BORDER}; }}')
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)

        new_btn = kit.button('+ New format')
        new_btn.clicked.connect(self._on_new)
        head = QHBoxLayout()
        head.addWidget(kit.heading('Formats'))
        head.addStretch()
        head.addWidget(new_btn)

        self.tag_list = QListWidget()
        self.tag_list.setStyleSheet(kit.LIST_STYLE)
        self.tag_list.setIconSize(QSize(_LIST_ICON, _LIST_ICON))
        self.tag_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tag_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tag_list.currentItemChanged.connect(self._on_tag_selected)

        layout.addLayout(head)
        layout.addWidget(self.tag_list, stretch=1)
        return wrap

    def _refresh_list(self):
        '''Rebuild the list, keeping the current format selected.'''
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
        if self.tag_list.currentRow() < 0 and self.tag_list.count() > 0:
            self.tag_list.setCurrentRow(0)
            return
        cur = self.tag_list.currentItem()
        if cur is not None:
            self._on_tag_selected(cur, None)

    def _make_list_item(self, tag):
        items_count = len(db.get_tag_components(tag['id']))
        used_by = db.query('SELECT COUNT(*) AS c FROM recipe_tags_mapping WHERE tag_id=?;',
                           (tag['id'],), one=True)['c']
        shape = _SHAPE_LABELS.get(tag.get('shape') or 'none', 'None')
        sub = (f"{shape} · {items_count} auto-add item{'' if items_count == 1 else 's'}"
               f" · {used_by} recipe{'' if used_by == 1 else 's'}")
        item = QListWidgetItem(f"{tag['name']}\n{sub}")
        item.setData(Qt.UserRole, tag['id'])
        item.setIcon(QIcon(_silhouette(tag.get('shape'), tag.get('color'), _LIST_ICON)))
        return item

    # --- editor --------------------------------------------------------

    def _build_editor_pane(self):
        body = QWidget()
        body.setObjectName('FormatDetail')
        body.setStyleSheet(f'QWidget#FormatDetail {{ background: {kit.BG}; }}')
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(20)

        layout.addWidget(self._build_banner())

        # Preview + identity
        self.preview = QLabel()
        self.preview.setFixedSize(_PREVIEW, _PREVIEW)
        self.preview.setAlignment(Qt.AlignCenter)

        self.name_edit = kit.field(320)
        self.name_edit.editingFinished.connect(self._on_name_committed)

        self._shape_group = QButtonGroup(self)
        self._shape_group.setExclusive(True)
        shapes = QHBoxLayout()
        shapes.setSpacing(6)
        self._shape_buttons = {}
        for value, label in _SHAPE_CHOICES:
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setToolTip(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(52, 52)
            btn.setIconSize(QSize(_SHAPE_ICON, _SHAPE_ICON))
            btn.setStyleSheet(f'QToolButton {{ border: 1px solid {kit.BORDER}; border-radius: 8px; background: #ffffff; }}'
                              f' QToolButton:hover {{ border-color: {kit.FIELD_BORDER}; }}'
                              f' QToolButton:checked {{ border: 2px solid {kit.ROMAINE}; background: {kit.SELECTED}; }}')
            btn.clicked.connect(lambda _c=False, v=value: self._on_shape_picked(v))
            self._shape_group.addButton(btn)
            self._shape_buttons[value] = btn
            shapes.addWidget(btn)
        shapes.addStretch()

        tints = QHBoxLayout()
        tints.setSpacing(8)
        self._tint_buttons = {}
        for hex_, label in _TINTS:
            btn = QToolButton()
            btn.setToolTip(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(28, 28)
            btn.clicked.connect(lambda _c=False, h=hex_: self._set_color(h))
            self._tint_buttons[hex_] = btn
            tints.addWidget(btn)
        self.custom_tint = QToolButton()
        self.custom_tint.setText('Custom…')
        self.custom_tint.setCursor(Qt.PointingHandCursor)
        self.custom_tint.setToolTip('Pick any color')
        self.custom_tint.clicked.connect(self._on_pick_color)
        tints.addWidget(self.custom_tint)
        tints.addStretch()

        ident = QVBoxLayout()
        ident.setSpacing(14)
        for label, child in (('Name', self.name_edit), ('Shape', shapes), ('Shape tint', tints)):
            col = QVBoxLayout()
            col.setSpacing(6)
            col.addWidget(kit.eyebrow(label))
            if isinstance(child, QWidget):
                col.addWidget(child)
            else:
                col.addLayout(child)
            ident.addLayout(col)
        top = QHBoxLayout()
        top.setSpacing(24)
        top.addWidget(self.preview, alignment=Qt.AlignTop)
        top.addLayout(ident, stretch=1)
        layout.addLayout(top)

        # Auto-add items card
        items_card = QFrame()
        items_card.setObjectName('ItemsCard')
        items_card.setStyleSheet(f'QFrame#ItemsCard {{ background: #ffffff; border: 1px solid {kit.BORDER};'
                                 ' border-radius: 8px; }')
        ic = QVBoxLayout(items_card)
        ic.setContentsMargins(0, 0, 0, 0)
        ic.setSpacing(0)
        self.add_item_btn = kit.button('+ Add item')
        self.add_item_btn.clicked.connect(self._on_add_item)
        self.items_note = kit.note('')
        ih = QHBoxLayout()
        ih.setContentsMargins(16, 12, 16, 12)
        ih.setSpacing(12)
        ih.addWidget(kit.subheading('Auto-add items'))
        ih.addWidget(self.items_note, stretch=1)
        ih.addWidget(self.add_item_btn)
        head_wrap = QFrame()
        head_wrap.setObjectName('ItemsHead')
        head_wrap.setStyleSheet(f'QFrame#ItemsHead {{ border: 0; border-bottom: 1px solid {kit.BORDER}; }}')
        head_wrap.setLayout(ih)
        ic.addWidget(head_wrap)

        self.items_table = QTableWidget(0, 5)
        self.items_table.setHorizontalHeaderLabels(['Ingredient', 'Qty', 'Unit', 'Cost', ''])
        self.items_table.verticalHeader().setVisible(False)
        self.items_table.verticalHeader().setDefaultSectionSize(36)
        self.items_table.setShowGrid(False)
        self.items_table.setFrameShape(QFrame.NoFrame)
        self.items_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.items_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                         | QAbstractItemView.SelectedClicked)
        self.items_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.items_table.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; border: 0; color: {kit.KALE};
                selection-background-color: #fff1da; selection-color: {kit.KALE}; }}
            QTableWidget::item {{ border-top: 1px solid #f3ece0; padding: 0 8px; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.MUTED}; border: 0; padding: 8px;
                font-size: 11px; font-weight: 600; }}''')
        hh = self.items_table.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 70), (2, 70), (3, 80), (4, 40)):
            hh.setSectionResizeMode(col, QHeaderView.Fixed)
            self.items_table.setColumnWidth(col, width)
        self.items_table.setItemDelegateForColumn(1, _QuantityDelegate(self.items_table))
        self.items_table.itemChanged.connect(self._on_item_changed)
        ic.addWidget(self.items_table)
        self.items_empty = kit.note('No items yet')
        self.items_empty.setContentsMargins(16, 10, 16, 12)
        ic.addWidget(self.items_empty)
        layout.addWidget(items_card)

        # Portion rules card
        rules_card, rl = kit.card()
        rh = QHBoxLayout()
        rh.setSpacing(12)
        rh.addWidget(kit.subheading('Portion rules'))
        rh.addWidget(kit.note('Shared base: ingredients split one amount. Each: every ingredient gets it.'),
                     stretch=1)
        self.review_btn = kit.button('Check recipes…')
        self.review_btn.clicked.connect(self.open_review)
        rh.addWidget(self.review_btn, alignment=Qt.AlignTop)
        rl.addLayout(rh)
        self.rules_layout = QVBoxLayout()
        self.rules_layout.setSpacing(8)
        rl.addLayout(self.rules_layout)
        self.add_rule_btn = QPushButton('+ Category')
        self.add_rule_btn.setCursor(Qt.PointingHandCursor)
        self.add_rule_btn.setStyleSheet(
            f'QPushButton {{ min-height: 36px; padding: 0 12px; border: 1px dashed {kit.FIELD_BORDER};'
            f' border-radius: 8px; background: transparent; color: {kit.MUTED}; }}'
            ' QPushButton:hover { background: #f8f2e6; }')
        self.add_rule_btn.clicked.connect(lambda: self._on_add_rule(self.add_rule_btn))
        add_row = QHBoxLayout()
        add_row.addWidget(self.add_rule_btn)
        add_row.addStretch()
        rl.addLayout(add_row)
        layout.addWidget(rules_card)

        self.delete_btn = kit.button('Delete format…', danger=True)
        self.delete_btn.clicked.connect(self._on_delete)
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(self.delete_btn)
        layout.addStretch()
        layout.addLayout(foot)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; border: 0; }}')
        scroll.setWidget(body)
        self._body = body
        return scroll

    def _set_editor_enabled(self, enabled):
        self._body.setEnabled(enabled)

    # --- selection / load ---------------------------------------------------

    def _on_tag_selected(self, current, _previous):
        if current is None:
            self.current_tag_id = None
            self._set_editor_enabled(False)
            self._refresh_items()
            self._refresh_rules()
            self.preview.setPixmap(_silhouette(None, None, _PREVIEW))
            return
        if current.data(Qt.UserRole) != self.current_tag_id:
            self._drop_pending()
        self.current_tag_id = current.data(Qt.UserRole)
        self._set_editor_enabled(True)
        tag = self._current_tag()
        if not tag:
            return
        self.name_edit.blockSignals(True)
        self.name_edit.setText(tag['name'] or '')
        self.name_edit.blockSignals(False)
        self._sync_identity(tag)
        self._refresh_items()
        self._refresh_rules()

    def _sync_identity(self, tag):
        shape = tag.get('shape') or 'none'
        color = tag.get('color') or _DEFAULT_COLOR
        self.preview.setPixmap(_silhouette(shape, color, _PREVIEW))
        for value, btn in self._shape_buttons.items():
            btn.setIcon(QIcon(_silhouette(value, color, _SHAPE_ICON)))
            btn.setChecked(value == shape)
        for hex_, btn in self._tint_buttons.items():
            on = hex_.lower() == color.lower()
            btn.setStyleSheet(f'QToolButton {{ border-radius: 14px; background: {hex_};'
                              f' border: {"2px solid " + kit.KALE if on else "1px solid " + kit.BORDER}; }}')
        custom = color.lower() not in {h.lower() for h, _l in _TINTS}
        self.custom_tint.setStyleSheet(
            f'QToolButton {{ height: 26px; padding: 0 10px; border-radius: 13px; background: #ffffff;'
            f' color: {kit.KALE}; border: {"2px solid " + kit.KALE if custom else "1px solid " + kit.FIELD_BORDER};'
            f' {"border-left: 12px solid " + color + ";" if custom else ""} }}')

    def _current_tag(self):
        if not self.current_tag_id:
            return None
        return next((t for t in db.get_tags(kind='recipe') if t['id'] == self.current_tag_id), None)

    # --- identity edits -----------------------------------------------------

    def _on_name_committed(self):
        if not self.current_tag_id:
            return
        tag = self._current_tag()
        new_name = self.name_edit.text().strip()
        taken = {t['name'].lower() for t in db.get_tags(kind='recipe') if t['id'] != self.current_tag_id}
        if not new_name or new_name.lower() in taken:
            if new_name:
                QMessageBox.information(self, 'Format name', f'There is already a format called “{new_name}”.')
            self.name_edit.blockSignals(True)
            self.name_edit.setText(tag['name'] if tag else '')
            self.name_edit.blockSignals(False)
            return
        if tag and tag.get('name') == new_name:
            return
        db.update_tag(self.current_tag_id, name=new_name)
        self._refresh_list_item_in_place()
        self._sync_items_note()

    def _set_color(self, hex_):
        if not self.current_tag_id:
            return
        db.update_tag(self.current_tag_id, color=hex_)
        self._sync_identity(self._current_tag())
        self._refresh_list_item_in_place()

    def _on_pick_color(self):
        if not self.current_tag_id:
            return
        tag = self._current_tag()
        initial = QColor(tag.get('color') if tag else _DEFAULT_COLOR)
        if not initial.isValid():
            initial = QColor(_DEFAULT_COLOR)
        picked = QColorDialog.getColor(initial, self, 'Shape tint')
        if picked.isValid():
            self._set_color(picked.name())

    def _on_shape_picked(self, shape):
        if not self.current_tag_id:
            return
        db.update_tag(self.current_tag_id, shape=shape)
        self._sync_identity(self._current_tag())
        self._refresh_list_item_in_place()

    # --- items -------------------------------------------------------------

    def _sync_items_note(self):
        tag = self._current_tag()
        if not tag:
            self.items_note.setText('')
            return
        n = len(db.get_format_recipe_ids(tag['id']))
        self.items_note.setText(f'Added to {n} recipe{"" if n == 1 else "s"}')

    def _refresh_items(self):
        self._sync_items_note()
        self.items_table.blockSignals(True)
        try:
            self.items_table.setRowCount(0)
            rows = db.get_tag_components(self.current_tag_id) if self.current_tag_id else []
            self.items_table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                cat = db.get_ingredient_tag(row['child_ingredient']) if row['child_ingredient'] else None
                name_item = QTableWidgetItem(row['Name'] or '')
                name_item.setData(Qt.UserRole, row['id'])
                name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
                name_item.setIcon(QIcon(_dot((cat or {}).get('color') or '#a7ad9c')))
                if cat:
                    name_item.setToolTip(cat['name'])
                qty_item = QTableWidgetItem(_fmt_qty(row['quantity']))
                qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                qty_item.setToolTip('Double-click to change')
                unit_item = QTableWidgetItem(row.get('Unit') or '')
                unit_item.setFlags(unit_item.flags() & ~Qt.ItemIsEditable)
                unit_item.setForeground(QColor(kit.MUTED))
                cost = float(row.get('UnitCost') or 0) * float(row.get('quantity') or 0)
                cost_item = QTableWidgetItem(f'${cost:.2f}')
                cost_item.setFlags(cost_item.flags() & ~Qt.ItemIsEditable)
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                for c, it in enumerate((name_item, qty_item, unit_item, cost_item)):
                    self.items_table.setItem(r, c, it)
                remove = QToolButton()
                remove.setText('×')
                remove.setToolTip(f'Remove {row["Name"]}')
                remove.setCursor(Qt.PointingHandCursor)
                remove.setStyleSheet(f'QToolButton {{ border: 0; background: transparent; color: {kit.MUTED};'
                                     ' font-size: 15px; } QToolButton:hover { color: #8a4a00; }')
                remove.clicked.connect(lambda _c=False, tid=row['id']: self._remove_item(tid))
                self.items_table.setCellWidget(r, 4, remove)
        finally:
            self.items_table.blockSignals(False)
        n = self.items_table.rowCount()
        self.items_table.setFixedHeight(self.items_table.horizontalHeader().height() + 36 * n + 2 if n else 0)
        self.items_table.setVisible(bool(n))
        self.items_empty.setVisible(not n and self.current_tag_id is not None)

    def _on_item_changed(self, item):
        if item.column() != 1:
            return
        name_item = self.items_table.item(item.row(), 0)
        if name_item is None:
            return
        try:
            qty = float(item.text())
        except (TypeError, ValueError):
            qty = 0
        component_id = name_item.data(Qt.UserRole)
        current = next((r['quantity'] for r in db.get_tag_components(self.current_tag_id)
                        if r['id'] == component_id), None)
        if qty <= 0 or (current is not None and abs(float(current) - qty) < 1e-9):
            self._refresh_items()
            return
        self._template_write(lambda: db.update_tag_component_quantity(component_id, qty))
        self._refresh_items()

    def _on_add_item(self):
        tag = self._current_tag()
        if not tag:
            return
        # Ingredients only: a sub-recipe in a template creates a cycle as
        # soon as a recipe in its subtree is tagged with this format.
        dlg = RecipeComponentAddDialog(0, f"Format: {tag['name']}", parent=self, ingredients_only=True)
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        child_id, mode, _name, _unit, *_ = dlg.selected
        for row in db.get_tag_components(self.current_tag_id):
            if (mode == 'ingredient' and row['child_ingredient'] == child_id) or \
                    (mode == 'recipe' and row['child_recipe'] == child_id):
                QMessageBox.information(self, 'Already added', 'This format already includes that item.')
                return
        tag_id = self.current_tag_id
        self._template_write(lambda: db.add_tag_component(tag_id, mode, child_id, dlg.qty))
        self._refresh_items()
        self._refresh_list_item_in_place()

    def _remove_item(self, tag_component_id):
        self._template_write(lambda: db.delete_tag_component(tag_component_id))
        self._refresh_items()
        self._refresh_list_item_in_place()

    # --- portion rules --------------------------------------------------------

    def _refresh_rules(self):
        _clear_layout(self.rules_layout)
        rules = db.get_portion_rules(self.current_tag_id) if self.current_tag_id else []
        for rule in rules:
            self.rules_layout.addWidget(self._rule_row(rule))
        if not rules and self.current_tag_id:
            empty = kit.note('No rules')
            self.rules_layout.addWidget(empty)
        self.add_rule_btn.setVisible(self.current_tag_id is not None)

    def _rule_row(self, rule):
        row = QFrame()
        row.setObjectName('RuleRow')
        row.setStyleSheet(f'QFrame#RuleRow {{ border: 1px solid {kit.BORDER}; border-radius: 8px;'
                          ' background: #ffffff; }')
        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 6, 6, 6)
        hl.setSpacing(10)
        dot = QLabel()
        dot.setPixmap(_dot(rule['category_color'] or '#a7ad9c'))
        name = QLabel(rule['category_name'])
        name.setStyleSheet(f'color: {kit.KALE}; font-weight: 600;')
        name.setFixedWidth(110)
        combo_css = (f'QComboBox {{ min-height: 28px; border: 1px solid {kit.FIELD_BORDER}; border-radius: 4px;'
                     f' padding: 0 8px; color: {kit.KALE}; background: #ffffff; }}')
        mode = QComboBox()
        for value, label in _MODE_LABELS:
            mode.addItem(label, value)
        mode.setCurrentIndex(max(0, mode.findData(rule['mode'])))
        mode.setStyleSheet(combo_css)
        amount = QLineEdit(_fmt_qty(rule['amount']))
        amount.setFixedWidth(64)
        amount.setAlignment(Qt.AlignRight)
        amount.setValidator(QDoubleValidator(0.0001, 10000.0, 4, amount))
        amount.setStyleSheet(f'QLineEdit {{ min-height: 28px; border: 1px solid {kit.FIELD_BORDER};'
                             f' border-radius: 4px; padding: 0 6px; color: {kit.KALE}; background: #ffffff; }}')
        measure = QComboBox()
        for value in portions.RULE_MEASURES:
            measure.addItem(_MEASURE_LABELS.get(value, value), value)
        measure.setCurrentIndex(max(0, measure.findData(rule['measure'])))
        measure.setStyleSheet(combo_css)
        summary = kit.note(portions.describe_rule(rule['category_name'], rule['mode'], rule['amount'], rule['measure']))
        remove = QToolButton()
        remove.setText('×')
        remove.setToolTip(f'Size {rule["category_name"]} by hand in this format')
        remove.setCursor(Qt.PointingHandCursor)
        remove.setStyleSheet(f'QToolButton {{ border: 0; background: transparent; color: {kit.MUTED};'
                             ' font-size: 15px; } QToolButton:hover { color: #8a4a00; }')
        cat_id = rule['category_tag_id']

        def commit(*_args):
            self._on_rule_edited(cat_id, mode.currentData(), amount.text(), measure.currentData())

        mode.activated.connect(commit)
        measure.activated.connect(commit)
        amount.editingFinished.connect(commit)
        remove.clicked.connect(lambda _c=False: self._remove_rule(cat_id))
        for w in (dot, name, mode, amount, measure):
            hl.addWidget(w)
        hl.addWidget(summary, stretch=1)
        hl.addWidget(remove)
        return row

    def _on_rule_edited(self, category_tag_id, mode, amount_text, measure):
        if not self.current_tag_id:
            return
        try:
            amount = float(amount_text)
        except (TypeError, ValueError):
            amount = 0
        current = next((r for r in db.get_portion_rules(self.current_tag_id)
                        if r['category_tag_id'] == category_tag_id), None)
        if amount <= 0:
            self._refresh_rules()
            return
        if current and (current['mode'], current['measure']) == (mode, measure) \
                and abs(float(current['amount']) - amount) < 1e-9:
            return
        tag_id = self.current_tag_id
        self._template_write(lambda: db.set_portion_rule(tag_id, category_tag_id, mode, amount, measure))
        self._refresh_rules()

    def _remove_rule(self, category_tag_id):
        tag_id = self.current_tag_id
        self._template_write(lambda: db.delete_portion_rule(tag_id, category_tag_id))
        self._refresh_rules()

    def _on_add_rule(self, anchor):
        if not self.current_tag_id:
            return
        taken = {r['category_tag_id'] for r in db.get_portion_rules(self.current_tag_id)}
        available = [t for t in db.get_tags(kind='ingredient') if t['id'] not in taken]
        if not available:
            QMessageBox.information(self, 'No categories left', 'Every ingredient category already has a rule.')
            return
        menu = QMenu(self)
        for t in available:
            menu.addAction(QIcon(_dot(t.get('color') or '#a7ad9c')), t['name'],
                           lambda t=t: self.add_rule(t['id']))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def add_rule(self, category_tag_id, mode='base', amount=1.0, measure='cup'):
        tag_id = self.current_tag_id
        self._template_write(lambda: db.set_portion_rule(tag_id, category_tag_id, mode, amount, measure))
        self._refresh_rules()

    # --- applying template edits to recipes ---------------------------------

    def _build_banner(self):
        self.banner = QFrame()
        self.banner.setObjectName('ApplyBanner')
        self.banner.setStyleSheet(f'QFrame#ApplyBanner {{ background: {kit.SELECTED}; border: 1px solid #f0d9b5;'
                                  ' border-radius: 8px; }')
        hl = QHBoxLayout(self.banner)
        hl.setContentsMargins(14, 8, 8, 8)
        hl.setSpacing(10)
        self.banner_text = QLabel('')
        self.banner_text.setWordWrap(True)
        self.banner_text.setStyleSheet(f'color: {kit.KALE};')
        self.banner_undo = kit.button('Undo')
        self.banner_undo.clicked.connect(self.undo_pending)
        self.banner_review = kit.button('Review…')
        self.banner_review.setToolTip('Bring hand-sized recipes onto the rules')
        self.banner_review.clicked.connect(self.open_review)
        close = QToolButton()
        close.setText('×')
        close.setToolTip('Keep these changes')
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(f'QToolButton {{ border: 0; background: transparent; color: {kit.MUTED};'
                            ' font-size: 15px; }')
        close.clicked.connect(self._drop_pending)
        hl.addWidget(self.banner_text, stretch=1)
        hl.addWidget(self.banner_review)
        hl.addWidget(self.banner_undo)
        hl.addWidget(close)
        self.banner.hide()
        return self.banner

    def _template_write(self, write):
        '''Run one template edit, apply it to every recipe in the format
        and update the banner.'''
        tag_id = self.current_tag_id
        if not tag_id:
            return
        if self._pending is None or self._pending['tag_id'] != tag_id:
            self._pending = {'tag_id': tag_id, 'template': db.snapshot_template(tag_id),
                             'recipes': {}, 'costs': db.get_format_costs(tag_id)}
        write()
        for rid, rows in db.apply_template_to_recipes(tag_id).items():
            self._pending['recipes'].setdefault(rid, rows)
        self._show_banner()
        self._refresh_list_item_in_place()

    def _show_banner(self):
        pending = self._pending
        if pending is None:
            self.banner.hide()
            return
        tag = next((t for t in db.get_tags(kind='recipe') if t['id'] == pending['tag_id']), None)
        fmt = tag['name'] if tag else 'this format'
        n = len(pending['recipes'])
        if not n:
            text = f'Saved. No {fmt} recipe needed to change.'
        else:
            before, after = pending['costs'], db.get_format_costs(pending['tag_id'])
            ids = [rid for rid in after if rid in before]
            text = f'Updated {n} {fmt} recipe{"" if n == 1 else "s"}'
            if ids:
                b = sum(before[i] for i in ids) / len(ids)
                a = sum(after[i] for i in ids) / len(ids)
                text += f' · average cost ${b:.2f} → ${a:.2f}'
            text += '.'
        hand = db.count_hand_sized_recipes(pending['tag_id'])
        self.banner_review.setVisible(bool(hand))
        if hand:
            text += (f' {hand} recipe{" has" if hand == 1 else "s have"} hand-sized portions in a ruled'
                     ' category, which rules don’t change.')
        self.banner_text.setText(text)
        self.banner_undo.setToolTip(f'Put the {fmt} template and its recipes back as they were')
        self.banner.show()

    def open_review(self):
        '''The "Check recipes against portion rules" review. Recipes it
        changes aren't part of the banner's Undo, so the banner goes.'''
        from gui.dialogs.portion_review import PortionReviewDialog
        self._drop_pending()
        dlg = PortionReviewDialog(parent=self)
        dlg.exec()
        if dlg.changed:
            self._refresh_items()
            self._refresh_list_item_in_place()

    def undo_pending(self):
        '''Put the template and every recipe the pending edits changed
        back as they were.'''
        pending = self._pending
        if pending is None:
            return
        db.restore_template(pending['tag_id'], pending['template'])
        for rid, rows in pending['recipes'].items():
            db.restore_recipe_connections(rid, rows)
        self._pending = None
        self.banner.hide()
        self._refresh_items()
        self._refresh_rules()
        self._refresh_list_item_in_place()

    def _drop_pending(self):
        self._pending = None
        self.banner.hide()

    def hideEvent(self, event):
        # Leaving the page keeps the edits; recipes may be edited next, so
        # an Undo from here could overwrite them.
        self._drop_pending()
        super().hideEvent(event)

    # --- new / delete -----------------------------------------------------

    def _on_new(self, name=None):
        if name is None:
            name, ok = QInputDialog.getText(self, 'New format', 'Format name:')
            if not ok or not name.strip():
                return
        name = name.strip()
        if name.lower() in {t['name'].lower() for t in db.get_tags(kind='recipe')}:
            QMessageBox.information(self, 'New format', f'There is already a format called “{name}”.')
            return
        new_id = db.create_tag(name, kind='recipe', color=_DEFAULT_COLOR)
        self.current_tag_id = new_id
        self._refresh_list()
        return new_id

    def _on_delete(self, confirm=True):
        tag = self._current_tag()
        if not tag:
            return
        used_by = db.query('SELECT COUNT(*) AS c FROM recipe_tags_mapping WHERE tag_id=?;',
                           (self.current_tag_id,), one=True)['c']
        msg = f'Delete the format “{tag["name"]}”?'
        if used_by:
            msg += (f' {used_by} recipe{"" if used_by == 1 else "s"} use it: they become sub-recipes'
                    ' (no format) and keep their items.')
        if confirm and QMessageBox.question(self, 'Delete format', msg, QMessageBox.Yes | QMessageBox.No,
                                            QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_tag(self.current_tag_id)
        self.current_tag_id = None
        self._refresh_list()
        if self.tag_list.count() == 0:
            self._set_editor_enabled(False)

    def _refresh_list_item_in_place(self):
        '''Re-render the selected row (icon, name, counts) without
        rebuilding the list.'''
        row = self.tag_list.currentRow()
        tag = self._current_tag()
        if row < 0 or not tag:
            return
        fresh = self._make_list_item(tag)
        item = self.tag_list.item(row)
        self.tag_list.blockSignals(True)
        item.setText(fresh.text())
        item.setIcon(fresh.icon())
        self.tag_list.blockSignals(False)


# ---------- module-level helpers ----------

def _dot(color_hex, size=8):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QColor(color_hex or _DEFAULT_COLOR)
    p.setBrush(c if c.isValid() else QColor(_DEFAULT_COLOR))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return pm


def _clear_layout(layout):
    '''Remove every child widget / sublayout from `layout`.'''
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
