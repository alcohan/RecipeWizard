from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QTableView, QTabWidget,
    QVBoxLayout, QWidget,
)

import config
import db
import setup
from gui.dialogs.about import AboutDialog
from gui.dialogs.bulk_image_assign import BulkImageAssignDialog
from gui.dialogs.ingredient_create import IngredientCreateDialog
from gui.dialogs.ingredient_create_from_usda import IngredientCreateFromUsdaDialog
from gui.dialogs.ingredient_edit import IngredientEditDialog
from gui.dialogs.recipe_create import RecipeCreateDialog
from gui.dialogs.recipe_edit import RecipeEditDialog
from gui.dialogs.suppliers_manager import SuppliersManagerDialog
from gui.dialogs.tags_manager import TagsManagerDialog
from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.models.ingredients_model import IngredientsModel
from gui.models.recipes_model import RecipesModel
from gui.tabs.home_tab import HomeTab


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

    def focus_filter(self):
        '''Called by the global Ctrl+F shortcut when this pane's tab is active.'''
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()

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
        self.resize(1100, 760)
        self._build_menus()
        self._build_tabs()

    def _build_tabs(self):
        '''Top-level navigation. To add a tab later, write a `_xxx_tab()`
        method that returns a QWidget and add one `addTab(...)` line below.'''
        self.ingredients_model = IngredientsModel(self)
        self.recipes_model = RecipesModel(self)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._home_tab(), 'Home')
        self.tabs.addTab(self._ingredients_tab(), 'Ingredients')
        self.tabs.addTab(self._recipes_tab(), 'Recipes')
        self.setCentralWidget(self.tabs)

        # Ctrl+F focuses whichever tab's filter is active.
        find_shortcut = QShortcut(QKeySequence.Find, self)
        find_shortcut.activated.connect(self._focus_active_filter)

        self.statusBar().showMessage('Ready')

    def _focus_active_filter(self):
        tab = self.tabs.currentWidget()
        focus = getattr(tab, 'focus_filter', None)
        if callable(focus):
            focus()

    def _home_tab(self):
        tab = HomeTab(self.ingredients_model, self.recipes_model)
        tab.recipeClicked.connect(self._on_recipe_edit_by_id)
        return tab

    def _ingredients_tab(self):
        new_search_btn = QPushButton('New (Search Database)')
        new_search_btn.clicked.connect(self._on_new_ingredient_search)
        new_blank_btn = QPushButton('New From Blank')
        new_blank_btn.clicked.connect(self._on_new_ingredient_blank)
        pane = _BrowsePane(
            placeholder='\U0001F50D  Filter ingredients…',
            source_model=self.ingredients_model,
            action_buttons=[new_search_btn, new_blank_btn],
            context_actions=[
                ('Edit…', self._on_ingredient_edit),
                ('Delete', self._on_ingredient_delete),
            ],
        )
        pane.rowActivated.connect(self._on_ingredient_edit)
        return pane

    def _recipes_tab(self):
        new_recipe_btn = QPushButton('New Recipe')
        new_recipe_btn.clicked.connect(self._on_new_recipe)
        pane = _BrowsePane(
            placeholder='\U0001F50D  Filter recipes…',
            source_model=self.recipes_model,
            action_buttons=[new_recipe_btn],
            context_actions=[
                ('Edit…', self._on_recipe_edit),
                ('Delete', self._on_recipe_delete),
            ],
        )
        pane.rowActivated.connect(self._on_recipe_edit)
        return pane

    def _build_menus(self):
        bar = self.menuBar()

        file_menu = bar.addMenu('&File')
        new_recipe_action = file_menu.addAction('&New Recipe', self._on_new_recipe)
        new_recipe_action.setShortcut(QKeySequence.New)
        new_ingredient_action = file_menu.addAction('New &Ingredient', self._on_new_ingredient_blank)
        new_ingredient_action.setShortcut('Ctrl+Shift+N')
        file_menu.addSeparator()
        file_menu.addAction('&Import from CSV', self._on_import_csv)
        file_menu.addAction('&Export to CSV', self._on_export_csv)
        file_menu.addSeparator()
        file_menu.addAction('E&xit', self.close)

        manage_menu = bar.addMenu('&Manage')
        manage_menu.addAction('&Suppliers', self._on_suppliers)
        manage_menu.addAction('&Tags', self._on_tags)

        tools_menu = bar.addMenu('&Tools')
        refresh_action = tools_menu.addAction('&Refresh', self.refresh)
        refresh_action.setShortcut('F5')
        tools_menu.addAction('Reset Database', self._on_reset_clean)
        tools_menu.addAction('Reset With Sample Data', self._on_reset_sample)
        tools_menu.addSeparator()
        tools_menu.addAction('Auto-assign Images', self._on_auto_assign_images)
        tools_menu.addAction('Bulk Assign Images', self._on_bulk_assign_images)

        help_menu = bar.addMenu('&Help')
        help_menu.addAction('&About', self._on_about)

    # --- refresh ---

    def refresh(self):
        self.ingredients_model.refresh()
        self.recipes_model.refresh()
        self.statusBar().showMessage('Refreshed', 2000)

    # --- ingredient / recipe handlers ---

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
        self._on_recipe_edit_by_id(self.recipes_model.id_at_row(src_row))

    def _on_recipe_edit_by_id(self, recipe_id):
        '''Open the recipe edit dialog by recipe id (not row). Lets the home
        tab gallery dispatch directly without round-tripping through a model
        row index.'''
        dlg = RecipeEditDialog(recipe_id, parent=self)
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

    def _on_bulk_assign_images(self):
        BulkImageAssignDialog(parent=self).exec()
        self.refresh()

    def _on_suppliers(self):
        SuppliersManagerDialog(parent=self).exec()
        # Suppliers don't affect the ingredient/recipe browse lists directly,
        # but a refresh is cheap and keeps the model consistent if anything
        # downstream (like price-history dialogs) re-reads.
        self.refresh()

    def _on_tags(self):
        TagsManagerDialog(parent=self).exec()
        self.refresh()

    def _on_about(self):
        AboutDialog(parent=self).exec()
