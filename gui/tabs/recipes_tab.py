'''Recipes place — library mode (filter + view toggle + action buttons
wrapping a stacked gallery/table) switchable to editor mode (an
EditorTabs holding one tab per open recipe).

Activating a recipe (double-click a card or row) switches this place
into editor mode and opens the recipe in a new tab. The "← Recipes"
breadcrumb at the top of the editor returns to library mode without
closing any tabs — so they're still there when the user comes back.
Closing the last tab auto-returns to library mode.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QPushButton, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.widgets.editor_tabs import EditorTabs
from gui.widgets.recipe_gallery import RecipeGallery
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
        editor_view = self._build_editor()

        self._mode_stack = QStackedWidget()
        self._mode_stack.addWidget(library_view)    # index 0
        self._mode_stack.addWidget(editor_view)     # index 1
        self._mode_stack.setCurrentIndex(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._mode_stack)

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

        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.addLayout(header_row)
        wrap_layout.addWidget(self.stack, stretch=1)
        wrap_layout.addLayout(button_row)
        return wrap

    def _build_table(self, source_model):
        self.proxy = MultiColumnFilterProxy(self)
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

    # --- editor view ---------------------------------------------------

    def _build_editor(self):
        back_btn = QPushButton('← Recipes')
        back_btn.setFlat(True)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.setStyleSheet('''
            QPushButton {
                color: #347200;
                font-weight: 600;
                padding: 6px 8px;
                border: 0;
                text-align: left;
            }
            QPushButton:hover { color: #285900; }
        ''')
        back_btn.clicked.connect(self._on_back_to_library)

        breadcrumb_row = QHBoxLayout()
        breadcrumb_row.setContentsMargins(0, 0, 0, 0)
        breadcrumb_row.addWidget(back_btn)
        breadcrumb_row.addStretch()

        self.editor_tabs = EditorTabs()
        self.editor_tabs.allClosed.connect(self._on_all_tabs_closed)
        self.editor_tabs.recipeDeleted.connect(self.recipeDeletedFromTabs.emit)

        wrap = QWidget()
        wrap_layout = QVBoxLayout(wrap)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.addLayout(breadcrumb_row)
        wrap_layout.addWidget(self.editor_tabs, stretch=1)
        return wrap

    # --- public API ----------------------------------------------------

    def open_in_editor(self, recipe_id):
        '''Switch to editor mode and open the given recipe in a tab —
        creating a new tab or re-focusing an existing one.'''
        self.editor_tabs.open_recipe(recipe_id)
        self._mode_stack.setCurrentIndex(1)

    def close_all_tabs(self):
        '''Called by MainWindow on shutdown so cost snapshots stamp
        before the app goes away.'''
        self.editor_tabs.close_all()

    def _on_back_to_library(self):
        '''Breadcrumb click — switch to library mode WITHOUT closing
        open tabs. They're still there when the user comes back.'''
        self._mode_stack.setCurrentIndex(0)

    def _on_all_tabs_closed(self):
        '''EditorTabs fired allClosed. Auto-return to library mode so
        the user isn't staring at an empty tab bar.'''
        self._mode_stack.setCurrentIndex(0)

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
        # Only meaningful in library mode. In editor mode, Ctrl+F does
        # nothing (the recipe editor has its own focus targets).
        if self._mode_stack.currentIndex() == 0:
            self.filter_edit.setFocus()
            self.filter_edit.selectAll()

    def _toggle_tray_for_current(self):
        '''Space handler for library mode (table view). In editor mode,
        Space is a plain space in whatever input has focus.'''
        if self._compare_tray is None:
            return
        if self._mode_stack.currentIndex() != 0:
            return
        rid = None
        if self.stack.currentWidget() is self.table:
            idx = self.table.currentIndex()
            if idx.isValid():
                src_row = self.proxy.mapToSource(idx).row()
                rid = self.source_model.id_at_row(src_row)
        if rid is not None:
            self._compare_tray.toggle(rid)
