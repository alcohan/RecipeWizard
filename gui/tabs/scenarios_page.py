'''Configure › Scenarios: what-if layers over the baseline (an airport
store's packaging and menu prices, take-out vs in-store packaging).

A scenario list on the left; on the right the chosen scenario's rules,
one card per template plus "All recipes", the tags it leaves out, and
its menu prices. Each rule shows what it does to cost across the menu.
Scenarios only show in Analytics; they never change recipes.

Edits save as they're made; Ctrl+Z / Ctrl+Y (or the Undo / Redo
buttons) step through them, restoring every scenario as it was.
'''
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator, QKeySequence, QShortcut, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QListWidget, QListWidgetItem, QMenu, QMessageBox, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

import db
from gui.services import food_cost
from gui.widgets import config_kit as kit
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.text_fit import literal
from gui.widgets.toolbar_controls import ToolbarCombo
from utilities import scenarios


ACTION_LABELS = (
    ('substitute', 'Swap an item'),
    ('add', 'Add an item'),
    ('remove', 'Remove an item'),
    ('price_adjust', 'Change menu price'),
)


def _money(value, signed=False):
    if value is None:
        return ''
    if signed:
        return f'{"+" if value >= 0 else "−"}${abs(value):,.2f}'
    return f'${value:,.2f}'


def _qty(value):
    return '{:g}'.format(value)


def _clear(layout):
    while layout.count():
        w = layout.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()


def _plain_note(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
    return lbl


# --- undo -----------------------------------------------------------------

class _EditCommand(QUndoCommand):
    '''Runs one edit, then undoes / redoes by restoring every scenario
    from a snapshot taken before and after it.'''

    def __init__(self, page, label, apply):
        super().__init__(label)
        self._page = page
        self._apply = apply
        self._before = self._after = None
        self._select_before = page.current_id()
        self._select_after = None

    def redo(self):
        if self._before is None:
            self._before = scenarios.snapshot_all()
            result = self._apply()
            self._after = scenarios.snapshot_all()
            self._select_after = result if isinstance(result, int) else self._page.current_id()
        else:
            scenarios.restore_all(self._after)
        self._page.refresh(select_id=self._select_after)

    def undo(self):
        scenarios.restore_all(self._before)
        self._page.refresh(select_id=self._select_before)


# --- pieces ---------------------------------------------------------------

class TagChips(QWidget):
    '''Chosen tags as removable chips, plus a "+ Tag" menu of the rest.
    `changed(list of tag ids)` fires on every add or remove.'''

    changed = Signal(list)

    def __init__(self, kinds, empty_text='None', parent=None):
        super().__init__(parent)
        self._kinds = kinds
        self._empty_text = empty_text
        self._ids = []
        self._layout = FlowLayout(self, spacing=6)
        self._layout.setContentsMargins(0, 0, 0, 0)
        policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._tags = {}
        self.reload_tags()

    def reload_tags(self):
        self._tags = {t['id']: t for kind in self._kinds for t in db.get_tags(kind=kind)}

    def set_ids(self, ids):
        self._ids = [i for i in ids if i in self._tags]
        self._rebuild()

    def ids(self):
        return list(self._ids)

    def _rebuild(self):
        _clear(self._layout)
        for tag_id in self._ids:
            tag = self._tags[tag_id]
            chip = QToolButton()
            chip.setText(f'{literal(tag["name"])}  ×')
            chip.setCursor(Qt.PointingHandCursor)
            chip.setToolTip('Remove')
            color = tag.get('color') or '#64748b'
            chip.setStyleSheet(f'QToolButton {{ border: 1px solid {color}; border-radius: 11px; padding: 2px 10px;'
                               f' background: #ffffff; color: {kit.KALE}; }}'
                               ' QToolButton:hover { background: #f3ece0; }')
            chip.clicked.connect(lambda _c=False, t=tag_id: self._remove(t))
            self._layout.addWidget(chip)
        if not self._ids and self._empty_text:
            self._layout.addWidget(_plain_note(self._empty_text))
        add = QToolButton()
        add.setText('+ Tag')
        add.setCursor(Qt.PointingHandCursor)
        add.setStyleSheet(f'QToolButton {{ border: 1px dashed {kit.FIELD_BORDER}; border-radius: 11px;'
                          f' padding: 2px 10px; background: transparent; color: {kit.KALE}; }}'
                          ' QToolButton:hover { background: #f3ece0; }')
        add.clicked.connect(lambda: self._menu(add))
        add.setEnabled(any(t not in self._ids for t in self._tags))
        self._layout.addWidget(add)

    def _menu(self, anchor):
        menu = QMenu(self)
        last_kind = None
        for tag in self._tags.values():
            if tag['id'] in self._ids:
                continue
            if last_kind is not None and tag['kind'] != last_kind:
                menu.addSeparator()
            last_kind = tag['kind']
            menu.addAction(literal(tag['name'])).triggered.connect(
                lambda _c=False, t=tag['id']: self._add(t))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _add(self, tag_id):
        self._ids.append(tag_id)
        self._rebuild()
        self.changed.emit(self.ids())

    def _remove(self, tag_id):
        self._ids = [t for t in self._ids if t != tag_id]
        self._rebuild()
        self.changed.emit(self.ids())


class IngredientCombo(QComboBox):
    '''Type-to-find ingredient picker; `suggested` ids come first.'''

    def __init__(self, ingredients, suggested=(), parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(280)
        self.setMaxVisibleItems(16)
        self.setStyleSheet(f'QComboBox {{ min-height: 30px; padding: 0 8px; border: 1px solid {kit.FIELD_BORDER};'
                           f' border-radius: 4px; background: #ffffff; color: {kit.KALE}; }}'
                           f' QComboBox:focus {{ border: 2px solid {kit.ROMAINE}; }}')
        by_id = {i['Id']: i for i in ingredients}
        first = [by_id[i] for i in suggested if i in by_id]
        for ing in first:
            self.addItem(ing['Name'], ing['Id'])
        if first:
            self.insertSeparator(self.count())
        for ing in ingredients:
            if ing['Id'] not in suggested:
                self.addItem(ing['Name'], ing['Id'])
        completer = QCompleter(self.model(), self)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)
        self.setCurrentIndex(-1)
        self.lineEdit().setPlaceholderText('Find an ingredient')

    def ingredient_id(self):
        i = self.findText(self.currentText().strip(), Qt.MatchFixedString)
        return self.itemData(i) if i >= 0 else None

    def set_ingredient(self, ingredient_id):
        i = self.findData(ingredient_id)
        self.setCurrentIndex(i)
        if i < 0:
            self.setEditText('')


class RuleDialog(QDialog):
    '''Add or edit one rule. `values()` is the rule's fields plus
    except_tags.'''

    def __init__(self, scope_name, ingredients, suggested=(), rule=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{"Edit" if rule else "Add"} rule · {scope_name}')
        self.setStyleSheet(f'QDialog {{ background: #ffffff; }} QLabel {{ color: {kit.KALE}; }}')
        self.setMinimumWidth(460)
        rule = rule or {}

        self.action = ToolbarCombo()
        for key, label in ACTION_LABELS:
            self.action.addItem(label, key)
        self.action.setCurrentIndex(max(0, self.action.findData(rule.get('action', 'substitute'))))
        self.action.currentIndexChanged.connect(self._sync)

        self.from_combo = IngredientCombo(ingredients, suggested)
        self.from_combo.set_ingredient(rule.get('from_ingredient'))
        self.to_combo = IngredientCombo(ingredients)
        self.to_combo.set_ingredient(rule.get('to_ingredient'))
        self.qty = kit.field(90)
        self.qty.setAlignment(Qt.AlignRight)
        self.qty.setValidator(QDoubleValidator(0.0, 100000.0, 4))
        q = rule.get('quantity')
        self.qty.setText('' if q is None else _qty(q))
        self.amount = kit.field(90)
        self.amount.setAlignment(Qt.AlignRight)
        self.amount.setValidator(QDoubleValidator(-1000.0, 1000.0, 2))
        a = rule.get('amount')
        self.amount.setText('' if a is None else '{:.2f}'.format(a))
        self.except_tags = TagChips(('recipe_tag',), empty_text='')
        self.except_tags.set_ids(rule.get('except_tags', []))

        self._rows = {}
        form = QVBoxLayout()
        form.setSpacing(12)
        for key, label, widget in (('action', 'Rule', self.action),
                                   ('from', 'Replace', self.from_combo),
                                   ('to', 'With', self.to_combo),
                                   ('qty', 'Quantity', self.qty),
                                   ('amount', 'Change ($)', self.amount),
                                   ('except', 'Except recipes tagged', self.except_tags)):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(4)
            title = kit.eyebrow(label)
            bl.addWidget(title)
            bl.addWidget(widget)
            self._rows[key] = (box, title)
            form.addWidget(box)
        self.error = QLabel('')
        self.error.setStyleSheet(f'color: {kit.WARN};')
        self.error.hide()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Save' if rule else 'Add rule')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addWidget(kit.subheading(scope_name))
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)
        self._sync()

    def _sync(self, *_):
        action = self.action.currentData()
        self._rows['from'][0].setVisible(action in ('substitute', 'remove'))
        self._rows['to'][0].setVisible(action in ('substitute', 'add'))
        self._rows['to'][1].setText('WITH' if action == 'substitute' else 'ITEM')
        self._rows['qty'][0].setVisible(action in ('substitute', 'add'))
        self._rows['qty'][1].setText('× REPLACED AMOUNT' if action == 'substitute' else 'QUANTITY')
        self.qty.setPlaceholderText('1')
        self._rows['amount'][0].setVisible(action == 'price_adjust')
        self.adjustSize()

    def values(self):
        action = self.action.currentData()
        text = self.qty.text().strip()
        try:
            qty = float(text) if text and action in ('substitute', 'add') else None
        except ValueError:
            qty = None
        try:
            amount = float(self.amount.text()) if action == 'price_adjust' else None
        except ValueError:
            amount = None
        return {
            'action': action,
            'from_ingredient': self.from_combo.ingredient_id() if action in ('substitute', 'remove') else None,
            'to_ingredient': self.to_combo.ingredient_id() if action in ('substitute', 'add') else None,
            'quantity': qty,
            'amount': amount,
            'except_tags': self.except_tags.ids(),
        }

    def _accept(self):
        v = self.values()
        problem = None
        if v['action'] in ('substitute', 'remove') and v['from_ingredient'] is None:
            problem = 'Choose the item to replace.'
        elif v['action'] in ('substitute', 'add') and v['to_ingredient'] is None:
            problem = 'Choose the item to use.'
        elif v['action'] == 'substitute' and v['from_ingredient'] == v['to_ingredient']:
            problem = 'Choose a different item.'
        elif v['action'] == 'price_adjust' and not v['amount']:
            problem = 'Enter a price change.'
        if problem:
            self.error.setText(problem)
            self.error.show()
            return
        self.accept()


# --- the page --------------------------------------------------------------

class ScenariosPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scenarios = []
        self._ingredients = []
        self._names = {}
        self._loading = False

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(lambda _i: self._sync_undo())
        for keys, slot in ((QKeySequence.Undo, self.undo_stack.undo), (QKeySequence.Redo, self.undo_stack.redo)):
            sc = QShortcut(keys, self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        # list column
        new_btn = kit.button('+ New')
        new_btn.clicked.connect(self.new_scenario)
        head = QHBoxLayout()
        head.addWidget(kit.heading('Scenarios'))
        head.addStretch()
        head.addWidget(new_btn)
        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.currentRowChanged.connect(lambda _r: self._show_current())
        self.list.model().rowsMoved.connect(self._on_reordered)
        left = QWidget()
        left.setFixedWidth(280)
        left.setObjectName('ScenarioList')
        left.setStyleSheet(f'QWidget#ScenarioList {{ border-right: 1px solid {kit.BORDER}; }}')
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 20, 16, 16)
        ll.setSpacing(12)
        ll.addLayout(head)
        ll.addWidget(kit.note('Compare in Analytics'))
        ll.addWidget(self.list, stretch=1)

        # detail header
        self.name_edit = kit.field(320)
        self.name_edit.editingFinished.connect(self._on_name)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(kit.eyebrow('Name'))
        name_col.addWidget(self.name_edit)
        self.undo_btn = kit.button('Undo')
        self.undo_btn.clicked.connect(self.undo_stack.undo)
        self.redo_btn = kit.button('Redo')
        self.redo_btn.clicked.connect(self.undo_stack.redo)
        self.dup_btn = kit.button('Duplicate')
        self.dup_btn.clicked.connect(self.duplicate_current)
        self.delete_btn = kit.button('Delete…', danger=True)
        self.delete_btn.clicked.connect(self.delete_current)
        top = QHBoxLayout()
        top.addLayout(name_col)
        top.addStretch()
        for b in (self.undo_btn, self.redo_btn, self.dup_btn, self.delete_btn):
            top.addWidget(b, alignment=Qt.AlignBottom)

        self.rules_box = QVBoxLayout()
        self.rules_box.setSpacing(12)

        excl_card, el = kit.card()
        el.addWidget(kit.subheading('Left out'))
        el.addWidget(kit.note('Recipes with these tags'))
        self.exclusions = TagChips(('recipe', 'recipe_tag'), empty_text='No recipes left out')
        self.exclusions.changed.connect(self._on_exclusions)
        el.addWidget(self.exclusions)

        price_card, pl = kit.card()
        price_head = QHBoxLayout()
        price_head.addWidget(kit.subheading('Menu prices'))
        price_head.addStretch()
        self.price_filter = kit.field(220)
        self.price_filter.setPlaceholderText('Find a recipe')
        self.price_filter.textChanged.connect(self._filter_prices)
        price_head.addWidget(self.price_filter)
        pl.addLayout(price_head)
        pl.addWidget(kit.note('Type a price to set it here; clear it to follow the menu'))
        self.prices = QTableWidget(0, 5)
        self.prices.setHorizontalHeaderLabels(['Recipe', 'Menu', 'Here', 'Cost here', 'Food cost'])
        self.prices.verticalHeader().hide()
        self.prices.setSelectionMode(QAbstractItemView.SingleSelection)
        self.prices.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                    | QAbstractItemView.AnyKeyPressed)
        self.prices.setShowGrid(False)
        self.prices.setAlternatingRowColors(True)
        self.prices.setStyleSheet(f'QTableWidget {{ border: 0; color: {kit.KALE};'
                                  ' alternate-background-color: #fbf7ef; }'
                                  f' QHeaderView::section {{ border: 0; border-bottom: 1px solid {kit.BORDER};'
                                  f' background: #ffffff; color: {kit.MUTED}; padding: 4px 6px; }}')
        hdr = self.prices.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.prices.itemChanged.connect(self._on_price_item)
        pl.addWidget(self.prices)

        self.detail = QWidget()
        self.detail.setObjectName('ScenarioDetail')
        self.detail.setStyleSheet(f'QWidget#ScenarioDetail {{ background: {kit.BG}; }}')
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(28, 20, 28, 28)
        dl.setSpacing(20)
        dl.addLayout(top)
        dl.addLayout(self.rules_box)
        dl.addWidget(excl_card)
        dl.addWidget(price_card)
        dl.addStretch()

        self.empty = QWidget()
        em = QVBoxLayout(self.empty)
        em.setContentsMargins(28, 24, 28, 24)
        em.addWidget(kit.heading('No scenarios yet'))
        em.addWidget(kit.note('A scenario changes packaging or menu prices for one kind of store or order, '
                              'like an airport location or take-out.'))
        start = kit.button('+ New scenario', primary=True)
        start.clicked.connect(self.new_scenario)
        em.addWidget(start, alignment=Qt.AlignLeft)
        em.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.detail)
        self.scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; border: 0; }}')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(left)
        layout.addWidget(self.scroll, stretch=1)
        layout.addWidget(self.empty, stretch=1)

        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(300)
        self._emit_timer.timeout.connect(self.changed.emit)
        self.refresh()

    # --- data ------------------------------------------------------------

    def library_replaced(self):
        '''After a restore or reset: undo would put back another
        library's scenarios.'''
        self.undo_stack.clear()
        self.refresh()

    def showEvent(self, event):
        # Ingredients, formats and recipes may have changed elsewhere.
        self.refresh()
        super().showEvent(event)

    def current_id(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def current(self):
        sid = self.current_id()
        return next((s for s in self._scenarios if s['id'] == sid), None)

    def refresh(self, select_id=None):
        select_id = select_id or self.current_id()
        self._scenarios = scenarios.get_scenarios()
        self._all_ingredients = db.get_ingredients()
        self._ingredients = [i for i in self._all_ingredients if (i.get('status') or 'active') != 'archived']
        self._names = {i['Id']: i['Name'] for i in self._all_ingredients}
        self._formats = db.get_tags(kind='recipe')
        self.exclusions.reload_tags()
        self.list.blockSignals(True)
        self.list.clear()
        for s in self._scenarios:
            item = QListWidgetItem(self._item_text(s))
            item.setData(Qt.UserRole, s['id'])
            # Room for both lines with the selected row's thicker border.
            item.setSizeHint(QSize(0, self.list.fontMetrics().lineSpacing() * 2 + 26))
            self.list.addItem(item)
        self.list.blockSignals(False)
        row = next((i for i, s in enumerate(self._scenarios) if s['id'] == select_id),
                   0 if self._scenarios else -1)
        self.list.setCurrentRow(row)
        self._show_current()
        self._sync_undo()

    def _item_text(self, s):
        n, p = len(s['rules']), len(s['prices'])
        bits = [f'{n} rule{"" if n == 1 else "s"}']
        if p:
            bits.append(f'{p} price{"" if p == 1 else "s"}')
        return f'{s["name"]}\n{" · ".join(bits)}'

    def _sync_undo(self):
        try:
            self.undo_stack.count()
        except RuntimeError:    # the stack goes first while the page is torn down
            return
        self.undo_btn.setEnabled(self.undo_stack.canUndo())
        self.redo_btn.setEnabled(self.undo_stack.canRedo())
        self.undo_btn.setToolTip(self.undo_stack.undoText())
        self.redo_btn.setToolTip(self.undo_stack.redoText())

    # --- showing -----------------------------------------------------------

    def _show_current(self):
        s = self.current()
        self.scroll.setVisible(s is not None)
        self.empty.setVisible(s is None)
        if s is None:
            return
        self._loading = True
        self.name_edit.setText(s['name'])
        self.exclusions.set_ids(s['exclusions'])
        self._loading = False
        result = scenarios.matrix(scenario_ids=[s['id']])
        self._build_rules(s, result)
        self._fill_prices(s, result)

    def _rule_effects(self, sid, result):
        '''{rule_id: (recipe count, average delta)}'''
        acc = {}
        for r in result['recipes']:
            for a in r['cells'][sid]['applied']:
                acc.setdefault(a['rule_id'], []).append(a['delta'])
        return {rid: (len(d), sum(d) / len(d)) for rid, d in acc.items()}

    def _build_rules(self, s, result):
        _clear(self.rules_box)
        effects = self._rule_effects(s['id'], result)
        counts = {}
        for r in result['recipes']:
            counts[r['format_id']] = counts.get(r['format_id'], 0) + 1
        scopes = [(f['id'], f['name']) for f in self._formats] + [(None, 'All recipes')]
        for tag_id, name in scopes:
            rules = [r for r in s['rules'] if r['format_tag_id'] == tag_id]
            n = len(result['recipes']) if tag_id is None else counts.get(tag_id, 0)
            self.rules_box.addWidget(self._scope_card(tag_id, name, n, rules, effects))

    def _scope_card(self, tag_id, name, n, rules, effects):
        frame, cl = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading(name))
        count = _plain_note(f'{n} recipe{"" if n == 1 else "s"}')
        head.addWidget(count)
        head.addStretch()
        add = kit.button('+ Rule')
        add.clicked.connect(lambda _c=False: self.add_rule(tag_id, name))
        head.addWidget(add)
        cl.addLayout(head)
        if not rules:
            cl.addWidget(kit.note('No changes'))
        for rule in rules:
            cl.addWidget(self._rule_row(rule, name, effects.get(rule['id'])))
        return frame

    def _rule_text(self, rule):
        tags = {t['id']: t['name'] for t in db.get_tags(kind='recipe_tag')}
        return scenarios.describe_rule(rule, self._names, tags)

    def _rule_row(self, rule, scope_name, effect):
        row = QFrame()
        row.setObjectName('RuleRow')
        row.setStyleSheet(f'QFrame#RuleRow {{ border-top: 1px solid {kit.BORDER}; }}')
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 8, 0, 0)
        hl.setSpacing(10)
        text = QLabel(self._rule_text(rule))
        text.setTextFormat(Qt.PlainText)
        text.setWordWrap(True)
        text.setMinimumWidth(1)
        text.setStyleSheet(f'color: {kit.KALE};')
        hl.addWidget(text, stretch=1)
        if effect is None:
            fx = QLabel('No recipes')
            fx.setStyleSheet(f'color: {kit.WARN}; font-size: 12px;')
        else:
            n, avg = effect
            what = 'price' if rule['action'] == 'price_adjust' else 'cost'
            fx = QLabel(f'{_money(avg, signed=True)} {what} · {n} recipe{"" if n == 1 else "s"}')
            fx.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
        hl.addWidget(fx)
        edit = kit.button('Edit')
        edit.clicked.connect(lambda _c=False: self.edit_rule(rule, scope_name))
        remove = kit.button('×')
        remove.setToolTip('Delete rule')
        remove.clicked.connect(lambda _c=False: self.delete_rule(rule))
        hl.addWidget(edit)
        hl.addWidget(remove)
        return row

    def _fill_prices(self, s, result):
        sid = s['id']
        names = {f['id']: f['name'] for f in self._formats}
        scroll = self.prices.verticalScrollBar().value()
        self.prices.blockSignals(True)
        self.prices.setRowCount(0)
        rows = sorted(result['recipes'], key=lambda r: (names.get(r['format_id'], '~'), r['name'].lower()))
        self.prices.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cell, base = r['cells'][sid], r['base']
            fmt = names.get(r['format_id'])
            label = QTableWidgetItem(r['name'] + (f'  · {fmt}' if fmt else ''))
            label.setData(Qt.UserRole, r['id'])
            label.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            menu = QTableWidgetItem(_money(base['price']))
            menu.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            override = s['prices'].get(r['id'])
            here = QTableWidgetItem('' if cell['excluded'] else
                                    _money(override) if override is not None else _money(cell['price']))
            if override is None:
                here.setForeground(Qt.gray)
                here.setToolTip('Follows the menu')
            else:
                f = here.font()
                f.setBold(True)
                here.setFont(f)
            if cell['excluded']:
                here.setFlags(Qt.ItemIsEnabled)
                here.setText('Left out')
            cost = QTableWidgetItem('' if cell['excluded'] else _money(cell['cost']))
            cost.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if not cell['excluded'] and abs((cell['cost'] or 0) - base['cost']) >= 0.005:
                cost.setToolTip(f'Menu {_money(base["cost"])}')
            pct = QTableWidgetItem('' if cell['pct'] is None else f'{cell["pct"]:.1f}%')
            pct.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if food_cost.over_percent(cell['pct']):
                pct.setForeground(Qt.darkRed)
                pct.setToolTip(f'Over the {food_cost.target_percent():.0f}% target')
            for c in (1, 2, 3, 4):
                (menu, here, cost, pct)[c - 1].setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for c, item in enumerate((label, menu, here, cost, pct)):
                self.prices.setItem(i, c, item)
        self.prices.blockSignals(False)
        shown = max(4, min(len(rows), 14))
        self.prices.setFixedHeight(self.prices.horizontalHeader().height() + 4
                                   + shown * self.prices.verticalHeader().defaultSectionSize())
        self._filter_prices()
        self.prices.verticalScrollBar().setValue(scroll)

    def _filter_prices(self, *_):
        needle = self.price_filter.text().strip().lower()
        for i in range(self.prices.rowCount()):
            item = self.prices.item(i, 0)
            self.prices.setRowHidden(i, bool(needle) and needle not in item.text().lower())

    # --- edits -------------------------------------------------------------

    def _do(self, label, apply):
        self.undo_stack.push(_EditCommand(self, label, apply))
        self._emit_timer.start()

    def new_scenario(self):
        taken = {s['name'].lower() for s in self._scenarios}
        name, n = 'New scenario', 2
        while name.lower() in taken:
            name, n = f'New scenario {n}', n + 1
        self._do('New scenario', lambda: scenarios.create_scenario(name))
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def duplicate_current(self):
        s = self.current()
        if s is None:
            return
        taken = {x['name'].lower() for x in self._scenarios}
        name, n = f'{s["name"]} copy', 2
        while name.lower() in taken:
            name, n = f'{s["name"]} copy {n}', n + 1
        self._do('Duplicate scenario', lambda: scenarios.duplicate_scenario(s['id'], name))

    def delete_current(self):
        s = self.current()
        if s is None:
            return
        if QMessageBox.question(self, 'Delete scenario', f'Delete the scenario “{s["name"]}”?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._do('Delete scenario', lambda: scenarios.delete_scenario(s['id']) or 0)

    def _on_name(self):
        s = self.current()
        name = self.name_edit.text().strip()
        if self._loading or s is None or name == s['name']:
            return
        taken = {x['name'].lower() for x in self._scenarios if x['id'] != s['id']}
        if not name or name.lower() in taken:
            QMessageBox.information(self, 'Scenario name', f'There is already a scenario called “{name}”.'
                                    if name else 'A scenario needs a name.')
            self.name_edit.setText(s['name'])
            return
        self._do('Rename scenario', lambda: scenarios.rename_scenario(s['id'], name))

    def _on_reordered(self, *_args):
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        self._do('Reorder scenarios', lambda: scenarios.reorder_scenarios(ids))

    def _on_exclusions(self, tag_ids):
        s = self.current()
        if self._loading or s is None:
            return
        self._do('Change left-out tags', lambda: scenarios.set_scenario_exclusions(s['id'], tag_ids))

    def _suggested(self, tag_id):
        '''The format's template items, with a sub-recipe item (a packaging
        kit) opened up into its ingredients: rules swap ingredients.'''
        if tag_id is None:
            return []
        out = []
        for c in db.get_tag_components(tag_id):
            ids = [c['child_ingredient']] if c['child_ingredient'] else db.recipe_leaf_ingredient_ids(c['child_recipe'])
            out += [i for i in ids if i and i not in out]
        return out

    def add_rule(self, tag_id, scope_name):
        s = self.current()
        if s is None:
            return
        dlg = RuleDialog(scope_name, self._ingredients, self._suggested(tag_id), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        except_tags = v.pop('except_tags')
        self._do('Add rule', lambda: scenarios.add_rule(s['id'], format_tag_id=tag_id,
                                                        except_tags=except_tags, **v) and None)

    def edit_rule(self, rule, scope_name):
        # An archived item the rule already uses stays pickable.
        keep = {rule['from_ingredient'], rule['to_ingredient']}
        choices = [i for i in self._all_ingredients
                   if (i.get('status') or 'active') != 'archived' or i['Id'] in keep]
        dlg = RuleDialog(scope_name, choices, self._suggested(rule['format_tag_id']),
                         rule=rule, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        except_tags = v.pop('except_tags')

        def apply():
            scenarios.update_rule(rule['id'], **v)
            scenarios.set_rule_exclusions(rule['id'], except_tags)
        self._do('Edit rule', apply)

    def delete_rule(self, rule):
        self._do('Delete rule', lambda: scenarios.delete_rule(rule['id']))

    def _on_price_item(self, item):
        s = self.current()
        if s is None or item.column() != 2:
            return
        rid = self.prices.item(item.row(), 0).data(Qt.UserRole)
        text = item.text().strip().replace('$', '').replace(',', '')
        if not text:
            price = None
        else:
            try:
                price = round(float(text), 2)
            except ValueError:
                QTimer.singleShot(0, self._show_current)
                return
            if price <= 0:
                price = None
        if price == s['prices'].get(rid):
            QTimer.singleShot(0, self._show_current)
            return
        # Rebuilding the table from inside its own itemChanged is unsafe.
        QTimer.singleShot(0, lambda: self._do('Set menu price', lambda: scenarios.set_price(s['id'], rid, price)))
