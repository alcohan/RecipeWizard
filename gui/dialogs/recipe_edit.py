'''Recipe edit dialog with QUndoStack-backed editing.

All mutations (rename, yield change, add/remove/change-qty of components,
tag toggles) are pushed through the dialog's QUndoStack so they can be
reversed with Ctrl+Z. QUndoStack.indexChanged drives the refresh that
re-reads RecipesWithNutrition, redraws the wedge, and re-syncs the
editable demographic fields.

Layout: three columns separated by a QSplitter.
  Left:    demographic + Update button, tag grid, components table, action row
  Middle:  read-only info / nutrition / contains panels
  Right:   wedge preview'''
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QDoubleValidator, QKeySequence, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
    QTableView, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.nutrition_label import NutritionLabelDialog
from gui.dialogs.price_history import PriceHistoryDialog
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.dialogs.recipe_component_edit import RecipeComponentEditDialog
from gui.models.components_model import RecipeComponentsModel
from gui.undo.recipe_commands import (
    AddComponentCommand, RemoveComponentCommand, SetComponentQtyCommand,
    ToggleTagCommand, UpdateRecipeInfoCommand,
)
from gui.widgets.tag_checkbox_grid import TagCheckboxGrid
from gui.widgets.wedge_view import WedgeView


WEDGE_SIZE = 220
INFO_FIELDS = (('Weight', 'Weight (g)'), ('Cost', 'Cost'), ('Components', 'Components'))


