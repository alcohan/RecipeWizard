'''Recipes place — a tab strip whose pinned first tab is the Library
(facet pane + filter + gallery/table) and whose other tabs are open
recipes, one RecipeEditWidget each.

Activating a recipe (double-click a card or row) opens it in a tab
beside Library. Library is always one click (or Ctrl+0) away, and
open tabs survive switching places and restarts.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from gui.models.recipes_facet_proxy import RecipesFacetProxy
from gui.widgets.editor_tabs import EditorTabs
from gui.widgets.recipe_gallery import RecipeGallery
from gui.widgets.recipes_facet_pane import RecipesFacetPane
from gui.widgets.view_toggle import ViewToggle


_SETTINGS_KEY = 'recipes/view'
_DEFAULT_VIEW = 'gallery'


class RecipesTab(QWidget):
    rowActivated = Signal(int)         # source-model row index (unused now; kept for API parity)
    recipeIdActivated = Signal(int)    # convenience: emits recipe id
    recipeDeletedFromTabs = Signal(int)  # propagates from EditorTabs so MainWindow can refresh

    def __init__(self, source_model, context_actions, action_buttons,
                 compare_tray=None, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions
        self._compare_tray = compare_tray

        library_view = self._build_library(source_model, action_buttons)

        self.editor_tabs = EditorTabs(library_view, compare_tray=compare_tray)
        self.editor_tabs.recipeDeleted.connect(self.recipeDeletedFromTabs.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor_tabs)

        # Row activation now opens the recipe in the editor tabs — the
        # old modal-dialog path is gone from this place. External
        # callers that still want to open a recipe (Analytics
        # double-click, "+ New Recipe") call open_in_editor(id)
        # directly on this widget.
        self.rowActivated.connect(self._open_from_source_row)

        # Space toggles the currently-focused recipe in the compare
        # tray. Scoped to this widget so Space elsewhere (inputs,
        # ingredients) is unaffected.
        if self._compare_tray is not None:
            space_sc = QShortcut(QKeySequence(Qt.Key_Space), self)
            space_sc.setContext(Qt.WidgetWithChildrenShortcut)
            space_sc.activated.connect(self._toggle_tray_for_current)

    # --- library view --------------------------------------------------

    def _build_library(self, source_model, action_buttons):
        saved = QSettings().value(_SETTINGS_KEY, _DEFAULT_VIEW, type=str)
        initial_view = saved if saved in ('gallery', 'table') else _DEFAULT_VIEW

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('\U0001F50D  Filter recipes…')
        self.filter_edit.setClearButtonEnabled(True)

        self.toggle = ViewToggle(
            modes=[('gallery', '⊞ Gallery'), ('table', '☰ Table')],
            current=initial_view,
        )
        self.toggle.viewChanged.connect(self._on_view_changed)

        self.gallery = RecipeGallery(source_model, compare_tray=self._compare_tray)
        self.gallery.recipeClicked.connect(self.recipeIdActivated.emit)
        self.gallery.recipeClicked.connect(self._emit_row_for_recipe)

        self.table = self._build_table(source_model)

        self.filter_edit.textChanged.connect(self.proxy.setFilterText)
        self.filter_edit.textChanged.connect(self.gallery.setFilterText)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.gallery)
        self.stack.addWidget(self.table)
        self.stack.setCurrentIndex(0 if initial_view == 'gallery' else 1)

        header_row = QHBoxLayout()
        header_row.addWidget(self.filter_edit, stretch=1)
        header_row.addSpacing(12)
        header_row.addWidget(self.toggle)

        button_row = QHBoxLayout()
        for btn in action_buttons:
            button_row.addWidget(btn)
        button_row.addStretch()

        # Facet pane on the left, workspace content on the right.
        self.facet_pane = RecipesFacetPane()
        self.facet_pane.formatsChanged.connect(self.proxy.setFormats)
        self.facet_pane.freeFromChanged.connect(self.proxy.setFreeFrom)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addLayout(header_row)
        content_layout.addWidget(self.stack, stretch=1)
        content_layout.addLayout(button_row)

        wrap = QWidget()
        wrap_layout = QHBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(self.facet_pane)
        wrap_layout.addWidget(content, stretch=1)
        return wrap

    def _build_table(self, source_model):
        self.proxy = RecipesFacetProxy(self)
        self.proxy.setSourceModel(source_model)

        table = QTableView()
        table.setModel(self.proxy)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSortingEnabled(True)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(24)
        table.horizontalHeader().setStretchLastSection(True)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_table_context_menu)
        table.doubleClicked.connect(self._on_table_activated)
        return table

    # --- public API ----------------------------------------------------

    def open_in_editor(self, recipe_id):
        '''Open the given recipe in a tab — creating a new tab or
        re-focusing an existing one.'''
        self.editor_tabs.open_recipe(recipe_id)

    def show_library(self):
        self.editor_tabs.show_library()

    def close_all_tabs(self):
        '''Called by MainWindow on shutdown so unsaved edits get a
        prompt. Returns False if the user cancelled.'''
        return self.editor_tabs.close_all()

    def handle_recipe_deleted(self, recipe_id):
        '''MainWindow calls this after deleting a recipe from the
        library view, so any editor tab bound to that id is torn
        down cleanly instead of running UPDATE paths against the
        gone row.'''
        self.editor_tabs.handle_external_delete(recipe_id)

    # --- library handlers ----------------------------------------------

    def _on_view_changed(self, name):
        self.stack.setCurrentIndex(0 if name == 'gallery' else 1)
        QSettings().setValue(_SETTINGS_KEY, name)

    def _on_table_activated(self, view_index):
        if not view_index.isValid():
            return
        self.rowActivated.emit(self.proxy.mapToSource(view_index).row())

    def _emit_row_for_recipe(self, recipe_id):
        '''Look up a recipe's source-model row from its id so the
        gallery can emit the same rowActivated signal as the table.'''
        model = self.source_model
        for i in range(model.rowCount()):
            if model.id_at_row(i) == recipe_id:
                self.rowActivated.emit(i)
                return

    def _open_from_source_row(self, src_row):
        recipe_id = self.source_model.id_at_row(src_row)
        self.open_in_editor(recipe_id)

    def _show_table_context_menu(self, point):
        view_index = self.table.indexAt(point)
        if not view_index.isValid():
            return
        src_row = self.proxy.mapToSource(view_index).row()
        menu = QMenu(self.table)
        for label, handler in self._context_actions:
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, r=src_row, h=handler: h(r))
        menu.exec(self.table.viewport().mapToGlobal(point))

    def focus_filter(self):
        # Ctrl+F filters the Library, so it brings the Library forward.
        self.editor_tabs.show_library()
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()

    def set_facets_visible(self, visible):
        self.facet_pane.setVisible(visible)

    def facets_visible(self):
        '''The user's show/hide choice. Not isVisible(): that's also
        False whenever the Library tab or this place is off-screen.'''
        return not self.facet_pane.isHidden()

    def _toggle_tray_for_current(self):
        '''Space handler. On the Library tab it toggles the table's
        current recipe; on a recipe tab it toggles that recipe.'''
        if self._compare_tray is None:
            return
        editor = self.editor_tabs.current_editor()
        if editor is not None:
            self._compare_tray.toggle(editor.recipe_id)
            return
        rid = None
        if self.stack.currentWidget() is self.table:
            idx = self.table.currentIndex()
            if idx.isValid():
                src_row = self.proxy.mapToSource(idx).row()
                rid = self.source_model.id_at_row(src_row)
        if rid is not None:
            self._compare_tray.toggle(rid)
