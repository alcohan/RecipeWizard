import datetime
import os
import shutil

from PySide6.QtCore import Qt, QSettings, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QPushButton, QTableView, QTabWidget,
    QVBoxLayout, QWidget,
)

import api.usda
import config
import db
import setup
from gui.dialogs.about import AboutDialog
from gui.dialogs.bulk_image_assign import BulkImageAssignDialog
from gui.dialogs.ingredient_create import IngredientCreateDialog
from gui.dialogs.ingredient_create_from_usda import IngredientCreateFromUsdaDialog
from gui.dialogs.ingredient_edit import IngredientEditDialog
from gui.dialogs.preferences import PreferencesDialog
from gui.dialogs.recipe_create import RecipeCreateDialog
from gui.dialogs.recipe_edit import RecipeEditDialog
from gui.dialogs.suppliers_manager import SuppliersManagerDialog
from gui.dialogs.tags_manager import IngredientTagsDialog, RecipeTemplatesDialog
from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.models.ingredients_model import IngredientsModel
from gui.models.recipes_model import RecipesModel
from gui.tabs.home_tab import HomeTab
from gui.widgets.tag_badge import TagBadgeCellDelegate


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
        # Push the user's saved USDA API key into the API client before any
        # USDA-dependent dialog can open. Empty string = use DEMO_KEY fallback.
        api.usda.set_api_key(QSettings().value('usda/apiKey', '', type=str))
        self._build_menus()
        self._build_tabs()
        self._restore_state()

    def _restore_state(self):
        '''Restore window geometry and last-active tab from QSettings.
        First launch has no settings — resize() above is the default.'''
        settings = QSettings()
        geom = settings.value('mainWindow/geometry')
        if geom is not None:
            self.restoreGeometry(geom)
        state = settings.value('mainWindow/state')
        if state is not None:
            self.restoreState(state)
        last_tab = settings.value('mainWindow/currentTab', 0)
        try:
            idx = int(last_tab)
        except (TypeError, ValueError):
            idx = 0
        if 0 <= idx < self.tabs.count():
            self.tabs.setCurrentIndex(idx)

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('mainWindow/geometry', self.saveGeometry())
        settings.setValue('mainWindow/state', self.saveState())
        settings.setValue('mainWindow/currentTab', self.tabs.currentIndex())
        super().closeEvent(event)

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
        # Paint the Tag column as a colored pill badge.
        tag_col = self.ingredients_model.COLUMNS.index('Tag')
        pane.table.setItemDelegateForColumn(tag_col, TagBadgeCellDelegate(pane.table))
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
        # MenuRole.PreferencesRole tells Qt to relocate this to the native
        # app-menu Preferences slot on macOS; on Windows/Linux it stays here.
        prefs_action = file_menu.addAction('&Preferences…', self._on_preferences)
        prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        file_menu.addSeparator()
        file_menu.addAction('E&xit', self.close)

        manage_menu = bar.addMenu('&Manage')
        manage_menu.addAction('&Suppliers', self._on_suppliers)
        manage_menu.addAction('Ingredient &Tags', self._on_ingredient_tags)
        manage_menu.addAction('Recipe Tem&plates', self._on_recipe_templates)

        view_menu = bar.addMenu('&View')
        refresh_action = view_menu.addAction('&Refresh', self.refresh)
        refresh_action.setShortcut('F5')

        tools_menu = bar.addMenu('&Tools')
        tools_menu.addAction('&Auto-assign Images', self._on_auto_assign_images)
        tools_menu.addAction('&Bulk Assign Images…', self._on_bulk_assign_images)
        tools_menu.addSeparator()
        tools_menu.addAction('&Open Data Folder', self._on_open_data_folder)
        tools_menu.addAction('Back&up Database…', self._on_backup_database)
        tools_menu.addAction('&Restore Database…', self._on_restore_database)
        tools_menu.addSeparator()
        # Destructive ops live at the bottom so they're physically farther
        # from common actions and harder to hit by accident.
        tools_menu.addAction('Reset &Database…', self._on_reset_clean)
        tools_menu.addAction('Reset With &Sample Data…', self._on_reset_sample)

        help_menu = bar.addMenu('&Help')
        help_menu.addAction('&About', self._on_about)

    # --- refresh ---

    def refresh(self):
        self.ingredients_model.refresh()
        self.recipes_model.refresh()
        self.statusBar().showMessage('Refreshed', 2000)

    # --- ingredient / recipe handlers ---

    def _flash_status(self, msg):
        '''Show a toast in the status bar for ~3s. Centralized so handlers
        all use the same dwell time.'''
        if msg:
            self.statusBar().showMessage(msg, 3000)

    def _on_ingredient_edit(self, src_row):
        ing_id = self.ingredients_model.id_at_row(src_row)
        dlg = IngredientEditDialog(ing_id, parent=self)
        dlg.exec()
        if dlg.modified:
            self.refresh()
        self._flash_status(dlg.status_message)

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
        self._flash_status(f"Deleted '{row['Name']}'")

    def _on_new_ingredient_search(self):
        dlg = IngredientCreateFromUsdaDialog(parent=self)
        if dlg.exec() != QDialog.Accepted or not dlg.new_id:
            return
        edit_dlg = IngredientEditDialog(dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()
        # Edit-stage message wins (most recent action), else fall back to "Created"
        self._flash_status(edit_dlg.status_message or dlg.status_message)

    def _on_new_ingredient_blank(self):
        create_dlg = IngredientCreateDialog(parent=self)
        if create_dlg.exec() != QDialog.Accepted or not create_dlg.new_id:
            return
        edit_dlg = IngredientEditDialog(create_dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()
        self._flash_status(edit_dlg.status_message or create_dlg.status_message)

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
        self._flash_status(dlg.status_message)

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
        self._flash_status(f"Deleted '{row['Name']}'")

    def _on_new_recipe(self):
        create_dlg = RecipeCreateDialog(parent=self)
        if create_dlg.exec() != QDialog.Accepted or not create_dlg.new_id:
            return
        edit_dlg = RecipeEditDialog(create_dlg.new_id, parent=self)
        edit_dlg.exec()
        self.refresh()
        self._flash_status(edit_dlg.status_message or create_dlg.status_message)

    # --- functional handlers wired to existing business layer ---

    def _on_open_data_folder(self):
        '''Reveal the per-user data directory (DB + ingredient images) in
        the system file browser. Useful for manual backups or for dropping
        ingredient image files in by hand.'''
        QDesktopServices.openUrl(QUrl.fromLocalFile(config.user_data_dir()))

    def _on_backup_database(self):
        default_name = f'RecipeWizard_backup_{datetime.date.today().isoformat()}.db'
        path, _ = QFileDialog.getSaveFileName(
            self, 'Backup Database', default_name, 'SQLite Database (*.db)',
        )
        if not path:
            return
        try:
            shutil.copy(config.DATABASE, path)
        except OSError as exc:
            QMessageBox.critical(self, 'Backup Failed', str(exc))
            return
        self._flash_status(f'Backed up to {path}')

    def _on_restore_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Restore Database', '', 'SQLite Database (*.db);;All Files (*)',
        )
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(config.DATABASE):
            QMessageBox.warning(
                self, 'Restore Database',
                "That's the current database — pick a different backup file.",
            )
            return
        confirm = QMessageBox.warning(
            self, 'Restore Database',
            f'This will REPLACE your current data with the contents of:'
            f'\n\n{path}\n\nContinue?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            shutil.copy(path, config.DATABASE)
            # Older backups may predate later schema migrations; bring them
            # up to date before any query can hit a missing column.
            setup.migrateDB()
        except Exception as exc:
            QMessageBox.critical(self, 'Restore Failed', str(exc))
            return
        self.refresh()
        self._flash_status(f'Restored from {os.path.basename(path)}')

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
        self._flash_status('Database reset')

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
        self._flash_status('Sample data loaded')

    def _on_auto_assign_images(self):
        counts = setup.auto_assign_images()
        QMessageBox.information(
            self, 'Auto-assign Images',
            f"Assigned: {counts['assigned']}\n"
            f"Ambiguous (skipped): {counts['ambiguous']}\n"
            f"No match: {counts['unmatched']}",
        )
        self.refresh()
        self._flash_status(f"Auto-assigned {counts['assigned']} image(s)")

    def _on_bulk_assign_images(self):
        BulkImageAssignDialog(parent=self).exec()
        self.refresh()

    def _on_suppliers(self):
        SuppliersManagerDialog(parent=self).exec()
        # Suppliers don't affect the ingredient/recipe browse lists directly,
        # but a refresh is cheap and keeps the model consistent if anything
        # downstream (like price-history dialogs) re-reads.
        self.refresh()

    def _on_ingredient_tags(self):
        IngredientTagsDialog(parent=self).exec()
        self.refresh()

    def _on_recipe_templates(self):
        RecipeTemplatesDialog(parent=self).exec()
        # Templates affect what wedges and badges show, so a refresh sweeps
        # any edits (e.g. shape changes) back into the home gallery.
        self.refresh()

    def _on_about(self):
        AboutDialog(parent=self).exec()

    def _on_preferences(self):
        PreferencesDialog(parent=self).exec()
