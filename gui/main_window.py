from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QTableView,
    QVBoxLayout, QWidget,
)

import config
import db
import setup
from gui.dialogs.ingredient_create import IngredientCreateDialog
from gui.dialogs.ingredient_create_from_usda import IngredientCreateFromUsdaDialog
from gui.dialogs.ingredient_edit import IngredientEditDialog
from gui.dialogs.recipe_create import RecipeCreateDialog
from gui.dialogs.recipe_edit import RecipeEditDialog
from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.models.ingredients_model import IngredientsModel
from gui.models.recipes_model import RecipesModel


class _BrowsePane(QWidget):
    '''Filter line + virtualized table + action-button row. Emits source-row
    indices via signals so the parent can map them back to DB ids.'''

    rowActivated = Signal(int)

    def __init__(self, placeholder, source_model, action_buttons, context_actions, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions

        self.proxy = MultiColumnFilterProxy(self)
        self.proxy.setSourceModel(self.source_model)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(placeholder)
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self.proxy.setFilterText)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # Fixed row height → Qt skips per-row measurement, which is what makes
        # large lists scroll smoothly. Equivalent to setUniformItemSizes on QListView.
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.activated.connect(self._on_activated)

        # Resize columns whenever the model resets (refresh, filter clear, etc.)
        self.source_model.modelReset.connect(self.table.resizeColumnsToContents)
        self.table.resizeColumnsToContents()

        button_row = QHBoxLayout()
        for btn in action_buttons:
            button_row.addWidget(btn)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.filter_edit)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(button_row)

    def _on_activated(self, view_index):
        if not view_index.isValid():
            return
        self.rowActivated.emit(self.proxy.mapToSource(view_index).row())

    def _show_context_menu(self, point):
        view_index = self.table.indexAt(point)
        if not view_index.isValid():
            return
        src_row = self.proxy.mapToSource(view_index).row()
        menu = QMenu(self.table)
        for label, handler in self._context_actions:
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, r=src_row, h=handler: h(r))
        menu.exec(self.table.viewport().mapToGlobal(point))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APPNAME)
        self.resize(1000, 720)
        self._build_menus()
        self._build_panes()

    def _build_panes(self):
        self.ingredients_model = IngredientsModel(self)
        self.recipes_model = RecipesModel(self)

        new_search_btn = QPushButton('New (Search Database)')
        new_search_btn.clicked.connect(self._on_new_ingredient_search)
        new_blank_btn = QPushButton('New From Blank')
        new_blank_btn.clicked.connect(self._on_new_ingredient_blank)
        self.ingredients_pane = _BrowsePane(
            placeholder='\U0001F50D  Filter ingredients…',
            source_model=self.ingredients_model,
            action_buttons=[new_search_btn, new_blank_btn],
            context_actions=[
                ('Edit…', self._on_ingredient_edit),
                ('Delete', self._on_ingredient_delete),
            ],
        )
        self.ingredients_pane.rowActivated.connect(self._on_ingredient_edit)

        new_recipe_btn = QPushButton('New Recipe')
        new_recipe_btn.clicked.connect(self._on_new_recipe)
        self.recipes_pane = _BrowsePane(
            placeholder='\U0001F50D  Filter recipes…',
            source_model=self.recipes_model,
            action_buttons=[new_recipe_btn],
            context_actions=[
                ('Edit…', self._on_recipe_edit),
                ('Delete', self._on_recipe_delete),
            ],
        )
        self.recipes_pane.rowActivated.connect(self._on_recipe_edit)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.ingredients_pane)
        splitter.addWidget(self.recipes_pane)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

        self.statusBar().showMessage('Ready')

    def _build_menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu('&File')
        file_menu.addAction('&Import from CSV', self._on_import_csv)
        file_menu.addAction('&Export to CSV', self._on_export_csv)
        file_menu.addSeparator()
        file_menu.addAction('E&xit', self.close)

        manage_menu = bar.addMenu('&Manage')
        manage_menu.addAction('&Suppliers', lambda: self._stub_log('Suppliers', phase=4))
        manage_menu.addAction('&Tags', lambda: self._stub_log('Tags', phase=4))

        tools_menu = bar.addMenu('&Tools')
        refresh_action = tools_menu.addAction('&Refresh', self.refresh)
        refresh_action.setShortcut('F5')
        tools_menu.addAction('Reset Database', self._on_reset_clean)
        tools_menu.addAction('Reset With Sample Data', self._on_reset_sample)
        tools_menu.addSeparator()
        tools_menu.addAction('Auto-assign Images', self._on_auto_assign_images)
        tools_menu.addAction('Bulk Assign Images', lambda: self._stub_log('Bulk Assign Images', phase=4))

        help_menu = bar.addMenu('&Help')
        help_menu.addAction('&About', lambda: self._stub_log('About', phase=4))

    # --- refresh ---

    def refresh(self):
        self.ingredients_model.refresh()
        self.recipes_model.refresh()
        self.statusBar().showMessage('Refreshed', 2000)

    # --- stub handlers (filled in by later phases) ---

    def _stub_log(self, name, phase):
        print(f'[stub] {name} — Phase {phase} will implement this')

    def _on_ingredient_edit(self, src_row):
        ing_id = self.ingredients_model.id_at_row(src_row)
        dlg = IngredientEditDialog(ing_id, parent=self)
        dlg.exec()
        if dlg.modified:
            self.refresh()

    def _on_ingredient_delete(self, src_row):
        row = self.ingredients_model.row_dict(src_row)
        if QMessageBox.question(
            self, 'Delete', f"Delete {row['Name']}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_ingredient(row['Id'])
        except Exception as exc:
            QMessageBox.warning(self, 'Ingredient In Use', str(exc))
            return
        self.refresh()

    def _on_new_ingredient_search(self):
        dlg = IngredientCreateFromUsdaDialog(parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.new_id:
            return
        edit_dlg = IngredientEditDialog(dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()

    def _on_new_ingredient_blank(self):
        create_dlg = IngredientCreateDialog(parent=self)
        if create_dlg.exec() != QDialog.Accepted or not create_dlg.new_id:
            return
        edit_dlg = IngredientEditDialog(create_dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()

    def _on_recipe_edit(self, src_row):
        rec_id = self.recipes_model.id_at_row(src_row)
        dlg = RecipeEditDialog(rec_id, parent=self)
        dlg.exec()
        if dlg.modified:
            self.refresh()

    def _on_recipe_delete(self, src_row):
        row = self.recipes_model.row_dict(src_row)
        if QMessageBox.question(
            self, 'Delete', f"Delete {row['Name']}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_recipe(row['Id'])
        except Exception as exc:
            QMessageBox.warning(self, 'Recipe In Use', str(exc))
            return
        self.refresh()

    def _on_new_recipe(self):
        create_dlg = RecipeCreateDialog(parent=self)
        if create_dlg.exec() != QDialog.Accepted or not create_dlg.new_id:
            return
        edit_dlg = RecipeEditDialog(create_dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()

    # --- functional handlers wired to existing business layer ---

    def _on_import_csv(self):
        confirm = QMessageBox.warning(
            self, 'Import from CSV',
            'This will ERASE all current data and reload from export/*.csv. Continue?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        from utilities import import_data_to_tables
        try:
            setup.initializeDB(includeSampleData=False)
            import_data_to_tables('builder.db')
            setup.auto_assign_images()
        except Exception as exc:
            QMessageBox.critical(self, 'Import Failed', str(exc))
            return
        self.refresh()
        self.statusBar().showMessage('Imported from CSV', 3000)

    def _on_export_csv(self):
        from utilities import export_tables_to_file
        try:
            export_tables_to_file('builder.db')
        except Exception as exc:
            QMessageBox.critical(self, 'Export Failed', str(exc))
            return
        self.statusBar().showMessage('Exported to export/*.csv', 3000)

    def _on_reset_clean(self):
        confirm = QMessageBox.warning(
            self, 'Reset Database',
            'Erase ALL data and start with an empty database?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        setup.initializeDB(includeSampleData=False)
        self.refresh()

    def _on_reset_sample(self):
        confirm = QMessageBox.warning(
            self, 'Reset With Sample Data',
            'Erase ALL data and reload from the bundled sample data?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        setup.initializeDB()
        setup.auto_assign_images()
        self.refresh()

    def _on_auto_assign_images(self):
        counts = setup.auto_assign_images()
        QMessageBox.information(
            self, 'Auto-assign Images',
            f"Assigned: {counts['assigned']}\n"
            f"Ambiguous (skipped): {counts['ambiguous']}\n"
            f"No match: {counts['unmatched']}",
        )
        self.refresh()
