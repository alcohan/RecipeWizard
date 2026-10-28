import datetime
import os
import shutil

from PySide6.QtCore import Qt, QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
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
from gui.dialogs.tags_manager import IngredientTagsDialog
from gui.dialogs.template_editor import TemplatesManagerDialog
from gui.models.ingredients_model import IngredientsModel
from gui.models.recipes_model import RecipesModel
from gui.tabs.analytics_tab import AnalyticsTab
from gui.tabs.ingredients_tab import IngredientsTab
from gui.tabs.library_health_tab import LibraryHealthTab
from gui.tabs.recipes_tab import RecipesTab
from gui.tabs.suppliers_tab import SuppliersTab
from gui.widgets.place_rail import PlaceRail
from gui.widgets.status_bar import RecipeWizardStatusBar


class MainWindow(QMainWindow):
    '''Shell: five places behind a left rail, with a custom status bar
    pinned at the bottom.

    The design is strict about the rail — exactly five slots, ⌘1-⌘5,
    labelled icons. Recipes is the landing place (no separate Home);
    Compare was previously the Analytics tab; Suppliers was previously
    a modal dialog; Library Health is new.'''

    _PLACES = ('recipes', 'ingredients', 'compare', 'suppliers', 'health')

    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APPNAME)
        self.resize(1200, 820)
        # Push the user's saved USDA API key into the API client before any
        # USDA-dependent dialog can open. Empty string = use DEMO_KEY fallback.
        api.usda.set_api_key(QSettings().value('usda/apiKey', '', type=str))
        self._build_menus()
        self._build_places()
        self._restore_state()

    def _restore_state(self):
        '''Restore window geometry and last-active place from QSettings.
        First launch has no settings — resize() above is the default.'''
        settings = QSettings()
        geom = settings.value('mainWindow/geometry')
        if geom is not None:
            self.restoreGeometry(geom)
        state = settings.value('mainWindow/state')
        if state is not None:
            self.restoreState(state)
        last_place = settings.value('mainWindow/currentPlace', 0)
        try:
            idx = int(last_place)
        except (TypeError, ValueError):
            idx = 0
        if 0 <= idx < self.stack.count():
            self.rail.set_current(idx)
            self.stack.setCurrentIndex(idx)

    def closeEvent(self, event):
        settings = QSettings()
        settings.setValue('mainWindow/geometry', self.saveGeometry())
        settings.setValue('mainWindow/state', self.saveState())
        settings.setValue('mainWindow/currentPlace', self.rail.current())
        super().closeEvent(event)

    def _build_places(self):
        '''Rail + stacked workspace + status bar. One place per rail
        slot; indices are the order below. Model refs are stashed on
        self so handlers can call refresh() on them.'''
        self.ingredients_model = IngredientsModel(self)
        self.recipes_model = RecipesModel(self)

        self.rail = PlaceRail(self)
        self.stack = QStackedWidget()
        self.rail.placeChanged.connect(self.stack.setCurrentIndex)

        # Recipes = landing place. Promoted from the old Home tab.
        self.rail.add_place('Recipes', 'recipes')
        self.stack.addWidget(self._recipes_place())
        # Ingredients.
        self.rail.add_place('Ingredients', 'ingredients')
        self.stack.addWidget(self._ingredients_place())
        # Compare (the old Analytics tab — same spreadsheet view, same
        # category breakdowns; the "tray" scoping comes later).
        self.rail.add_place('Compare', 'compare')
        self.stack.addWidget(self._compare_place())
        # Suppliers (promoted from a modal to a place).
        self.rail.add_place('Suppliers', 'suppliers')
        self.stack.addWidget(self._suppliers_place())
        # Library Health pinned to the bottom of the rail.
        self.rail.add_spacer()
        self.rail.add_place('Health', 'health')
        self.library_health_tab = LibraryHealthTab()
        self.stack.addWidget(self.library_health_tab)

        self.rail.install_shortcuts(self)

        self.status_bar = RecipeWizardStatusBar()
        self.status_bar.compareTrayClicked.connect(
            lambda: self.rail.set_current(self._PLACES.index('compare'))
        )

        central = QWidget()
        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)
        inner.addWidget(self.rail)
        inner.addWidget(self.stack, stretch=1)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addLayout(inner, stretch=1)
        outer.addWidget(self.status_bar)
        self.setCentralWidget(central)

        # Keep the status bar + Library Health in sync with the models.
        for m in (self.ingredients_model, self.recipes_model):
            m.modelReset.connect(self.status_bar.refresh)
            m.modelReset.connect(self.library_health_tab.mark_stale)
        self.status_bar.refresh()

        # Ctrl+F focuses whichever place's filter is active.
        find_shortcut = QShortcut(QKeySequence.Find, self)
        find_shortcut.activated.connect(self._focus_active_filter)

    def _focus_active_filter(self):
        place = self.stack.currentWidget()
        focus = getattr(place, 'focus_filter', None)
        if callable(focus):
            focus()

    def _recipes_place(self):
        new_recipe_btn = QPushButton('+ New Recipe')
        new_recipe_btn.clicked.connect(self._on_new_recipe)
        new_ing_btn = QPushButton('+ New Ingredient')
        new_ing_btn.clicked.connect(self._on_new_ingredient_search)
        tab = RecipesTab(
            source_model=self.recipes_model,
            context_actions=[
                ('Edit…', self._on_recipe_edit),
                ('Delete', self._on_recipe_delete),
            ],
            action_buttons=[new_recipe_btn, new_ing_btn],
        )
        tab.rowActivated.connect(self._on_recipe_edit)
        return tab

    def _ingredients_place(self):
        new_search_btn = QPushButton('+ New (USDA Search)')
        new_search_btn.clicked.connect(self._on_new_ingredient_search)
        new_blank_btn = QPushButton('+ New (Blank)')
        new_blank_btn.clicked.connect(self._on_new_ingredient_blank)
        tab = IngredientsTab(
            source_model=self.ingredients_model,
            context_actions=[
                ('Edit…', self._on_ingredient_edit),
                ('Delete', self._on_ingredient_delete),
            ],
            action_buttons=[new_search_btn, new_blank_btn],
        )
        tab.rowActivated.connect(self._on_ingredient_edit)
        return tab

    def _compare_place(self):
        tab = AnalyticsTab(self.recipes_model)
        tab.recipeActivated.connect(self._on_recipe_edit_by_id)
        return tab

    def _suppliers_place(self):
        return SuppliersTab()

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

        # Suppliers has moved to the place rail (⌘4). Keep the two
        # tag-management entries under Manage until they get their own
        # place or get folded into a Settings dialog.
        manage_menu = bar.addMenu('&Manage')
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
        '''Reset both source models — model-reset signals propagate to
        each place, the custom status bar, and Library Health. No
        explicit "Refreshed" toast; the status bar's live counts are
        feedback enough.'''
        self.ingredients_model.refresh()
        self.recipes_model.refresh()

    # --- ingredient / recipe handlers ---

    def _flash_status(self, msg):
        '''No-op. Previously showed a transient Qt-statusBar toast, but
        the custom status bar doesn't carry transient messages; a
        future "status toast" slot can replace this. Kept as a no-op
        so handler code reads unchanged.'''
        pass

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

    def _on_ingredient_tags(self):
        IngredientTagsDialog(parent=self).exec()
        self.refresh()

    def _on_recipe_templates(self):
        TemplatesManagerDialog(parent=self).exec()
        # Templates affect what wedges and badges show, so a refresh sweeps
        # any edits (e.g. shape changes) back into the home gallery.
        self.refresh()

    def _on_about(self):
        AboutDialog(parent=self).exec()

    def _on_preferences(self):
        PreferencesDialog(parent=self).exec()
