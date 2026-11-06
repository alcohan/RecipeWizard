import os

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QMainWindow, QMessageBox,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

import api.usda
import config
import db
import setup
from utilities import backup
from gui.dialogs import backup_restore
from gui.dialogs.about import AboutDialog
from gui.dialogs.bulk_image_assign import BulkImageAssignDialog
from gui.dialogs.ingredient_edit import IngredientEditDialog
from gui.dialogs.ingredient_new import IngredientNewDialog
from gui.dialogs.ingredient_price_edit import IngredientPriceEditDialog
from gui.dialogs.import_purchases import run_import
from gui.dialogs.preferences import PreferencesPage
from gui.dialogs.recipe_create import RecipeCreateDialog
from gui.dialogs.update import UpdateDialog, install_update
from gui.dialogs.template_editor import TemplatesEditor, TemplatesManagerDialog
from gui.models.ingredients_model import IngredientsModel
from gui.printing.print_dialog import print_recipes
from gui.models.recipes_model import RecipesModel
from gui.tabs.analytics_tab import AnalyticsTab
from gui.dialogs.tags_manager import TagsPage
from gui.tabs.allergens_page import AllergensPage
from gui.tabs.configure_tab import ConfigureTab, LauncherPage
from gui.tabs.diets_page import DietsPage
from gui.tabs.ingredients_tab import IngredientsTab
from gui.tabs.library_health_tab import LibraryHealthTab
from gui.tabs.portion_tools_page import PortionToolsPage
from gui.tabs.print_page import PrintPage
from gui.tabs.recipes_tab import ARCHIVE_ACTION, RecipesTab
from gui.tabs.import_formats_page import ImportFormatsPage
from gui.tabs.suppliers_tab import SuppliersTab
from gui.tabs.vendor_items_page import VendorItemsPage
from gui.services.compare_tray import CompareTray
from gui.services.updates import UpdateService
from gui.widgets.app_header import AppHeader
from gui.widgets.command_palette import CommandPalette
from gui.widgets.compare_tray_dock import CompareTrayDock
from gui.widgets.status_bar import RecipeWizardStatusBar