class RecipeEditDialog(QDialog):
    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.modified = False

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._refresh)

        recipe = db.recipe_info(recipe_id)
        self.setWindowTitle(f"{config.APPNAME} | {recipe['Name']}")
        self.resize(1200, 760)

        self._recipe_snapshot = self._snapshot(recipe)
        self.components_model = RecipeComponentsModel(recipe_id)

        left_col = self._build_left(recipe)
        middle_col = self._build_middle(recipe)
        right_col = self._build_right()

        # Undo/Redo actions — keyboard shortcuts only, no toolbar buttons.
        undo_action = self.undo_stack.createUndoAction(self, 'Undo')
        undo_action.setShortcut(QKeySequence.Undo)
        redo_action = self.undo_stack.createRedoAction(self, 'Redo')
        redo_action.setShortcut(QKeySequence.Redo)
        self.addAction(undo_action)
        self.addAction(redo_action)

        button_box = QDialogButtonBox()
        delete_btn = button_box.addButton('Delete Recipe', QDialogButtonBox.DestructiveRole)
        delete_btn.setStyleSheet('background-color: #c0392b; color: white; padding: 4px 10px;')
        close_btn = button_box.addButton('Close', QDialogButtonBox.RejectRole)
        delete_btn.clicked.connect(self._on_delete)
        close_btn.clicked.connect(self.reject)
        for btn in button_box.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(left_col)
        self.splitter.addWidget(middle_col)
        self.splitter.addWidget(right_col)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setStretchFactor(2, 1)

        layout = QVBoxLayout(self)
        layout.addWidget(self.splitter, stretch=1)
        layout.addWidget(button_box)

        # Restore splitter ratios from the previous session if we have them.
        settings = QSettings()
        state = settings.value('recipeEditDialog/splitter')
        if state is not None:
            self.splitter.restoreState(state)

        self._refresh()

    def done(self, result):
        QSettings().setValue('recipeEditDialog/splitter', self.splitter.saveState())
        super().done(result)

    # --- layout builders ---

    def _build_left(self, recipe):
        # Demographic
        demo_box = QGroupBox('Recipe')
        self.name_edit = QLineEdit(recipe['Name'])
        self.unit_edit = QLineEdit(recipe['Unit'])
        self.yield_edit = QLineEdit(str(recipe['OutputQty']))
        self.yield_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        update_btn = QPushButton('Update')
        update_btn.clicked.connect(self._on_update_info)

        demo_form = QFormLayout()
        demo_form.addRow('Name', self.name_edit)
        demo_form.addRow('Yield Unit', self.unit_edit)
        demo_form.addRow('Recipe Yield', self.yield_edit)

        demo_row = QHBoxLayout()
        demo_row.addLayout(demo_form, stretch=1)
        demo_row.addWidget(update_btn, alignment=Qt.AlignBottom)
        demo_layout = QVBoxLayout(demo_box)
        demo_layout.addLayout(demo_row)

        # Tags
        self.tag_grid = TagCheckboxGrid(recipe_id=self.recipe_id)
        self.tag_grid.toggled.connect(self._on_tag_toggle)

        # Components table
        comp_box = QGroupBox('Components')
        self.components_table = QTableView()
        self.components_table.setModel(self.components_model)
        self.components_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.components_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.components_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.components_table.verticalHeader().setVisible(False)
        self.components_table.horizontalHeader().setStretchLastSection(True)
        self.components_table.activated.connect(self._on_component_activated)
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

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.addWidget(demo_box)
        layout.addWidget(self.tag_grid)
        layout.addWidget(comp_box, stretch=1)
        layout.addLayout(action_row)
        return wrap

    def _build_middle(self, recipe):
        unit = recipe['Unit']

        self.info_box = QGroupBox(f'Info (per {unit})')
        self.info_labels = {}
        info_form = QFormLayout(self.info_box)
        for key, label_text in INFO_FIELDS:
            lbl = QLabel('')
            info_form.addRow(label_text, lbl)
            self.info_labels[key] = lbl

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
        layout.addWidget(self.info_box)
        layout.addWidget(self.nutrition_box)
        layout.addWidget(contains_box)
        layout.addStretch()
        return wrap

    def _build_right(self):
        preview_box = QGroupBox('Preview')
        self.wedge = WedgeView(self.recipe_id, size=WEDGE_SIZE)
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.addWidget(self.wedge, alignment=Qt.AlignCenter)
        preview_layout.addStretch()
        return preview_box

    # --- helpers ---

    def _snapshot(self, recipe):
        return (recipe['Name'], recipe['Unit'], float(recipe['OutputQty']))

    def _refresh(self):
        '''Re-read recipe state from DB and update every dependent view.
        Fires on every QUndoStack.indexChanged plus on dialog construction.'''
        self.modified = True
        recipe = db.recipe_info(self.recipe_id)
        self._recipe_snapshot = self._snapshot(recipe)

        self.components_model.refresh()

        for key, lbl in self.info_labels.items():
            value = recipe.get(key)
            lbl.setText('' if value is None else str(value))
        for key, lbl in self.nutrition_labels.items():
            value = recipe.get(key)
            lbl.setText('' if value is None else str(value))

        allergens = db.get_recipe_allergens(self.recipe_id)
        self.allergens_label.setText(', '.join(allergens) or '(none)')

        self.wedge.refresh()

        # Group-box titles depend on the unit; rebuild on rename.
        self.info_box.setTitle(f"Info (per {recipe['Unit']})")
        self.nutrition_box.setTitle(f"Nutrition (per {recipe['Unit']})")

        # Sync editable demographic fields. Uncommitted typed-but-not-Updated
        # values will be lost here — that's an acceptable tradeoff for keeping
        # the form visibly in sync after an undo.
        for edit, value in (
            (self.name_edit, recipe['Name']),
            (self.unit_edit, recipe['Unit']),
            (self.yield_edit, str(recipe['OutputQty'])),
        ):
            edit.blockSignals(True)
            if edit.text() != value:
                edit.setText(value)
            edit.blockSignals(False)

        # Sync tag checkboxes (so undoing a tag toggle visually reverts)
        for tag_row in db.get_recipe_tags(self.recipe_id):
            self.tag_grid.set_checked(tag_row['id'], bool(tag_row['checked']))

        self.setWindowTitle(f"{config.APPNAME} | {recipe['Name']}")

    # --- handlers ---

    def _on_update_info(self):
        name = self.name_edit.text().strip()
        unit = self.unit_edit.text()
        try:
            yield_qty = float(self.yield_edit.text() or 0)
        except ValueError:
            QMessageBox.warning(self, 'Invalid', 'Recipe Yield must be numeric.')
            return
        after = (name, unit, yield_qty)
        if after == self._recipe_snapshot:
            return  # nothing to push
        self.undo_stack.push(UpdateRecipeInfoCommand(self.recipe_id, self._recipe_snapshot, after))

    def _on_tag_toggle(self, tag_id, tag_name, state):
        self.undo_stack.push(ToggleTagCommand(self.recipe_id, tag_id, state, tag_name))

    def _on_add_component(self):
        dlg = RecipeComponentAddDialog(self.recipe_id, self.name_edit.text(), parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.selected:
            return
        child_id, mode, name, _unit = dlg.selected
        self.undo_stack.push(AddComponentCommand(self.recipe_id, mode, child_id, dlg.qty, name))

    def _on_component_activated(self, view_index):
        if not view_index.isValid():
            return
        component = self.components_model.row_dict(view_index.row())
        dlg = RecipeComponentEditDialog(self.name_edit.text(), component, parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        mode = component['Type']
        child_id = component['Id']
        name = component['Name']
        try:
            old_qty = float(component['Quantity'])
        except (TypeError, ValueError):
            old_qty = 0.0
        if dlg.result_action == 'update':
            if dlg.new_qty == old_qty:
                return
            self.undo_stack.push(SetComponentQtyCommand(
                self.recipe_id, mode, child_id, old_qty, dlg.new_qty, name,
            ))
        elif dlg.result_action == 'delete':
            self.undo_stack.push(RemoveComponentCommand(
                self.recipe_id, mode, child_id, old_qty, name,
            ))

    def _on_nutrition_label(self):
        NutritionLabelDialog(self.recipe_id, parent=self).exec()

    def _on_price_history(self):
        dlg = PriceHistoryDialog(self.recipe_id, self.name_edit.text(), recipe_mode=True, parent=self)
        dlg.exec()

    def _on_delete(self):
        if QMessageBox.question(
            self, 'Delete', f'Delete {self.name_edit.text()}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_recipe(self.recipe_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Recipe In Use', str(exc))
            return
        self.modified = True
        self.accept()
