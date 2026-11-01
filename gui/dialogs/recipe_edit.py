'''Recipe editor — widget + thin modal-dialog wrapper.

RecipeEditWidget is an embeddable QWidget with the full editor UX
(QUndoStack-backed demographic + component edits, format tag selector,
wedge preview, nutrition rollup, allergens). It's hosted inline inside
the Recipes workspace as a document tab in the normal flow.

RecipeEditDialog is a thin QDialog that wraps the widget for callers
that still want modal behavior (currently the Ingredient editor's
"Used in recipes" link, which opens a recipe from inside its own
modal context — tabs wouldn't help).

All mutations push through self.undo_stack so Ctrl+Z reverses them.
QUndoStack.indexChanged drives the refresh that re-reads
RecipesWithNutrition, redraws the wedge, and re-syncs the editable
demographic fields.

UX notes:
- Name / Yield Unit / Recipe Yield / Menu Price auto-save on
  focus-out or Enter; there is no explicit "Update" button.
- Component quantities are edited inline (double-click, or right-click
  Edit).
- Right-click a component also exposes Remove.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QDoubleValidator, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSplitter, QStyledItemDelegate, QTableView, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.nutrition_label import NutritionLabelDialog
from gui.dialogs.price_history import PriceHistoryDialog
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.models.components_model import RecipeComponentsModel
from gui.undo.recipe_commands import (
    AddComponentCommand, RemoveComponentCommand, ReorderComponentsCommand,
    SetComponentQtyCommand, SetRecipeTagCommand, UpdateRecipeInfoCommand,
)
from gui.widgets.tag_badge import TagBadgeCellDelegate
from gui.widgets.tag_selector import TagSelector
from gui.widgets.template_summary import TemplateSummaryWidget
from gui.widgets.wedge_view import WedgeView


WEDGE_SIZE = 220
# Order matters — the info strip in _build_summary joins these in order.
INFO_FIELDS = (('Weight', 'Weight (g)'), ('Cost', 'Cost'), ('Components', 'Components'))
# Fallback target food cost when the user hasn't set one. Stored in
# QSettings('food_cost/target_pct') as a float in [0, 1].
_DEFAULT_FOOD_COST_TARGET = 0.28


class _QuantityDelegate(QStyledItemDelegate):
    '''Numeric-only editor for the Quantity column. Wires a QLineEdit with
    QDoubleValidator so the user can't commit garbage text.'''

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QDoubleValidator(0.0001, 1_000_000.0, 4, editor)
        validator.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(validator)
        return editor


class RecipeEditWidget(QWidget):
    '''Embeddable recipe editor. The container (EditorTabs or
    RecipeEditDialog) owns window chrome and the close flow; this
    widget emits signals for the title / modified state / delete and
    exposes close_requested() so the container can flush pending edits
    and stamp the cost snapshot before tearing down.'''

    titleChanged = Signal(str)       # recipe's current name — tab/window title
    recipeDeleted = Signal(int)      # recipe_id, fired after confirm + DB delete
    modifiedChanged = Signal(bool)   # true once any undo-stack push has fired

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.modified = False
        self.status_message = ''
        self._being_deleted = False

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._refresh)

        # Bring the recipe in line with its current format's template
        # before reading anything else — fixes sample-seeded recipes
        # that were tagged but missed some template items, and recipes
        # whose template was edited after they were tagged. Silent /
        # not on the undo stack: this reconciles latent data drift,
        # not a user action.
        db.reconcile_recipe_template(recipe_id)

        recipe = db.recipe_info(recipe_id)
        self._title = recipe['Name']

        self._recipe_snapshot = self._snapshot(recipe)
        self.components_model = RecipeComponentsModel(recipe_id)
        self.components_model.qtyEdited.connect(self._on_qty_edited)
        self.components_model.rowsReordered.connect(self._on_components_reordered)

        left_col = self._build_left(recipe)
        right_col = self._build_summary(recipe)

        # Undo/Redo actions — keyboard shortcuts only, no toolbar buttons.
        # Scoped to the widget so a container with multiple tabs still
        # only sees the active tab's undo stack.
        undo_action = self.undo_stack.createUndoAction(self, 'Undo')
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        redo_action = self.undo_stack.createRedoAction(self, 'Redo')
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.addAction(undo_action)
        self.addAction(redo_action)

        delete_btn = QPushButton('Delete Recipe')
        delete_btn.setStyleSheet(
            'QPushButton { background-color: #b80700; color: white;'
            ' border: 0; border-radius: 6px; padding: 6px 12px;'
            ' font-weight: 600; }'
            ' QPushButton:hover { background-color: #a00600; }'
        )
        delete_btn.setAutoDefault(False)
        delete_btn.setDefault(False)
        delete_btn.clicked.connect(self._on_delete)
        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(delete_btn)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left_col)
        self.splitter.addWidget(right_col)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter, stretch=1)
        layout.addLayout(action_row)

        # Restore splitter ratios from the previous session if we have
        # them. Written back from close_requested() below.
        state = QSettings().value('recipeEditor/splitter')
        if state is not None:
            self.splitter.restoreState(state)

        self._refresh()

    # --- container-facing API ------------------------------------------

    def title(self):
        return self._title

    def close_requested(self):
        '''Called by the container (tab bar or modal wrapper) when this
        widget is about to go away. Flushes any pending demographic
        edit, stamps the cost snapshot, saves the splitter state.
        Returns True to allow the close; there's no "unsaved prompt"
        today because every edit auto-commits.'''
        self._maybe_commit_info()
        if not self._being_deleted:
            try:
                db.update_recipe_cost_snapshot(self.recipe_id)
            except Exception:
                # A failure here is a UX nicety, not correctness —
                # swallow so a flaky DB doesn't block closing.
                pass
        QSettings().setValue('recipeEditor/splitter', self.splitter.saveState())
        return True

    # --- layout builders -----------------------------------------------

    def _build_left(self, recipe):
        # Demographic — fields auto-save on focus-out / Enter, no Update button.
        demo_box = QGroupBox('Recipe')
        self.name_edit = QLineEdit(recipe['Name'])
        self.name_edit.editingFinished.connect(self._maybe_commit_info)
        self.unit_edit = QLineEdit(recipe['Unit'])
        self.unit_edit.editingFinished.connect(self._maybe_commit_info)
        self.yield_edit = QLineEdit(str(recipe['OutputQty']))
        self.yield_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.yield_edit.editingFinished.connect(self._maybe_commit_info)
        # Blank is meaningful: "not on the menu / no food-cost %". We parse
        # that in _maybe_commit_info rather than relying on a validator that
        # would reject empty.
        self.menu_price_edit = QLineEdit(_format_menu_price(recipe.get('MenuPrice')))
        self.menu_price_edit.setPlaceholderText('— not on menu')
        self.menu_price_edit.editingFinished.connect(self._maybe_commit_info)

        demo_form = QFormLayout(demo_box)
        demo_form.addRow('Name', self.name_edit)
        demo_form.addRow('Yield Unit', self.unit_edit)
        demo_form.addRow('Recipe Yield', self.yield_edit)
        demo_form.addRow('Menu Price', self.menu_price_edit)

        # Components table — inline editing on Quantity, right-click for Edit/Remove.
        comp_box = QGroupBox('Components')
        self.components_table = QTableView()
        self.components_table.setModel(self.components_model)
        self.components_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.components_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.components_table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        # Drag-reorder rows. The model returns False from dropMimeData
        # for no-op moves and the actual SortOrder update goes through
        # the undo stack (see _on_components_reordered).
        self.components_table.setDragEnabled(True)
        self.components_table.setAcceptDrops(True)
        self.components_table.setDropIndicatorShown(True)
        self.components_table.setDragDropMode(QAbstractItemView.InternalMove)
        self.components_table.setDefaultDropAction(Qt.MoveAction)
        self.components_table.verticalHeader().setVisible(False)
        self.components_table.horizontalHeader().setStretchLastSection(True)
        qty_col = self.components_model.COLUMNS.index('Quantity')
        self.components_table.setItemDelegateForColumn(qty_col, _QuantityDelegate(self.components_table))
        # Type column paints the colored category badge for ingredients
        # (and falls back to the generic 'recipe' label for sub-recipes)
        # — this is the primary place the category reads in the editor.
        type_col = self.components_model.COLUMNS.index('Type')
        self.components_table.setItemDelegateForColumn(type_col, TagBadgeCellDelegate(self.components_table))
        self.components_table.activated.connect(self._on_component_activated)
        self.components_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.components_table.customContextMenuRequested.connect(self._show_components_context_menu)
        self.components_model.modelReset.connect(self.components_table.resizeColumnsToContents)
        self.components_table.resizeColumnsToContents()
        comp_layout = QVBoxLayout(comp_box)
        comp_layout.addWidget(self.components_table)

        # Action buttons
        add_btn = QPushButton('+ Add Component')
        add_btn.clicked.connect(self._on_add_component)
        label_btn = QPushButton('Nutrition Label')
        label_btn.clicked.connect(self._on_nutrition_label)
        history_btn = QPushButton('Price History')
        history_btn.clicked.connect(self._on_price_history)

        action_row = QHBoxLayout()
        action_row.addWidget(add_btn)
        action_row.addWidget(label_btn)
        action_row.addWidget(history_btn)
        action_row.addStretch()

        # Components is the focus of this column — demo on top, components
        # claims the rest of the vertical space, actions pinned to the
        # bottom. Format selector + template items live in the right
        # column alongside the wedge (see _build_summary).
        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.addWidget(demo_box)
        layout.addWidget(comp_box, stretch=1)
        layout.addLayout(action_row)
        return wrap

    def _build_summary(self, recipe):
        '''Right pane: wedge + format selector + template items at the top,
        then a one-line info strip, then nutrition and contains.

        Format moved here from the left column so the left column can be
        Components-dominated. The wedge silhouette and the format
        selector are visually paired (silhouette IS the format).'''
        unit = recipe['Unit']

        self.wedge = WedgeView(self.recipe_id, size=WEDGE_SIZE)

        # Format tag — single-select. Toggle routed through QUndoStack.
        self.tag_grid = TagSelector(
            kind='recipe', item_id=self.recipe_id, title='Format',
            autosave=False, columns=2,
        )
        self.tag_grid.selectionChanged.connect(self._on_tag_changed)
        # Two-row stats summary + click-to-expand flyout for the full
        # item list. Refreshed from _refresh() on every undo-stack tick.
        self.template_panel = TemplateSummaryWidget(self.recipe_id)

        # Format selector + template summary, side by side under the wedge.
        format_row = QHBoxLayout()
        format_row.addWidget(self.tag_grid, stretch=1)
        format_row.addWidget(self.template_panel, stretch=1)

        # One-line "Per <unit> — Weight • Cost • N components" strip below
        # the format row. Text is rebuilt by _refresh().
        self.info_strip = QLabel('')
        self.info_strip.setStyleSheet('color: #475569; padding: 2px 4px;')
        self.info_strip.setTextFormat(Qt.RichText)

        self.nutrition_box = QGroupBox(f'Nutrition (per {unit})')
        self.nutrition_labels = {}
        nut_form = QFormLayout(self.nutrition_box)
        for key, label_text in config.nutrition_fields.items():
            lbl = QLabel('')
            nut_form.addRow(label_text, lbl)
            self.nutrition_labels[key] = lbl

        contains_box = QGroupBox('Contains')
        self.allergens_label = QLabel('')
        self.allergens_label.setWordWrap(True)
        contains_layout = QVBoxLayout(contains_box)
        contains_layout.addWidget(self.allergens_label)

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.addWidget(self.wedge, alignment=Qt.AlignCenter)
        layout.addLayout(format_row)
        layout.addWidget(self.info_strip)
        layout.addWidget(self.nutrition_box)
        layout.addWidget(contains_box)
        layout.addStretch()
        return wrap

    # --- helpers -------------------------------------------------------

    def _snapshot(self, recipe):
        return (
            recipe['Name'], recipe['Unit'], float(recipe['OutputQty']),
            _coerce_menu_price(recipe.get('MenuPrice')),
        )

    def _refresh(self):
        '''Re-read recipe state from DB and update every dependent view.
        Fires on every QUndoStack.indexChanged plus on widget construction.'''
        was_modified = self.modified
        self.modified = True
        if not was_modified:
            self.modifiedChanged.emit(True)
        recipe = db.recipe_info(self.recipe_id)
        self._recipe_snapshot = self._snapshot(recipe)

        self.components_model.refresh()

        # One-line info strip — Weight / Cost / Food cost % / Components.
        # Food cost appears only when the recipe has a menu_price; its
        # color goes amber when above the user's target.
        strip_parts = []
        for key, label_text in INFO_FIELDS:
            value = recipe.get(key)
            if value is None or value == '':
                continue
            strip_parts.append(f"<b>{label_text}</b> {value}")
        food_cost_html = _food_cost_html(recipe.get('CostRaw'), recipe.get('MenuPrice'))
        if food_cost_html:
            # Insert after Cost (index 1 in INFO_FIELDS) when present, else at end.
            insert_at = 2 if len(strip_parts) >= 2 else len(strip_parts)
            strip_parts.insert(insert_at, food_cost_html)
        # "Prices changed" chip: live cost drifted away from the snapshot
        # the user last confirmed by closing the editor.
        prices_changed_html = _prices_changed_html(
            recipe.get('CostRaw'), recipe.get('CostSnapshot'),
        )
        if prices_changed_html:
            strip_parts.append(prices_changed_html)
        sep = '  •  '
        self.info_strip.setText(
            f"Per {recipe['Unit']} — {sep.join(strip_parts)}" if strip_parts else ''
        )

        for key, lbl in self.nutrition_labels.items():
            value = recipe.get(key)
            lbl.setText('' if value is None else str(value))

        allergens = db.get_recipe_allergens(self.recipe_id)
        self.allergens_label.setText(', '.join(allergens) or '(none)')

        self.wedge.refresh()

        # Nutrition group-box title depends on the unit; rebuild on rename.
        self.nutrition_box.setTitle(f"Nutrition (per {recipe['Unit']})")

        # Sync editable demographic fields. The widget the user is currently
        # editing is left alone — otherwise typing in one field while another
        # commits would clobber the in-progress edit.
        for edit, value in (
            (self.name_edit, recipe['Name']),
            (self.unit_edit, recipe['Unit']),
            (self.yield_edit, str(recipe['OutputQty'])),
            (self.menu_price_edit, _format_menu_price(recipe.get('MenuPrice'))),
        ):
            if edit.hasFocus():
                continue
            edit.blockSignals(True)
            if edit.text() != value:
                edit.setText(value)
            edit.blockSignals(False)

        # Sync format-tag selection (so undoing a change visually reverts)
        current_tag = db.get_recipe_tag(self.recipe_id)
        self.tag_grid.set_selected(current_tag['id'] if current_tag else None)
        # Template items panel reflects the now-current format.
        self.template_panel.refresh()

        if recipe['Name'] != self._title:
            self._title = recipe['Name']
            self.titleChanged.emit(self._title)

    # --- handlers ------------------------------------------------------

    def _maybe_commit_info(self):
        '''Auto-save the recipe demographic fields. Wired to each input's
        editingFinished signal and called explicitly from close_requested()
        so a close doesn't lose an in-flight edit.'''
        name = self.name_edit.text().strip()
        if not name:
            # Refuse the empty-name commit; restore the previous value.
            self.name_edit.blockSignals(True)
            self.name_edit.setText(self._recipe_snapshot[0])
            self.name_edit.blockSignals(False)
            return
        unit = self.unit_edit.text()
        try:
            yield_qty = float(self.yield_edit.text() or 0)
        except ValueError:
            self.yield_edit.blockSignals(True)
            self.yield_edit.setText(str(self._recipe_snapshot[2]))
            self.yield_edit.blockSignals(False)
            return
        try:
            menu_price = _parse_menu_price(self.menu_price_edit.text())
        except ValueError:
            # Restore last-committed value so a bogus edit doesn't commit.
            self.menu_price_edit.blockSignals(True)
            self.menu_price_edit.setText(_format_menu_price(self._recipe_snapshot[3]))
            self.menu_price_edit.blockSignals(False)
            return
        after = (name, unit, yield_qty, menu_price)
        if after == self._recipe_snapshot:
            return
        self.undo_stack.push(UpdateRecipeInfoCommand(self.recipe_id, self._recipe_snapshot, after))

    def _on_tag_changed(self, new_tag_id, prev_tag_id):
        if new_tag_id == prev_tag_id:
            return
        label = 'Clear format' if new_tag_id is None else 'Set format'
        self.undo_stack.push(SetRecipeTagCommand(
            self.recipe_id, prev_tag_id, new_tag_id, label,
        ))

    def _on_add_component(self):
        dlg = RecipeComponentAddDialog(self.recipe_id, self.name_edit.text(), parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        child_id, mode, name, _unit, *_ = dlg.selected
        self.undo_stack.push(AddComponentCommand(self.recipe_id, mode, child_id, dlg.qty, name))

    def _on_component_activated(self, view_index):
        '''Double-click or Enter on a row — open the inline Quantity editor.'''
        if not view_index.isValid():
            return
        qty_col = self.components_model.COLUMNS.index('Quantity')
        qty_index = self.components_model.index(view_index.row(), qty_col)
        self.components_table.setCurrentIndex(qty_index)
        self.components_table.edit(qty_index)

    def _on_qty_edited(self, row, new_qty):
        '''The components model emitted qtyEdited because the user finished
        an inline edit. Push a SetComponentQtyCommand so the change is
        undoable.'''
        row_dict = self.components_model.row_dict(row)
        try:
            old_qty = float(row_dict.get('QuantityRaw', 0) or 0)
        except (TypeError, ValueError):
            old_qty = 0.0
        if new_qty == old_qty:
            return
        self.undo_stack.push(SetComponentQtyCommand(
            self.recipe_id, row_dict['Type'], row_dict['Id'],
            old_qty, new_qty, row_dict['Name'],
        ))

    def _show_components_context_menu(self, point):
        index = self.components_table.indexAt(point)
        if not index.isValid():
            return
        row_dict = self.components_model.row_dict(index.row())
        is_template = row_dict.get('FromTemplateTagId') is not None
        menu = QMenu(self.components_table)
        edit_action = menu.addAction('Edit Quantity')
        remove_action = menu.addAction('Remove')
        if is_template:
            # Template-added rows are managed by the template, not the
            # recipe. Disable mutating actions; the user can edit the
            # template itself via the Tags Manager.
            edit_action.setEnabled(False)
            remove_action.setEnabled(False)
            edit_action.setToolTip('Edit this in the Template Editor')
            remove_action.setToolTip('Edit this in the Template Editor')
        chosen = menu.exec(self.components_table.viewport().mapToGlobal(point))
        if chosen is edit_action:
            self._on_component_activated(index)
        elif chosen is remove_action:
            self._remove_component(index.row())

    def _remove_component(self, row):
        row_dict = self.components_model.row_dict(row)
        name = row_dict['Name']
        if QMessageBox.question(
            self, 'Remove', f"Remove '{name}' from this recipe?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            old_qty = float(row_dict.get('QuantityRaw', 0) or 0)
        except (TypeError, ValueError):
            old_qty = 0.0
        sort_order = row_dict.get('SortOrder')
        self.undo_stack.push(RemoveComponentCommand(
            self.recipe_id, row_dict['Type'], row_dict['Id'], old_qty, name,
            sort_order=sort_order,
        ))

    def _on_components_reordered(self, before, after):
        '''Model fired this when the user dropped a row at a new position.
        Push it through the undo stack so the DB rewrite is reversible.'''
        if before == after:
            return
        self.undo_stack.push(ReorderComponentsCommand(self.recipe_id, before, after))

    def _on_nutrition_label(self):
        NutritionLabelDialog(self.recipe_id, parent=self).exec()

    def _on_price_history(self):
        dlg = PriceHistoryDialog(self.recipe_id, self.name_edit.text(), recipe_mode=True, parent=self)
        dlg.exec()

    def _on_delete(self):
        name = self.name_edit.text()
        if QMessageBox.question(
            self, 'Delete', f'Delete {name}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_recipe(self.recipe_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Recipe In Use', str(exc))
            return
        self.modified = True
        self.status_message = f"Deleted '{name}'"
        # Flag so close_requested() skips the cost-snapshot stamp
        # (the recipe row is already gone from the DB).
        self._being_deleted = True
        self.recipeDeleted.emit(self.recipe_id)


class RecipeEditDialog(QDialog):
    '''Thin modal wrapper around RecipeEditWidget. Kept for callers
    already in a modal context (the Ingredient editor's "Used in
    recipes" link opens a recipe from inside its own dialog, where a
    tabbed editor on the Recipes place can't be reached without
    closing the ingredient dialog first).'''

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.widget = RecipeEditWidget(recipe_id, parent=self)
        self.setWindowTitle(f"{config.APPNAME} | {self.widget.title()}")
        self.resize(1200, 760)
        self.widget.titleChanged.connect(
            lambda name: self.setWindowTitle(f"{config.APPNAME} | {name}")
        )
        self.widget.recipeDeleted.connect(lambda _id: self.accept())

        close_btn = QPushButton('Close')
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.widget, stretch=1)
        layout.addLayout(btn_row)

    # Property passthroughs for callers (main_window) that read these
    # after exec() to decide whether to refresh or flash a status toast.
    @property
    def recipe_id(self):
        return self.widget.recipe_id

    @property
    def modified(self):
        return self.widget.modified

    @property
    def status_message(self):
        return self.widget.status_message

    def done(self, result):
        self.widget.close_requested()
        super().done(result)


def _parse_menu_price(text):
    '''Accept blank / '-' / '$3.42' / '13.95' etc. Returns float or None;
    raises ValueError on anything else so the caller can refuse the edit.'''
    s = (text or '').strip().lstrip('$').strip()
    if not s or s == '-' or s == '—':
        return None
    return float(s)


def _format_menu_price(value):
    '''Inverse of _parse_menu_price for display.'''
    if value is None or value == '':
        return ''
    try:
        return '${:.2f}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _coerce_menu_price(value):
    '''DB → in-memory. None stays None; everything else becomes a float.'''
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _prices_changed_html(cost_raw, cost_snapshot):
    '''"+$0.19 vs saved" chip when the recipe's current cost has drifted
    from the snapshot the user last confirmed. Returns '' when either
    value is missing or the drift is under a penny (ignored jitter).'''
    try:
        cost = float(cost_raw) if cost_raw is not None else None
        snap = float(cost_snapshot) if cost_snapshot is not None else None
    except (TypeError, ValueError):
        return ''
    if cost is None or snap is None:
        return ''
    delta = cost - snap
    if abs(delta) < 0.01:
        return ''
    sign = '+' if delta > 0 else '−'
    # Up is bad (we're paying more); use the same amber tone as a food
    # cost that's gone over target. Down is good — mute green.
    bg, fg = ('#FBEADB', '#8A3F0C') if delta > 0 else ('#E6EFE3', '#24502A')
    return (
        f'<span style="color: {fg}; background: {bg}; padding: 0 5px;'
        f' border-radius: 4px; font-weight: 600">'
        f'{sign}${abs(delta):.2f} vs saved</span>'
    )


def _food_cost_html(cost_raw, menu_price):
    '''Return the HTML fragment for the info-strip's food-cost field, or
    '' when there isn't enough data to compute it. Amber-tints the value
    when it exceeds the user's target (QSettings food_cost/target_pct,
    default 28%). The user sets a food-cost target because a recipe
    whose cost takes too much of its menu price doesn't make money.'''
    try:
        cost = float(cost_raw) if cost_raw is not None else 0.0
        price = float(menu_price) if menu_price not in (None, '') else 0.0
    except (TypeError, ValueError):
        return ''
    if price <= 0 or cost <= 0:
        return ''
    pct = cost / price
    target = QSettings().value('food_cost/target_pct', _DEFAULT_FOOD_COST_TARGET, type=float)
    pct_label = f'{pct * 100:.1f}%'
    price_label = '${:.2f}'.format(price)
    if pct > target:
        return (
            f'<b>Food cost</b> <span style="color: #8A3F0C; background: #FBEADB;'
            f' padding: 0 5px; border-radius: 4px">{pct_label}</span> of {price_label}'
        )
    return f'<b>Food cost</b> {pct_label} of {price_label}'