class MainWindow(QMainWindow):
    '''Shell, top to bottom: menu bar, app bar (four places), the
    current place, the docked compare tray, the status bar.

    Places follow the RecipeWizard Framework canvas: Recipes (pinned
    Library tab + one tab per open recipe), Ingredients, Analytics
    (the compare tray, expanded) and Configure (setup and upkeep —
    formats, categories, suppliers, library health, data & backups,
    images, preferences). Ctrl+1-4 switch places; every command lives
    in the menu bar with its shortcut.'''

    _PLACES = ('recipes', 'ingredients', 'analytics', 'configure')

    def __init__(self, progress=None):
        '''`progress(message, fraction)` reports each stage of building
        the window to the startup splash.'''
        super().__init__()
        self._progress = progress or (lambda _message, _fraction: None)
        self.setWindowTitle(config.APPNAME)
        self.resize(1200, 820)
        # Push the user's saved USDA API key into the API client before any
        # USDA-dependent dialog can open. Empty string = use DEMO_KEY fallback.
        api.usda.set_api_key(QSettings().value('usda/apiKey', '', type=str))
        self._build_places()
        self._progress('Setting up menus…', 0.86)
        self._build_menus()
        self._restore_state()
        self.updates = UpdateService(self)
        self.updates.updateAvailable.connect(self._on_update_available)
        self.updates.schedule_startup_check()

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
            self.app_header.set_current(idx)
            self.stack.setCurrentIndex(idx)

        # Reopen the recipe tabs from last session, skipping any recipe
        # that's been deleted since (e.g. by a restore).
        existing = {r['Id'] for r in db.recipe_info()}
        reopen = [rid for rid in _parse_id_list(settings.value('recipes/openTabs', '')) if rid in existing]
        for i, rid in enumerate(reopen):
            self._progress(f'Reopening recipes ({i + 1} of {len(reopen)})…', 0.95 + 0.04 * i / len(reopen))
            self.recipes_tab.open_in_editor(rid)
        tab_idx = settings.value('recipes/currentTab', 0)
        try:
            self.recipes_tab.editor_tabs.setCurrentIndex(int(tab_idx))
        except (TypeError, ValueError):
            pass

        self._set_tray_docked(settings.value('compareTray/docked', False, type=bool))
        # Stored as "hidden" (default off) under a fresh key: the earlier
        # recipes/facetsVisible was written from isVisible() and could
        # record a bogus False, so it's deliberately not read.
        self.recipes_tab.set_facets_visible(
            not settings.value('recipes/facetsHidden', False, type=bool))
        self._sync_tray_visibility()

    def closeEvent(self, event):
        # Capture tabs before closing them — the close below empties
        # the strip. Close each tab so unsaved edits get a prompt and
        # cost snapshots stamp; Cancel on any prompt keeps the app open.
        tabs = self.recipes_tab.editor_tabs
        open_ids = tabs.open_recipe_ids()
        current_tab = tabs.currentIndex()
        if not self.recipes_tab.close_all_tabs():
            event.ignore()
            return
        settings = QSettings()
        settings.setValue('mainWindow/geometry', self.saveGeometry())
        settings.setValue('mainWindow/state', self.saveState())
        settings.setValue('mainWindow/currentPlace', self.app_header.current())
        settings.setValue('recipes/openTabs', ','.join(str(i) for i in open_ids))
        settings.setValue('recipes/currentTab', current_tab)
        settings.setValue('compareTray/docked', self._tray_docked)
        settings.setValue('recipes/facetsHidden', not self.recipes_tab.facets_visible())
        super().closeEvent(event)

    def _build_places(self):
        '''App bar + stacked places + docked compare tray + status bar.
        One place per app-bar slot; indices follow _PLACES. Model refs
        are stashed on self so handlers can call refresh() on them.'''
        self._progress('Loading ingredients…', 0.42)
        self.ingredients_model = IngredientsModel(self)
        self._progress('Loading recipes…', 0.46)
        self.recipes_model = RecipesModel(self)

        # Session-only staging set for side-by-side comparison. Lives
        # here so every place (Recipes cards, Analytics, the docked
        # strip, the status-bar chip) shares one source of truth.
        self.compare_tray = CompareTray(self)

        self.app_header = AppHeader(self)
        self.stack = QStackedWidget()
        # Workspace backdrop is the Evergreens `bg` token so places
        # inherit a consistent warm off-white, not Qt's OS default.
        self.stack.setAutoFillBackground(True)
        self.stack.setStyleSheet('QStackedWidget { background: #fffaf2; }')
        # Docking the compare tray must take its height from the place,
        # never grow the window. An Ignored vertical policy drops the
        # pages' minimum-size hints from the layout's sums; the explicit
        # floor keeps a place usable when the window is short.
        self.stack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Ignored)
        self.stack.setMinimumHeight(160)
        self.app_header.placeChanged.connect(self.stack.setCurrentIndex)
        self.app_header.placeChanged.connect(lambda _i: self._sync_tray_visibility())

        self._progress('Building the recipe library…', 0.5)
        self.app_header.add_place('Recipes')
        self.stack.addWidget(self._recipes_place())
        self._progress('Building Ingredients…', 0.66)
        self.app_header.add_place('Ingredients')
        self.stack.addWidget(self._ingredients_place())
        self._progress('Building Analytics…', 0.69)
        self.app_header.add_place('Analytics')
        self.stack.addWidget(self._analytics_place())
        self._progress('Building Configure…', 0.71)
        self.app_header.add_place('Configure')
        self.stack.addWidget(self._configure_place())
        self._progress('Checking library health…', 0.82)

        self.tray_dock = CompareTrayDock(self.compare_tray)
        self.tray_dock.expandRequested.connect(lambda: self._go_to_place('analytics'))
        self.tray_dock.recipeActivated.connect(self._on_recipe_edit_by_id)
        self.tray_dock.printRequested.connect(self._print_recipes)
        self.tray_dock.printNoPortionsRequested.connect(lambda ids: self._print_recipes(ids, portions=False))
        self._tray_docked = False

        self.status_bar = RecipeWizardStatusBar()
        self.status_bar.compareTrayClicked.connect(self._toggle_tray_docked)
        self.status_bar.updateClicked.connect(self._on_show_update)
        self.compare_tray.changed.connect(
            lambda: self.status_bar.set_compare_tray_count(self.compare_tray.count())
        )
        self.status_bar.set_compare_tray_count(self.compare_tray.count())

        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self.app_header)
        outer.addWidget(self.stack, stretch=1)
        outer.addWidget(self.tray_dock)
        outer.addWidget(self.status_bar)
        self.setCentralWidget(central)

        # Keep the status bar, Library health, header freshness and the
        # Library tab count in sync with the models.
        for m in (self.ingredients_model, self.recipes_model):
            m.modelReset.connect(self.status_bar.refresh)
            m.modelReset.connect(self.library_health_tab.mark_stale)
            m.modelReset.connect(self._refresh_header_freshness)
            m.modelReset.connect(self._refresh_health_count)
            m.modelReset.connect(self._refresh_configure_counts)
        self.recipes_model.modelReset.connect(self._refresh_library_count)
        # Diet fit counts follow the recipes.
        self.recipes_model.modelReset.connect(lambda: self.diets_page.refresh())
        self.status_bar.refresh()
        self._refresh_header_freshness()
        self._refresh_health_count()
        self._refresh_library_count()
        self._refresh_configure_counts()

    # --- place builders ------------------------------------------------

    def _recipes_place(self):
        tab = RecipesTab(
            source_model=self.recipes_model,
            context_actions=[
                ('Open in tab', self._on_recipe_edit),
                ('Add to compare (Space)', self._on_toggle_tray_for_row),
                ('Duplicate', lambda r: self._duplicate_recipe(self.recipes_model.id_at_row(r))),
                ('Print…', lambda r: self._print_recipes([self.recipes_model.id_at_row(r)])),
                ('Print without portions…',
                 lambda r: self._print_recipes([self.recipes_model.id_at_row(r)], portions=False)),
                (ARCHIVE_ACTION, None),
                (None, None),
                ('Delete…', self._on_recipe_delete),
            ],
            compare_tray=self.compare_tray,
        )
        tab.newRecipeRequested.connect(self._on_new_recipe)
        tab.duplicateRequested.connect(self._duplicate_recipe)
        tab.printRequested.connect(lambda rid: self._print_recipes([rid]))
        # A recipe deleted or saved from its tab changes what the
        # library, gallery and counts show.
        tab.recipeDeletedFromTabs.connect(lambda _rid: self.refresh())
        tabs = tab.editor_tabs
        tabs.recipeSaved.connect(lambda _rid: self.refresh())
        tabs.newTabRequested.connect(self._on_new_recipe)
        tabs.currentEditorChanged.connect(lambda _w: self._sync_recipe_state())
        tabs.dirtyChanged.connect(self._sync_recipe_state)
        self.recipes_tab = tab
        return tab

    def _on_toggle_tray_for_row(self, src_row):
        rid = self.recipes_model.id_at_row(src_row)
        self.compare_tray.toggle(rid)

    def _ingredients_place(self):
        tab = IngredientsTab(
            source_model=self.ingredients_model,
            context_actions=[
                ('Edit…', self._on_ingredient_edit),
                ('New price…', lambda r: self._on_ingredient_new_price(
                    self.ingredients_model.id_at_row(r))),
                ('Delete', self._on_ingredient_delete),
            ],
        )
        tab.rowActivated.connect(self._on_ingredient_edit)
        tab.newIngredientRequested.connect(self._on_new_ingredient_search)
        tab.newPriceRequested.connect(self._on_ingredient_new_price)
        tab.importRequested.connect(self._on_import_purchases)
        tab.recipeRequested.connect(self._on_recipe_edit_by_id)
        self.ingredients_tab = tab
        return tab

    def _on_ingredient_new_price(self, ingredient_id):
        if IngredientPriceEditDialog(ingredient_id, parent=self).exec() == QDialog.Accepted:
            self.refresh()

    def _on_import_purchases(self):
        '''Ingredients › Import purchases…: the wizard, then everything
        that shows prices catches up (it may also have been undone).'''
        run_import(self)
        self._on_prices_imported()

    def _on_prices_imported(self):
        self.refresh()
        self.vendor_items_page.refresh()
        self.import_formats_page.refresh()
        self.suppliers_page.refresh()
        self._refresh_configure_counts()

    def _analytics_place(self):
        tab = AnalyticsTab(self.recipes_model, compare_tray=self.compare_tray,
                           library_ids=lambda: self.recipes_tab.visible_ids())
        tab.recipeActivated.connect(self._on_recipe_edit_by_id)
        tab.dockRequested.connect(self._on_dock_tray)
        self.analytics_tab = tab
        return tab

    def _on_dock_tray(self):
        '''Analytics › Dock to bottom: back to Recipes with the tray docked.'''
        self._set_tray_docked(True)
        self._go_to_place('recipes')

    def _configure_place(self):
        '''Setup and upkeep. Suppliers and Library health are hosted
        inline; the rest open their existing dialogs until they move
        inline in a later slice.'''
        cfg = ConfigureTab()
        cfg.add_group('Menu library')
        self.templates_page = TemplatesEditor()
        cfg.add_section('formats', 'Formats & templates', self.templates_page)
        self.categories_page = TagsPage(
            'Ingredient categories', 'ingredient',
            'Order sets the wedge order. Nutrition and Price set what Library health checks')
        self.categories_page.changed.connect(self._on_config_changed)
        cfg.add_section('categories', 'Ingredient categories', self.categories_page)
        self.allergens_page = AllergensPage()
        self.allergens_page.changed.connect(self._on_config_changed)
        cfg.add_section('allergens', 'Allergens', self.allergens_page)
        self.recipe_tags_page = TagsPage('Recipe tags', 'recipe_tag')
        self.recipe_tags_page.changed.connect(self._on_config_changed)
        cfg.add_section('recipe_tags', 'Recipe tags', self.recipe_tags_page)
        self.diets_page = DietsPage(self.recipes_model)
        self.diets_page.changed.connect(self._on_config_changed)
        cfg.add_section('diets', 'Diets', self.diets_page)
        self.portion_tools_page = PortionToolsPage()
        cfg.add_section('portion_tools', 'Portion tools', self.portion_tools_page)
        # Template, category and tag edits save as they're made; the
        # Library picks them up when you move on.
        cfg.sectionChanged.connect(self._on_config_section_changed)
        cfg.add_group('Purchasing')
        self.suppliers_page = SuppliersTab()
        self.suppliers_page.changed.connect(self._on_config_changed)
        self.suppliers_page.ingredientRequested.connect(self._edit_ingredient_from_suppliers)
        cfg.add_section('suppliers', 'Suppliers', self.suppliers_page)
        self.vendor_items_page = VendorItemsPage()
        self.vendor_items_page.changed.connect(self._on_prices_imported)
        self.vendor_items_page.importRequested.connect(self._on_import_purchases)
        cfg.add_section('vendor_items', 'Vendor items', self.vendor_items_page)
        self.import_formats_page = ImportFormatsPage()
        self.import_formats_page.changed.connect(self._on_prices_imported)
        self.import_formats_page.importRequested.connect(self._on_import_purchases)
        cfg.add_section('import_formats', 'Import formats & history', self.import_formats_page)
        cfg.add_group('Upkeep')
        self.library_health_tab = LibraryHealthTab()
        self.library_health_tab.ingredientRequested.connect(self._on_ingredient_edit_by_id)
        self.library_health_tab.newPriceRequested.connect(self._on_ingredient_new_price)
        self.library_health_tab.changed.connect(self._refresh_health_count)
        cfg.add_section('health', 'Library health', self.library_health_tab)
        cfg.add_section('data', 'Data & backups', LauncherPage(
            'Data & backups',
            '',
            [
                ('Back up now', self._on_backup_now),
                ('Back up to…', self._on_backup_database),
                ('Restore…', self._on_restore_database),
                ('Open data folder', self._on_open_data_folder),
            ],
        ))
        cfg.add_section('images', 'Images', LauncherPage(
            'Images',
            '',
            [
                ('Auto-assign images', self._on_auto_assign_images),
                ('Bulk assign…', self._on_bulk_assign_images),
            ],
        ))
        cfg.add_group('App')
        self.preferences_page = PreferencesPage()
        self.preferences_page.changed.connect(self._refresh_configure_counts)
        self.preferences_page.foodCostChanged.connect(self._on_food_cost_target_changed)
        cfg.add_section('preferences', 'Preferences', self.preferences_page)
        self.print_page = PrintPage()
        cfg.add_section('print', 'Print & branding', self.print_page)
        self.configure_tab = cfg
        return cfg

    def _on_config_section_changed(self, key):
        left = getattr(self, '_config_section', None)
        self._config_section = key
        if left in ('formats', 'categories', 'recipe_tags', 'suppliers'):
            self.refresh()
        page = {'formats': None, 'categories': self.categories_page, 'recipe_tags': self.recipe_tags_page,
                'allergens': self.allergens_page, 'diets': self.diets_page,
                'vendor_items': getattr(self, 'vendor_items_page', None),
                'import_formats': getattr(self, 'import_formats_page', None)}.get(key)
        if page is not None:
            page.refresh()
        if key == 'formats':
            self.templates_page._refresh_list()

    def _edit_ingredient_from_suppliers(self, ingredient_id):
        dlg = self._on_ingredient_edit_by_id(ingredient_id)
        if dlg is not None and getattr(dlg, 'modified', False):
            self.suppliers_page.refresh()

    def _on_config_changed(self):
        '''A Configure page saved a change the Library depends on
        (allergens, diet rules): recompute, and let the other pages
        pick it up.'''
        self.refresh()
        sender = self.sender()
        for page in (self.allergens_page, self.diets_page):
            if page is not sender:
                page.refresh()

    # --- shell state ---------------------------------------------------

    def _go_to_place(self, name):
        self.app_header.set_current(self._PLACES.index(name))

    def _on_show_library(self):
        self._go_to_place('recipes')
        self.recipes_tab.show_library()

    def _set_tray_docked(self, docked):
        self._tray_docked = bool(docked)
        self.status_bar.set_compare_tray_docked(self._tray_docked)
        if hasattr(self, 'tray_toggle_action'):
            self.tray_toggle_action.setChecked(self._tray_docked)
        self._sync_tray_visibility()

    def _toggle_tray_docked(self):
        '''Ctrl+Shift+C / status-bar chip: collapsed ↔ docked. From
        Analytics (the expanded tray) it docks and returns to Recipes.'''
        if self.app_header.current() == self._PLACES.index('analytics'):
            self._set_tray_docked(True)
            self._go_to_place('recipes')
            return
        self._set_tray_docked(not self._tray_docked)

    def _sync_tray_visibility(self):
        on_analytics = self.app_header.current() == self._PLACES.index('analytics')
        self.tray_dock.setVisible(self._tray_docked and not on_analytics)

    def _toggle_facets(self):
        self._on_show_library()
        self.recipes_tab.set_facets_visible(not self.recipes_tab.facets_visible())

    def _refresh_health_count(self):
        try:
            n = db.library_health()['issues']
        except Exception:
            n = 0
        tip = f"{n} thing{'s' if n != 1 else ''} to fix in Library health"
        self.app_header.set_badge(self._PLACES.index('configure'), n, tip)
        self.configure_tab.set_section_alert('health', n, tip)

    def _refresh_configure_counts(self):
        cfg = self.configure_tab
        for key, n in (('formats', len(db.get_tags('recipe'))), ('categories', len(db.get_tags('ingredient'))),
                       ('allergens', len(db.get_all_allergen_rows())), ('recipe_tags', len(db.get_tags('recipe_tag'))),
                       ('diets', len(db.get_diets())), ('suppliers', len(db.get_suppliers()))):
            cfg.set_section_count(key, n)
        flagged = self.vendor_items_page.flagged_count()
        cfg.set_section_count('vendor_items', f'{flagged} flagged' if flagged else '')
        # The nav hints at what Preferences holds, as the canvas does.
        cfg.set_section_count('preferences', 'USDA key' if self.preferences_page.has_key() else 'demo key')

    def _refresh_library_count(self):
        self.recipes_tab.editor_tabs.set_library_count(self.recipes_model.rowCount())

    def _current_editor(self):
        return self.recipes_tab.editor_tabs.current_editor()

    def _sync_recipe_state(self):
        '''Enable recipe-only menu actions when a recipe tab is current,
        and show its unsaved-edit count in the status bar.'''
        editor = self._current_editor()
        for action in getattr(self, '_recipe_actions', ()):
            action.setEnabled(editor is not None)
        self.status_bar.set_unsaved_count(editor.dirty_count() if editor else 0)

    def _with_editor(self, method_name):
        editor = self._current_editor()
        if editor is not None:
            getattr(editor, method_name)()

    def _focus_active_filter(self):
        place = self.stack.currentWidget()
        focus = getattr(place, 'focus_filter', None)
        if callable(focus):
            focus()

    def _on_command_palette(self):
        '''Ctrl+K entry point. Builds a fresh index each time — recipe /
        ingredient lists change often enough that caching would need
        invalidation anyway.'''
        recipes = [(r['Id'], r['Name']) for r in db.recipe_info()]
        ingredients = [(i['Id'], i['Name']) for i in db.get_ingredients()]
        commands = [
            ('new-recipe', 'New Recipe'),
            ('new-ingredient-usda', 'New Ingredient (USDA Search)'),
            ('new-ingredient-blank', 'New Ingredient (Blank)'),
            ('preferences', 'Open Preferences…'),
            ('backup-now', 'Back Up Library Now'),
            ('backup', 'Back Up Library To…'),
            ('restore', 'Restore Library…'),
            ('open-data-folder', 'Open Data Folder'),
            ('reset-sample', 'Reset With Sample Data…'),
            ('place-recipes', 'Go to Recipes'),
            ('place-library', 'Go to Library'),
            ('place-ingredients', 'Go to Ingredients'),
            ('place-analytics', 'Go to Analytics'),
            ('place-configure', 'Go to Configure'),
            ('formats', 'Formats & Templates'),
            ('suppliers', 'Suppliers'),
            ('import-purchases', 'Import Purchases…'),
            ('vendor-items', 'Vendor Items'),
            ('health', 'Library Health'),
            ('compare-tray', 'Show / Hide Compare Tray'),
            ('check-updates', 'Check for Updates…'),
            ('about', 'About RecipeWizard'),
        ]
        self._command_handlers = {
            'new-recipe': self._on_new_recipe,
            'new-ingredient-usda': self._on_new_ingredient_search,
            'new-ingredient-blank': self._on_new_ingredient_blank,
            'preferences': self._on_preferences,
            'backup-now': self._on_backup_now,
            'backup': self._on_backup_database,
            'restore': self._on_restore_database,
            'open-data-folder': self._on_open_data_folder,
            'reset-sample': self._on_reset_sample,
            'place-recipes': lambda: self._go_to_place('recipes'),
            'place-library': self._on_show_library,
            'place-ingredients': lambda: self._go_to_place('ingredients'),
            'place-analytics': lambda: self._go_to_place('analytics'),
            'place-configure': lambda: self._go_to_place('configure'),
            'formats': lambda: self._show_configure('formats'),
            'suppliers': lambda: self._show_configure('suppliers'),
            'import-purchases': self._on_import_purchases,
            'vendor-items': lambda: self._show_configure('vendor_items'),
            'health': lambda: self._show_configure('health'),
            'compare-tray': self._toggle_tray_docked,
            'check-updates': self._on_check_updates,
            'about': self._on_about,
        }
        palette = CommandPalette(recipes, ingredients, commands, parent=self)
        palette.recipeChosen.connect(self._on_recipe_edit_by_id)
        palette.ingredientChosen.connect(self._on_ingredient_edit_by_id)
        palette.commandChosen.connect(self._on_command_chosen)
        palette.exec()

    def _show_configure(self, section):
        self._go_to_place('configure')
        self.configure_tab.show_section(section)

    def _on_command_chosen(self, key):
        handler = self._command_handlers.get(key)
        if handler:
            handler()

    def _on_ingredient_edit_by_id(self, ing_id):
        '''Open the Edit ingredient dialog. Afterwards refresh if it
        changed anything, and open the recipe the user picked under
        "Used in", if they did.'''
        dlg = IngredientEditDialog(ing_id, parent=self)
        dlg.exec()
        if dlg.modified:
            self.refresh()
        if dlg.open_recipe_id is not None:
            self._on_recipe_edit_by_id(dlg.open_recipe_id)
        return dlg

    def _refresh_header_freshness(self):
        '''Push the latest supplier-price date to the app bar's right
        side. Pulled from the same helper the status bar uses so the
        two never disagree.'''
        from gui.widgets.status_bar import _latest_price_date
        d = _latest_price_date()
        self.app_header.set_freshness(
            f'Costed at supplier prices as of {d}' if d else '')

    # --- menus ---------------------------------------------------------

    def _build_menus(self):
        '''File · Edit · View · Recipe · Ingredient · Tools · Help.
        Every command carries its shortcut here; the shortcuts are
        window-wide because they're menu actions.'''
        bar = self.menuBar()

        def add(menu, label, handler, shortcut=None):
            action = menu.addAction(label, handler)
            if shortcut is not None:
                action.setShortcut(shortcut)
            return action

        file_menu = bar.addMenu('&File')
        add(file_menu, '&New Recipe…', self._on_new_recipe, QKeySequence.New)
        add(file_menu, 'New &Ingredient…', self._on_new_ingredient_search, 'Ctrl+Shift+N')
        file_menu.addSeparator()
        save_action = add(file_menu, '&Save Recipe', lambda: self._with_editor('save'),
                          QKeySequence.Save)
        close_action = add(file_menu, '&Close Tab',
                           self.recipes_tab.editor_tabs.close_current)
        # Ctrl+W is owned by the tab strip's own shortcut; showing it
        # here as text keeps the menu honest without a second binding.
        close_action.setText('&Close Tab\tCtrl+W')
        file_menu.addSeparator()
        add(file_menu, 'E&xit', self.close)

        edit_menu = bar.addMenu('&Edit')
        add(edit_menu, '&Go to Anything…', self._on_command_palette, 'Ctrl+K')
        add(edit_menu, '&Filter This List', self._focus_active_filter, QKeySequence.Find)

        view_menu = bar.addMenu('&View')
        for i, name in enumerate(self._PLACES):
            add(view_menu, f'&{name.capitalize()}',
                lambda n=name: self._go_to_place(n), f'Ctrl+{i + 1}')
        add(view_menu, '&Library Tab', self._on_show_library, 'Ctrl+0')
        view_menu.addSeparator()
        self.tray_toggle_action = add(
            view_menu, 'Compare &Tray', self._toggle_tray_docked, 'Ctrl+Shift+C')
        self.tray_toggle_action.setCheckable(True)
        add(view_menu, 'Filter &Pane', self._toggle_facets, 'Ctrl+Alt+S')
        view_menu.addSeparator()
        add(view_menu, '&Refresh', self.refresh, 'F5')

        recipe_menu = bar.addMenu('&Recipe')
        add(recipe_menu, '&New Recipe…', self._on_new_recipe)
        add_component = add(recipe_menu, '&Add Component…',
                            lambda: self._with_editor('add_component'), 'Ctrl+Return')
        recipe_menu.addSeparator()
        label_action = add(recipe_menu, 'Nutrition &Label…',
                           lambda: self._with_editor('show_nutrition_label'))
        history_action = add(recipe_menu, '&Cost Over Time',
                             lambda: self._with_editor('show_cost_history'))
        add(recipe_menu, 'Pr&int Recipe…', self._on_print_current, 'Ctrl+P')
        add(recipe_menu, 'Print &Without Portions…', lambda: self._on_print_current(portions=False), 'Ctrl+Shift+P')
        recipe_menu.addSeparator()
        add(recipe_menu, 'D&uplicate Recipe', self._on_duplicate_current, 'Ctrl+D')
        self.archive_action = add(recipe_menu, 'A&rchive Recipe', self._on_toggle_archive_current)
        recipe_menu.aboutToShow.connect(self._sync_archive_action)
        add(recipe_menu, 'Recipe &Tags…', self._on_recipe_tags)
        delete_action = add(recipe_menu, '&Delete Recipe…',
                            lambda: self._with_editor('delete_recipe'))
        self._recipe_actions = (
            save_action, close_action, add_component,
            label_action, history_action, delete_action,
        )

        ingredient_menu = bar.addMenu('&Ingredient')
        add(ingredient_menu, 'New Ingredient (&USDA Search)…', self._on_new_ingredient_search)
        add(ingredient_menu, 'New Ingredient (&Blank)…', self._on_new_ingredient_blank)
        ingredient_menu.addSeparator()
        add(ingredient_menu, '&Import Purchases…', self._on_import_purchases, 'Ctrl+Shift+I')
        add(ingredient_menu, '&Vendor Items', lambda: self._show_configure('vendor_items'))
        ingredient_menu.addSeparator()
        add(ingredient_menu, 'Ingredient &Categories…', self._on_ingredient_tags)

        tools_menu = bar.addMenu('&Tools')
        add(tools_menu, '&Back Up Library Now', self._on_backup_now, 'Ctrl+Shift+B')
        add(tools_menu, 'Back Up &To…', self._on_backup_database)
        add(tools_menu, '&Restore Library…', self._on_restore_database)
        add(tools_menu, '&Open Data Folder', self._on_open_data_folder)
        tools_menu.addSeparator()
        add(tools_menu, '&Formats && Templates…', lambda: self._show_configure('formats'))
        add(tools_menu, '&Auto-assign Images', self._on_auto_assign_images)
        add(tools_menu, 'Bulk &Assign Images…', self._on_bulk_assign_images)
        tools_menu.addSeparator()
        # MenuRole.PreferencesRole relocates this to the native app-menu
        # slot on macOS; on Windows/Linux it stays here.
        prefs_action = add(tools_menu, '&Preferences…', self._on_preferences)
        prefs_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        tools_menu.addSeparator()
        # Destructive ops live at the bottom so they're physically farther
        # from common actions and harder to hit by accident.
        add(tools_menu, 'Reset &Database…', self._on_reset_clean)
        add(tools_menu, 'Reset With &Sample Data…', self._on_reset_sample)

        help_menu = bar.addMenu('&Help')
        self.update_action = add(help_menu, 'Check for &Updates…', self._on_check_updates)
        help_menu.addSeparator()
        add(help_menu, '&About', self._on_about)

        self._sync_recipe_state()

    # --- refresh ---

    def show_portion_review_if_new(self):
        from gui.dialogs.portion_review import maybe_show_after_upgrade
        if maybe_show_after_upgrade(self):
            self.refresh()

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
        dlg = self._on_ingredient_edit_by_id(self.ingredients_model.id_at_row(src_row))
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
        self._new_ingredient(show_usda=True)

    def _on_new_ingredient_blank(self):
        self._new_ingredient(show_usda=False)

    def _new_ingredient(self, show_usda):
        '''The New ingredient dialog saves everything itself (category,
        allergens, first price), so there's no follow-up edit step.'''
        dlg = IngredientNewDialog(parent=self, show_usda=show_usda)
        dlg.exec()
        if dlg.created_ids:
            self.refresh()
            self._flash_status(dlg.status_message)

    def _on_recipe_edit(self, src_row):
        self._on_recipe_edit_by_id(self.recipes_model.id_at_row(src_row))

    def _on_recipe_edit_by_id(self, recipe_id):
        '''Open a recipe for editing. Switches to the Recipes place and
        opens the recipe in a new (or existing) editor tab. Non-modal:
        the user can switch places, open other recipes, etc. while
        this one stays open.'''
        self.app_header.set_current(self._PLACES.index('recipes'))
        self.recipes_tab.open_in_editor(recipe_id)

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
        # Tear down any editor tab bound to the now-gone id before
        # refreshing — otherwise its close_requested would UPDATE
        # against a missing row and Ctrl+Z could push a bogus command.
        self.recipes_tab.handle_recipe_deleted(row['Id'])
        self.refresh()
        self._flash_status(f"Deleted '{row['Name']}'")

    def _on_duplicate_current(self):
        '''Ctrl+D: the recipe in the current tab, or the Library's
        selection.'''
        rid = self.recipes_tab.selected_recipe_id()
        if rid is not None and self.stack.currentWidget() is self.recipes_tab:
            self._duplicate_recipe(rid)

    def _on_print_current(self, portions=True):
        '''Ctrl+P: the recipe in the current tab, or the Library's
        selection.'''
        editor = self._current_editor()
        if editor is not None and self.stack.currentWidget() is self.recipes_tab:
            self._print_recipes([editor.recipe_id], portions)
            return
        rid = self.recipes_tab.selected_recipe_id()
        if rid is not None and self.stack.currentWidget() is self.recipes_tab:
            self._print_recipes([rid], portions)

    def _print_recipes(self, recipe_ids, portions=True):
        print_recipes(self, [rid for rid in recipe_ids if rid is not None], portions=portions)

    def _sync_archive_action(self):
        editor = self._current_editor()
        if editor is not None:
            archived = editor._archived
        else:
            rid = self.recipes_tab.selected_recipe_id()
            archived = rid is not None and self.recipes_tab.is_archived(rid)
        self.archive_action.setText('&Restore Recipe to Menu' if archived else 'A&rchive Recipe')

    def _on_toggle_archive_current(self):
        '''In a recipe tab, an edit in that tab; on the Library, the
        selection (undoable there with Ctrl+Z).'''
        editor = self._current_editor()
        if editor is not None:
            editor.toggle_archived()
            return
        rid = self.recipes_tab.selected_recipe_id()
        if rid is not None and self.stack.currentWidget() is self.recipes_tab:
            self.recipes_tab.toggle_archived(rid)

    def _duplicate_recipe(self, recipe_id):
        '''Copy the recipe and open the copy in a tab, so it can be
        renamed straight away.'''
        new_id = db.duplicate_recipe(recipe_id)
        self.recipes_tab.select_recipe(new_id)
        self.refresh()
        self._on_recipe_edit_by_id(new_id)
        name = (db.recipe_info(new_id) or {}).get('Name', 'recipe')
        self._flash_status(f"Duplicated as '{name}'")

    def _on_new_recipe(self):
        create_dlg = RecipeCreateDialog(parent=self, edit_templates=self._on_recipe_templates)
        if create_dlg.exec() != QDialog.Accepted or not create_dlg.new_id:
            return
        # Pick up the new row in the recipes model, then open it in a
        # new editor tab (non-modal — user can keep working elsewhere).
        self.refresh()
        self._on_recipe_edit_by_id(create_dlg.new_id)

    # --- functional handlers wired to existing business layer ---

    def _on_open_data_folder(self):
        '''Reveal the per-user data directory (DB + ingredient images) in
        the system file browser. Useful for manual backups or for dropping
        ingredient image files in by hand.'''
        QDesktopServices.openUrl(QUrl.fromLocalFile(config.user_data_dir()))

    def _on_backup_now(self):
        '''Ctrl+Shift+B: a timestamped .rwbackup in the data folder,
        without photos (Back up... asks, for a backup with them). The
        status bar's "Last backup" and Library health's backups card
        both read this folder.'''
        path = os.path.join(backup.default_backup_dir(), backup.timestamped_name())
        if backup_restore.run_backup(self, path, False) is None:
            return False
        self.status_bar.refresh()
        self.library_health_tab.mark_stale()
        return True

    def _on_backup_database(self):
        include_images = backup_restore.ask_backup_options(self)
        if include_images is None:
            return
        # Start in the data folder, where Back Up Now saves and where the
        # status bar and Library health look. A bare file name would open
        # the dialog in the working directory (the project folder when
        # run from source).
        default_path = os.path.join(backup.default_backup_dir(), backup.timestamped_name())
        path, _ = QFileDialog.getSaveFileName(
            self, 'Back Up Library', default_path, f'RecipeWizard backup (*{backup.EXTENSION})',
        )
        if not path:
            return
        if not path.lower().endswith(backup.EXTENSION):
            path += backup.EXTENSION
        if backup_restore.run_backup(self, path, include_images) is None:
            return
        self.status_bar.refresh()
        self.library_health_tab.mark_stale()
        self._flash_status(f'Backed up to {path}')

    def _on_restore_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Restore Library', backup.default_backup_dir(),
            f'RecipeWizard backups (*{backup.EXTENSION} *.db);;All Files (*)',
        )
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(config.DATABASE):
            QMessageBox.warning(
                self, 'Restore Library',
                "That's the current library — pick a backup file.",
            )
            return
        try:
            info = backup.read_backup(path)
        except (backup.BackupError, OSError) as exc:
            QMessageBox.warning(self, 'Restore Library', str(exc))
            return
        dlg = backup_restore.RestoreDialog(info, self)
        if dlg.exec() != QDialog.Accepted:
            return
        mode, safety = dlg.mode, dlg.safety
        if mode == 'overwrite' and QMessageBox.warning(
            self, 'Overwrite Library',
            'Replace your whole library with this backup? '
            + ('Your current library is backed up to the data folder first.' if safety
               else 'Your current library will not be backed up.'),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        # The data is about to change under them; open tabs would point
        # at rows that may no longer exist. Close them (with save
        # prompts) first.
        if not self.recipes_tab.close_all_tabs():
            return
        # Both restores run setup.migrateDB(), so older backups come up
        # to date before any query can hit a missing column.
        result = backup_restore.run_restore(self, path, mode, safety)
        if result is None:
            return
        self.refresh()
        self.status_bar.refresh()
        self.library_health_tab.mark_stale()
        if mode == 'merge':
            backup_restore.show_merge_summary(self, result)
        else:
            images = f' and {result["images"]} photos' if result['images'] else ''
            saved = (f'\n\nYour previous library was saved as {os.path.basename(result["safety"])} '
                     'in the data folder.' if result['safety'] else '')
            QMessageBox.information(
                self, 'Restore finished',
                f'Restored your library{images} from {os.path.basename(path)}.{saved}',
            )
        self._flash_status(f'Restored from {os.path.basename(path)}')

    def _on_reset_clean(self):
        confirm = QMessageBox.warning(
            self, 'Reset Database',
            'Erase ALL data and start with an empty database?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        # The data is about to be replaced; open tabs would point at
        # rows that no longer exist. Close them (with save prompts) first.
        if not self.recipes_tab.close_all_tabs():
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
        # The data is about to be replaced; open tabs would point at
        # rows that no longer exist. Close them (with save prompts) first.
        if not self.recipes_tab.close_all_tabs():
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
        self._show_configure('categories')

    def _on_recipe_tags(self):
        self._show_configure('recipe_tags')

    def _on_recipe_templates(self):
        TemplatesManagerDialog(parent=self).exec()
        # Templates affect what wedges and badges show, so a refresh sweeps
        # any edits (e.g. shape changes) back into the home gallery.
        self.refresh()

    def _on_about(self):
        AboutDialog(parent=self, on_check_updates=self._on_check_updates).exec()

    # --- updates ---

    def _on_update_available(self, release):
        '''Quiet notice: a status-bar chip, and the Help menu entry
        names the version. Nothing pops up on its own.'''
        self.status_bar.set_update(release)
        self.update_action.setText(f'&Update Available: {release.tag}…')

    def _on_show_update(self):
        release = self.updates.release
        if release is None:
            return
        dlg = UpdateDialog(release, parent=self)
        if dlg.exec() == QDialog.Accepted and dlg.install:
            install_update(self, release, backup=self._on_backup_now)

    def _on_check_updates(self):
        '''Help › Check for Updates…: always reports back.'''
        if self.updates.release is not None:
            self._on_show_update()
            return
        self.update_action.setEnabled(False)
        self.updates.check_now(self._on_manual_check_result)

    def _on_manual_check_result(self, kind, value):
        self.update_action.setEnabled(True)
        title = 'Check for Updates'
        if kind == 'update':
            self._on_show_update()
        elif kind == 'current':
            QMessageBox.information(
                self, title, f"You're up to date. RecipeWizard v{config.__version__} "
                'is the newest version.')
        else:
            QMessageBox.warning(self, title, f"Couldn't check for updates.\n\n{value}")

    def _on_food_cost_target_changed(self):
        '''The target moved or was switched off: everything that marks
        recipes over it redraws — Library, inspector, Needs review, open
        recipe tabs.'''
        self.refresh()
        for editor in self.recipes_tab.editor_tabs.editors():
            editor._refresh()

    def _on_preferences(self):
        self._show_configure('preferences')


def _parse_id_list(value):
    '''"12,7,30" (QSettings) → [12, 7, 30], skipping junk.'''
    ids = []
    for part in str(value or '').split(','):
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids
