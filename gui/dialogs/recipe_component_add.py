'''Pick an ingredient or sub-recipe to add as a component.

Laid out per the Framework canvas's Add component dialog: a search
field with a match count, an All / Ingredients / Sub-recipes switch, a
list where each row shows its category pill (or a Sub-recipe pill),
its name and its per-unit cost and calories, and a footer with the
quantity and a live preview of what the addition does to the recipe —
cost and calories per serving, any new allergens, the new total and
food cost.

Keyboard: type to filter, ↑/↓ move through the list without leaving
the search field, Enter adds. Components already in the recipe stay
listed but disabled ("Already in recipe · 1.5 oz").

Two modes:
- `on_add(child_id, mode, qty, name)` given (the recipe editor): each
  Add calls it. With "Keep open to add another" checked the dialog
  stays up for the next pick; Done closes it.
- No callback (the templates manager): Add accepts the dialog and the
  caller reads `selected` and `qty`, as before.
'''
from PySide6.QtCore import QRectF, QSettings, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QStyle,
    QStyledItemDelegate, QVBoxLayout, QWidget,
)

import config
import db
from gui.widgets.wedge_view import WedgeView
from utilities import fuzzy
from gui.widgets.text_fit import elide, text_width


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_SELECTED_BG = '#fff1da'
_BG = '#fffaf2'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"
# Neutral fallback if an ingredient's tag color is missing.
_DEFAULT_TAG_COLOR = '#94a3b8'

_ROW_ROLE = Qt.UserRole          # (id, mode, name, unit, tag, color, cost, kcal)
_EXISTING_ROLE = Qt.UserRole + 1  # qty already in the recipe, or None


def _tint(hex_color, amount=0.22):
    '''Mix a category color toward white for its pill background.'''
    c = QColor(hex_color or _DEFAULT_TAG_COLOR)
    r = int(255 - (255 - c.red()) * amount)
    g = int(255 - (255 - c.green()) * amount)
    b = int(255 - (255 - c.blue()) * amount)
    return QColor(r, g, b)


def _fmt_qty(q):
    return '{:.2f}'.format(float(q)).rstrip('0').rstrip('.')


def _number(v):
    '''A float, or None for a missing or non-numeric value (a stray ''
    would otherwise stop the row painting halfway, leaving it blank).'''
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class _MatchDelegate(QStyledItemDelegate):
    '''[pill] name ............ $0.04 / oz · 37 kcal'''

    ROW_HEIGHT = 40
    PAD_X = 10

    def paint(self, painter, option, index):
        row = index.data(_ROW_ROLE)
        if not row:
            super().paint(painter, option, index)
            return
        _id, mode, name, unit, tag_name, tag_color, cost, kcal = row
        existing = index.data(_EXISTING_ROLE)
        rect = option.rect.adjusted(2, 2, -2, -2)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        selected = bool(option.state & QStyle.State_Selected) and existing is None
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(_SELECTED_BG))
            painter.drawRoundedRect(QRectF(rect), 8, 8)
            painter.fillRect(rect.x(), rect.y() + 2, 3, rect.height() - 4, QColor(_ROMAINE))

        base = QFont(option.font)
        small = QFont(option.font)
        small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.85))
        x = rect.x() + self.PAD_X
        cy = rect.center().y()

        # Pill.
        painter.setFont(small)
        if mode == 'recipe':
            text = 'Sub-recipe'
            w = text_width(small, text) + 18
            pill = QRectF(x, cy - 10, w, 20)
            painter.setPen(QColor(_ROMAINE))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(pill, 10, 10)
            painter.drawText(pill, Qt.AlignCenter, text)
        else:
            text = tag_name or 'Uncategorized'
            w = text_width(small, text) + 30
            pill = QRectF(x, cy - 10, w, 20)
            painter.setPen(Qt.NoPen)
            painter.setBrush(_tint(tag_color))
            painter.drawRoundedRect(pill, 10, 10)
            painter.setBrush(QColor(tag_color or _DEFAULT_TAG_COLOR))
            painter.drawEllipse(QRectF(x + 8, cy - 4, 8, 8))
            painter.setPen(QColor(_KALE))
            painter.drawText(pill.adjusted(20, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        x = int(pill.right()) + 10

        # Right-hand meta.
        if existing is not None:
            meta = f'Already in recipe · {_fmt_qty(existing)} {unit or ""}'.rstrip()
        else:
            parts = []
            cost, kcal = _number(cost), _number(kcal)
            if cost is not None:
                parts.append(f'${cost:.2f} / {unit or "unit"}')
            if kcal is not None:
                parts.append(f'{kcal:,.0f} kcal')
            meta = ' · '.join(parts)
        painter.setFont(small)
        meta_w = painter.fontMetrics().horizontalAdvance(meta)
        painter.setPen(QColor(_MUTED))
        painter.drawText(rect.right() - self.PAD_X - meta_w, rect.y(), meta_w, rect.height(),
                         Qt.AlignVCenter | Qt.AlignRight, meta)

        # Name.
        if selected:
            base.setWeight(QFont.DemiBold)
        painter.setFont(base)
        painter.setPen(QColor(_MUTED if existing is not None else _KALE))
        name_w = rect.right() - self.PAD_X - meta_w - 12 - x
        elided = elide(painter.font(), name, max(0, name_w))
        painter.drawText(x, rect.y(), name_w, rect.height(), Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(option.rect.width() or 400, self.ROW_HEIGHT)


class _SearchField(QLineEdit):
    '''Forwards ↑/↓/PgUp/PgDn to the list so focus can stay here.'''

    navigate = Signal(int)

    def keyPressEvent(self, event):
        step = {Qt.Key_Up: -1, Qt.Key_Down: 1, Qt.Key_PageUp: -8, Qt.Key_PageDown: 8}.get(event.key())
        if step is not None:
            self.navigate.emit(step)
            return
        super().keyPressEvent(event)


class RecipeComponentAddDialog(QDialog):
    def __init__(self, recipe_id, recipe_name, parent=None, ingredients_only=False, on_add=None,
                 exclude_recipes=()):
        '''`ingredients_only=True` hides sub-recipe rows from the picker;
        `exclude_recipes` hides just those recipes (a format's template
        can't hold one that is the format or contains one).'''
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Add to {recipe_name}')
        self.resize(620, 700)

        self.recipe_id = recipe_id
        self._ingredients_only = ingredients_only
        self._exclude_recipes = set(exclude_recipes or ())
        self._on_add = on_add
        self._kind = 'all'
        # `selected` and `qty` are populated on Add when there's no callback.
        self.selected = None  # tuple (id, mode, name, unit, tag, color, cost, kcal)
        self.qty = None
        self._allergen_maps = db.get_component_allergen_maps()

        self.setStyleSheet(f'QDialog {{ background: #ffffff; }} QLabel {{ color: {_KALE}; }}')

        # --- header ---
        title = QLabel(f'Add to {recipe_name}')
        title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')
        header = QHBoxLayout()
        header.setContentsMargins(20, 16, 20, 8)
        header.setSpacing(10)
        if recipe_id:
            header.addWidget(WedgeView(recipe_id, size=32))
        header.addWidget(title)
        header.addStretch()

        # --- search + kind switch ---
        self.filter_edit = _SearchField()
        self.filter_edit.setPlaceholderText('Find an ingredient or sub-recipe')
        self.filter_edit.setFrame(False)
        self.filter_edit.setStyleSheet(f'border: 0; background: transparent; color: {_KALE};'
                                       ' font-size: 15px;')
        self.filter_edit.textChanged.connect(self._apply_filter)
        self.filter_edit.navigate.connect(self._move)
        self.filter_edit.returnPressed.connect(self._on_add_clicked)
        self.match_label = QLabel('')
        self.match_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        search_box = QFrame()
        search_box.setObjectName('SearchBox')
        search_box.setStyleSheet(f'QFrame#SearchBox {{ border: 2px solid {_ROMAINE};'
                                 ' border-radius: 4px; background: #ffffff; }')
        sb = QHBoxLayout(search_box)
        sb.setContentsMargins(10, 4, 10, 4)
        glass = QLabel('⌕')
        glass.setStyleSheet(f'color: {_MUTED}; font-size: 16px;')
        sb.addWidget(glass)
        sb.addWidget(self.filter_edit, stretch=1)
        sb.addWidget(self.match_label)

        kind_row = QHBoxLayout()
        kind_row.setSpacing(8)
        self._kind_group = QButtonGroup(self)
        kinds = QFrame()
        kinds.setObjectName('Kinds')
        kinds.setStyleSheet(f'''
            QFrame#Kinds {{ border: 1px solid {_FIELD_BORDER}; border-radius: 8px; }}
            QFrame#Kinds QPushButton {{ border: 0; padding: 0 12px; min-height: 28px;
                background: #ffffff; color: {_KALE}; }}
            QFrame#Kinds QPushButton:checked {{ background: {_ROMAINE}; color: #ffffff;
                font-weight: 600; }}
        ''')
        kl = QHBoxLayout(kinds)
        kl.setContentsMargins(1, 1, 1, 1)
        kl.setSpacing(0)
        for key, label in (('all', 'All'), ('ingredient', 'Ingredients'), ('recipe', 'Sub-recipes')):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == 'all')
            btn.setAutoDefault(False)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _c=False, k=key: self._set_kind(k))
            self._kind_group.addButton(btn)
            kl.addWidget(btn)
        kinds.setVisible(not ingredients_only)
        hint = QLabel('↑↓ to move · Enter to add')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        kind_row.addWidget(kinds)
        kind_row.addStretch()
        kind_row.addWidget(hint)

        top = QVBoxLayout()
        top.setContentsMargins(20, 0, 20, 12)
        top.setSpacing(10)
        top.addWidget(search_box)
        top.addLayout(kind_row)

        # --- list ---
        self.results = QListWidget()
        self.results.setItemDelegate(_MatchDelegate(self.results))
        self.results.setFrameShape(QFrame.NoFrame)
        self.results.setFocusPolicy(Qt.NoFocus)
        self.results.setStyleSheet(f'QListWidget {{ background: #ffffff; border: 0;'
                                   f' border-top: 1px solid {_BORDER}; padding: 4px 12px; }}')
        self.results.currentItemChanged.connect(self._on_selection_changed)
        self.results.itemDoubleClicked.connect(lambda _i: self._on_add_clicked())

        self.create_link = QLabel('')
        self.create_link.setTextFormat(Qt.RichText)
        self.create_link.setStyleSheet(f'color: {_MUTED}; font-size: 13px; padding: 8px 22px;'
                                       f' border-bottom: 1px solid {_BORDER};')
        self.create_link.linkActivated.connect(lambda _h: self._create_ingredient())
        # Creating ingredients only makes sense when adding to a recipe.
        self._can_create = on_add is not None

        # --- footer ---
        self.qty_edit = QLineEdit('1')
        self.qty_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.qty_edit.setAlignment(Qt.AlignRight)
        self.qty_edit.setFixedWidth(72)
        self.qty_edit.setStyleSheet(f'QLineEdit {{ height: 32px; padding: 0 8px; border: 1px solid'
                                    f' {_FIELD_BORDER}; border-radius: 4px; background: #ffffff; }}')
        self.qty_edit.textChanged.connect(self._update_preview)
        self.qty_edit.returnPressed.connect(self._on_add_clicked)
        self.unit_label = QLabel('')
        self.unit_label.setStyleSheet(f'color: {_MUTED};')
        qty_label = QLabel('QUANTITY')
        qty_label.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600;'
                                ' letter-spacing: 1px;')
        qty_row = QHBoxLayout()
        qty_row.setSpacing(8)
        qty_row.addWidget(self.qty_edit)
        qty_row.addWidget(self.unit_label)
        qty_col = QVBoxLayout()
        qty_col.setSpacing(4)
        qty_col.addWidget(qty_label)
        qty_col.addLayout(qty_row)

        self.preview = QLabel('')
        self.preview.setTextFormat(Qt.RichText)
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(f'color: {_KALE}; font-size: 13px;')
        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)
        preview_row.addLayout(qty_col)
        preview_row.addWidget(self.preview, stretch=1, alignment=Qt.AlignBottom)

        self.keep_open = QCheckBox('Keep open to add another')
        self.keep_open.setChecked(QSettings().value('addComponent/keepOpen', True, type=bool))
        self.keep_open.toggled.connect(lambda v: QSettings().setValue('addComponent/keepOpen', v))
        self.keep_open.setVisible(on_add is not None)
        done_btn = QPushButton('Done' if on_add is not None else 'Cancel')
        done_btn.setAutoDefault(False)
        done_btn.setStyleSheet(f'QPushButton {{ height: 34px; padding: 0 14px; border: 1px solid'
                               f' {_FIELD_BORDER}; border-radius: 8px; background: #ffffff;'
                               f' color: {_KALE}; }}')
        done_btn.clicked.connect(self.reject)
        self.add_btn = QPushButton('Add   Enter')
        self.add_btn.setAutoDefault(False)
        self.add_btn.setStyleSheet(f'QPushButton {{ height: 34px; padding: 0 16px; border: 0;'
                                   f' border-radius: 8px; background: {_ROMAINE}; color: #ffffff;'
                                   ' font-weight: 600; } QPushButton:disabled { background: #c9d1bf; }')
        self.add_btn.clicked.connect(self._on_add_clicked)
        button_row = QHBoxLayout()
        button_row.addWidget(self.keep_open)
        button_row.addStretch()
        button_row.addWidget(done_btn)
        button_row.addWidget(self.add_btn)

        footer = QWidget()
        footer.setObjectName('AddFooter')
        footer.setAttribute(Qt.WA_StyledBackground, True)
        footer.setStyleSheet(f'QWidget#AddFooter {{ background: {_BG}; }}')
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(20, 14, 20, 14)
        fl.setSpacing(12)
        fl.addLayout(preview_row)
        fl.addLayout(button_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addLayout(top)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(self.create_link)
        layout.addWidget(footer)

        # Ctrl+S stays a synonym for Add, as in the previous picker.
        QShortcut(QKeySequence.Save, self, activated=self._on_add_clicked)
        if self._can_create:
            QShortcut(QKeySequence('Ctrl+Shift+N'), self, activated=self._create_ingredient)

        self._load()
        self.filter_edit.setFocus()

    # --- data ----------------------------------------------------------

    def _load(self, select_key=None):
        '''(Re)build the list from the DB: eligible components, what's
        already in the recipe, and the recipe's current totals.'''
        eligible = db.get_eligible_ingredients(self.recipe_id)
        if self._ingredients_only:
            eligible = [row for row in eligible if row[1] != 'recipe']
        elif self._exclude_recipes:
            eligible = [row for row in eligible if not (row[1] == 'recipe' and row[0] in self._exclude_recipes)]
        # Like the Ingredients gallery: ingredients by category order, then
        # name (uncategorized last); sub-recipes after them, by name.
        cat_order = {t['name']: i for i, t in enumerate(db.get_tags('ingredient'))}
        eligible = sorted(eligible, key=lambda row: (
            row[1] == 'recipe',
            0 if row[1] == 'recipe' else cat_order.get(row[4], len(cat_order)),
            (row[2] or '').casefold()))
        self._existing = {}
        self._recipe = None
        self._recipe_allergens = set()
        if self.recipe_id:
            for r in db.query('SELECT ChildIngredient, ChildRecipe, Quantity FROM Connections'
                              ' WHERE ParentRecipe = ?', (self.recipe_id,))['data']:
                key = ('recipe', r['ChildRecipe']) if r['ChildRecipe'] else ('ingredient', r['ChildIngredient'])
                self._existing[key] = r['Quantity']
            self._recipe = db.recipe_info(self.recipe_id)
            self._recipe_allergens = set(db.get_recipe_allergens(self.recipe_id))

        self.results.clear()
        for row in eligible:
            child_id, mode, name, unit, tag_name = row[:5]
            item = QListWidgetItem()
            # Item text is the filter target: name, unit, and the pill's
            # visible word (category, or "sub-recipe").
            item.setText(' '.join(filter(None, [name, unit, 'sub-recipe' if mode == 'recipe' else tag_name])))
            item.setData(_ROW_ROLE, tuple(row))
            existing = self._existing.get((mode, child_id))
            item.setData(_EXISTING_ROLE, existing)
            if existing is not None:
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled)
            self.results.addItem(item)
        self._apply_filter()
        if select_key is not None:
            for i in range(self.results.count()):
                row = self.results.item(i).data(_ROW_ROLE)
                if (row[1], row[0]) == select_key:
                    self.results.setCurrentRow(i)
                    break

    # --- filtering + navigation ----------------------------------------

    def _set_kind(self, kind):
        self._kind = kind
        self._apply_filter()

    def _apply_filter(self, *_):
        needle = self.filter_edit.text().strip()
        shown = 0
        best = None
        for i in range(self.results.count()):
            item = self.results.item(i)
            mode = item.data(_ROW_ROLE)[1]
            score = fuzzy.score(needle, item.text()) if needle else 0
            hide = score is None or (self._kind != 'all' and mode != self._kind)
            item.setHidden(hide)
            shown += not hide
            if not hide and needle and item.flags() & Qt.ItemIsEnabled and (best is None or score < best[0]):
                best = (score, i)
        self.match_label.setText(f"{shown} match{'es' if shown != 1 else ''}" if needle else '')
        current = self.results.currentItem()
        if best is not None:
            self.results.setCurrentRow(best[1])     # Enter adds the closest match
        elif current is None or current.isHidden() or not (current.flags() & Qt.ItemIsEnabled):
            self._select_first()
        if self._can_create and needle:
            text = self.filter_edit.text().strip().replace('<', '&lt;')
            self.create_link.setText(
                f'<a href="create" style="color: {_ROMAINE}">Create “{text}” as a new ingredient</a>')
            self.create_link.show()
        else:
            self.create_link.hide()

    def _pickable(self, item):
        return not item.isHidden() and bool(item.flags() & Qt.ItemIsEnabled)

    def _select_first(self):
        for i in range(self.results.count()):
            if self._pickable(self.results.item(i)):
                self.results.setCurrentRow(i)
                return
        self.results.setCurrentRow(-1)
        self._on_selection_changed(None, None)

    def _move(self, step):
        n = self.results.count()
        i = self.results.currentRow()
        direction = 1 if step > 0 else -1
        remaining = abs(step)
        target = i
        j = i
        while remaining and 0 <= j + direction < n:
            j += direction
            if self._pickable(self.results.item(j)):
                target = j
                remaining -= 1
        if target != i and target >= 0:
            self.results.setCurrentRow(target)
            self.results.scrollToItem(self.results.item(target))

    def _on_selection_changed(self, current, _previous):
        row = current.data(_ROW_ROLE) if current is not None else None
        self.unit_label.setText(f'× {row[3]}' if row and row[3] else '')
        self.add_btn.setEnabled(row is not None)
        self._update_preview()

    # --- preview -------------------------------------------------------

    def _update_preview(self, *_):
        current = self.results.currentItem()
        if current is None or self._recipe is None or not self._pickable(current):
            self.preview.setText('')
            return
        row = current.data(_ROW_ROLE)
        child_id, mode = row[0], row[1]
        try:
            qty = float(self.qty_edit.text() or 0)
        except ValueError:
            qty = 0.0
        try:
            servings = float(self._recipe.get('OutputQty') or 1) or 1.0
        except (TypeError, ValueError):
            servings = 1.0
        add_cost = float(row[6] or 0) * qty / servings
        add_kcal = float(row[7] or 0) * qty / servings
        brings = self._allergen_maps[1 if mode == 'recipe' else 0].get(child_id, set())
        new_allergens = sorted(brings - self._recipe_allergens)
        allergen_text = ', '.join(new_allergens) if new_allergens else 'none new'

        cost_now = float(self._recipe.get('CostRaw') or 0)
        total = cost_now + add_cost
        tail = f'→ ${total:.2f}'
        try:
            price = float(self._recipe.get('MenuPrice') or 0)
        except (TypeError, ValueError):
            price = 0.0
        if price > 0:
            tail += f' · {total / price * 100:.1f}%'
        self.preview.setText(
            f'Cost <b>+${add_cost:.2f}</b>&nbsp;&nbsp; Calories <b>+{add_kcal:,.0f}</b>'
            f'&nbsp;&nbsp; Allergens <b>{allergen_text}</b>'
            f'&nbsp;&nbsp; <span style="color: {_MUTED}">{tail}</span>'
        )

    # --- actions -------------------------------------------------------

    def _on_add_clicked(self, *_):
        current = self.results.currentItem()
        if current is None or not self._pickable(current):
            QMessageBox.warning(self, 'No Selection', 'Pick an ingredient or recipe to add.')
            return
        try:
            qty = float(self.qty_edit.text() or 0)
        except ValueError:
            qty = 0.0
        if qty <= 0:
            QMessageBox.warning(self, 'Invalid Qty', 'Qty must be greater than zero.')
            self.qty_edit.setFocus()
            return
        row = current.data(_ROW_ROLE)
        if self._on_add is None:
            self.selected = row
            self.qty = qty
            self.accept()
            return
        self._on_add(row[0], row[1], qty, row[2])
        if not self.keep_open.isChecked():
            self.accept()
            return
        # Ready for the next pick: reload (the added row is now
        # "already in recipe"), reset the quantity, back to the search.
        self._load()
        self.qty_edit.setText('1')
        self.filter_edit.selectAll()
        self.filter_edit.setFocus()

    def _create_ingredient(self):
        '''"Create '<text>' as a new ingredient": the New ingredient
        dialog with the name filled in (and the USDA lookup already
        searching it); the new ingredient comes back selected.'''
        from gui.dialogs.ingredient_new import IngredientNewDialog
        dlg = IngredientNewDialog(parent=self, name=self.filter_edit.text().strip())
        if dlg.exec() != QDialog.Accepted or not dlg.new_id:
            return
        self._allergen_maps = db.get_component_allergen_maps()
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self._load(select_key=('ingredient', dlg.new_id))
        self.qty_edit.setFocus()
        self.qty_edit.selectAll()
