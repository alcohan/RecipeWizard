'''Recipes place — a tab strip whose pinned first tab is the Library
and whose other tabs are open recipes, one RecipeEditWidget each.

The Library, per the Framework canvas: a toolbar (title, filter,
"N of M", Sort, Wedges/Table, New recipe), the filter pane on the
left, the gallery (grouped by format) or table in the middle, and the
inspector on the right.

Single click selects a recipe and fills the inspector; double-click
or Enter opens it in a tab beside Library. Space adds the selected
recipe to the compare tray. Both views read one RecipesModel through
RecipesFacetProxy (the gallery via its accepts_row), and the
selection is kept by recipe id across refreshes. Open tabs survive
switching places and restarts.
'''
from PySide6.QtCore import QItemSelectionModel, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMenu, QPushButton, QStackedWidget, QTableView, QVBoxLayout,
    QWidget,
)

from gui.models.recipes_facet_proxy import RecipesFacetProxy
from gui.models.recipes_model import SORTS
from gui.widgets.editor_tabs import EditorTabs
from gui.widgets.recipe_gallery import RecipeGallery
from gui.widgets.recipe_inspector import RecipeInspector
from gui.widgets.recipes_facet_pane import RecipesFacetPane


_VIEW_KEY = 'recipes/view'
_SORT_KEY = 'recipes/sort'
_DEFAULT_VIEW = 'gallery'
_DEFAULT_SORT = 'name'

_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"


class RecipesTab(QWidget):
    rowActivated = Signal(int)           # source-model row index
    recipeIdActivated = Signal(int)
    recipeDeletedFromTabs = Signal(int)  # propagates from EditorTabs so MainWindow can refresh
    newRecipeRequested = Signal()
    duplicateRequested = Signal(int)     # recipe id

    def __init__(self, source_model, context_actions, compare_tray=None, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions
        self._compare_tray = compare_tray
        self._selected_id = None
        self._restore_id = None

        self._inspect_timer = QTimer(self)
        self._inspect_timer.setSingleShot(True)
        self._inspect_timer.setInterval(60)
        self._inspect_timer.timeout.connect(self._update_inspector)

        library_view = self._build_library()
        self.editor_tabs = EditorTabs(library_view, compare_tray=compare_tray)
        self.editor_tabs.recipeDeleted.connect(self.recipeDeletedFromTabs.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.editor_tabs)

        self.rowActivated.connect(lambda r: self.open_in_editor(self.source_model.id_at_row(r)))

        # Library keys, scoped to the Library page so they never reach
        # an editor tab: Enter opens, Space toggles the compare tray.
        for key in (Qt.Key_Return, Qt.Key_Enter):
            sc = QShortcut(QKeySequence(key), library_view)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda: self._open_id(self._selected_id))
        if self._compare_tray is not None:
            space_sc = QShortcut(QKeySequence(Qt.Key_Space), self)
            space_sc.setContext(Qt.WidgetWithChildrenShortcut)
            space_sc.activated.connect(self._toggle_tray_for_current)

        source_model.modelAboutToBeReset.connect(self._remember_selection)
        source_model.modelReset.connect(self._on_model_reset)
        self._stale = True

    # --- building ------------------------------------------------------

    def _build_library(self):
        self.proxy = RecipesFacetProxy(self)
        self.proxy.setSourceModel(self.source_model)

        toolbar = self._build_toolbar()
        self.facet_pane = RecipesFacetPane()
        self.facet_pane.changed.connect(self._apply_facets)

        self.gallery = RecipeGallery(self.source_model, compare_tray=self._compare_tray)
        self.gallery.recipeClicked.connect(self._on_gallery_clicked)
        self.gallery.recipeActivated.connect(self._open_id)
        self.gallery.contextMenuRequested.connect(self._show_context_menu)
        self.gallery.set_row_filter(self.proxy.accepts_row)

        self.table = self._build_table()
        table_card = QFrame()
        table_card.setObjectName('TableCard')
        table_card.setStyleSheet(f'QFrame#TableCard {{ background: #ffffff; border: 1px solid {_BORDER};'
                                 ' border-radius: 8px; }')
        tc = QVBoxLayout(table_card)
        tc.setContentsMargins(1, 1, 1, 1)
        tc.addWidget(self.table)
        table_wrap = QWidget()
        tw = QVBoxLayout(table_wrap)
        tw.setContentsMargins(20, 16, 20, 20)
        tw.addWidget(table_card)

        self.inspector = RecipeInspector()
        self.inspector.openRequested.connect(self._open_id)
        self.inspector.duplicateRequested.connect(self.duplicateRequested.emit)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.gallery)
        self.stack.addWidget(table_wrap)

        saved_sort = QSettings().value(_SORT_KEY, _DEFAULT_SORT, type=str)
        self._set_sort(saved_sort if saved_sort in SORTS else _DEFAULT_SORT, persist=False)
        saved = QSettings().value(_VIEW_KEY, _DEFAULT_VIEW, type=str)
        self._set_view(saved if saved in ('gallery', 'table') else _DEFAULT_VIEW, persist=False)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.facet_pane)
        body.addWidget(self.stack, stretch=1)
        body.addWidget(self.inspector)

        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        wl.addWidget(toolbar)
        wl.addLayout(body, stretch=1)
        self.filter_edit.textChanged.connect(self._on_text)
        return wrap

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('RecToolbar')
        bar.setStyleSheet(f'QFrame#RecToolbar {{ background: #ffffff; border-bottom: 1px solid {_BORDER}; }}'
                          f' QLabel {{ color: {_KALE}; }}')
        title = QLabel('Recipes')
        title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')

        field = QFrame()
        field.setObjectName('RecFilter')
        field.setStyleSheet(f'QFrame#RecFilter {{ border: 1px solid {_FIELD_BORDER}; border-radius: 4px;'
                            ' background: #ffffff; }')
        field.setMaximumWidth(420)
        fl = QHBoxLayout(field)
        fl.setContentsMargins(10, 2, 10, 2)
        glass = QLabel('⌕')
        glass.setStyleSheet(f'color: {_MUTED}; font-size: 15px;')
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter by name, format or allergen')
        self.filter_edit.setFrame(False)
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setStyleSheet(f'border: 0; background: transparent; color: {_KALE}; min-height: 28px;')
        kbd = QLabel('Ctrl+F')
        kbd.setStyleSheet(f'color: {_MUTED}; font-family: {_MONO}; font-size: 12px;')
        fl.addWidget(glass)
        fl.addWidget(self.filter_edit, stretch=1)
        fl.addWidget(kbd)

        self.count_label = QLabel('')
        self.count_label.setStyleSheet(f'color: {_MUTED};')

        sort_label = QLabel('Sort')
        sort_label.setStyleSheet(f'color: {_MUTED};')
        self.sort_combo = QComboBox()
        for key, (label, _fn) in SORTS.items():
            self.sort_combo.addItem(label, key)
        self.sort_combo.setStyleSheet(f'QComboBox {{ min-height: 30px; padding: 0 8px; color: {_KALE};'
                                      f' border: 1px solid {_FIELD_BORDER}; border-radius: 4px; background: #ffffff; }}')
        self.sort_combo.activated.connect(lambda i: self._set_sort(self.sort_combo.itemData(i)))

        views = QFrame()
        views.setObjectName('ViewSwitch')
        views.setStyleSheet(f'''
            QFrame#ViewSwitch {{ border: 1px solid {_FIELD_BORDER}; border-radius: 8px; }}
            QFrame#ViewSwitch QPushButton {{ border: 0; padding: 0 12px; min-height: 32px;
                background: #ffffff; color: {_KALE}; }}
            QFrame#ViewSwitch QPushButton:checked {{ background: {_ROMAINE}; color: #ffffff;
                font-weight: 600; }}
        ''')
        vl = QHBoxLayout(views)
        vl.setContentsMargins(1, 1, 1, 1)
        vl.setSpacing(0)
        self._view_group = QButtonGroup(self)
        self._view_buttons = {}
        for key, label in (('gallery', 'Wedges'), ('table', 'Table')):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(lambda _c=False, k=key: self._set_view(k))
            self._view_group.addButton(btn)
            self._view_buttons[key] = btn
            vl.addWidget(btn)

        new_btn = QPushButton('New recipe   Ctrl+N')
        new_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 16px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        new_btn.clicked.connect(self.newRecipeRequested.emit)

        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 10, 20, 10)
        row.setSpacing(16)
        row.addWidget(title)
        row.addWidget(field, stretch=1)
        row.addWidget(self.count_label)
        row.addStretch()
        row.addWidget(sort_label)
        row.addWidget(self.sort_combo)
        row.addWidget(views)
        row.addWidget(new_btn)
        return bar

    def _build_table(self):
        table = QTableView()
        table.setModel(self.proxy)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        table.setSortingEnabled(True)
        table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._after_filter())
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setStyleSheet(f'''
            QTableView {{ background: #ffffff; border: 0; border-radius: 8px; color: {_KALE};
                selection-background-color: #fff1da; selection-color: {_KALE}; }}
            QTableView::item {{ border-top: 1px solid #f3ece0; padding: 0 8px; }}
            QHeaderView::section {{ background: #ffffff; color: {_MUTED}; border: 0;
                border-bottom: 1px solid {_BORDER}; padding: 8px 8px; font-size: 11px;
                font-weight: 600; }}
        ''')
        cols = self.source_model.COLUMNS
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        for name, width in (('TagName', 110), ('Cost', 84), ('FoodCostPct', 92),
                            ('Calories', 80), ('Components', 100)):
            header.setSectionResizeMode(cols.index(name), QHeaderView.Interactive)
            table.setColumnWidth(cols.index(name), width)
        header.setSectionResizeMode(cols.index('Name'), QHeaderView.Stretch)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_table_context_menu)
        table.doubleClicked.connect(self._on_table_activated)
        table.selectionModel().currentRowChanged.connect(self._on_current_changed)
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

    def selected_recipe_id(self):
        '''The recipe in the current tab, or the Library's selection.'''
        editor = self.editor_tabs.current_editor()
        return editor.recipe_id if editor is not None else self._selected_id

    def select_recipe(self, recipe_id):
        '''Select a recipe in the Library (after a refresh lands it).'''
        self._restore_id = recipe_id
        self._selected_id = recipe_id

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

    # --- view, sort, filtering -----------------------------------------

    def _set_view(self, name, persist=True):
        self._view_buttons[name].setChecked(True)
        self.stack.setCurrentIndex(0 if name == 'gallery' else 1)
        if persist:
            QSettings().setValue(_VIEW_KEY, name)
        self._after_filter()
        if self._selected_id is not None:
            self._select_id(self._selected_id)

    def _set_sort(self, key, persist=True):
        self.sort_combo.setCurrentIndex(self.sort_combo.findData(key))
        self.gallery.set_sort(key)
        self.table.horizontalHeader().blockSignals(True)
        self.proxy.sort_by(key)
        self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.table.horizontalHeader().blockSignals(False)
        if persist:
            QSettings().setValue(_SORT_KEY, key)
        self._after_filter()

    def _on_text(self, text):
        self.proxy.setFilterText(text)
        self._after_filter()

    def _apply_facets(self):
        self.proxy.set_facets(*self.facet_pane.selection())
        self._after_filter()

    def _after_filter(self):
        if not hasattr(self, 'count_label'):
            return
        self.gallery.set_row_filter(self.proxy.accepts_row)
        shown, total = self.proxy.rowCount(), self.source_model.rowCount()
        if self.stack.currentWidget() is self.gallery:
            how = 'grouped by format'
        else:
            col = self.table.horizontalHeader().sortIndicatorSection()
            label = (self.source_model.HEADERS[self.source_model.COLUMNS[col]] if col >= 0
                     else SORTS[self.sort_combo.currentData() or _DEFAULT_SORT][0])
            how = 'sorted by ' + label.lower()
        self.count_label.setText(f'{shown} of {total} · {how}')
        # Keep the inspector on a visible recipe.
        if self._selected_id is not None and not self._select_id(self._selected_id):
            self._select_first()

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self._sync_to_model()

    def _on_model_reset(self):
        if self.isVisible():
            self._sync_to_model()
        else:
            self._stale = True

    def _sync_to_model(self):
        self._stale = False
        self.facet_pane.set_library(self.source_model.rows())
        self.proxy.set_facets(*self.facet_pane.selection())
        self._after_filter()
        QTimer.singleShot(0, self._restore_selection)

    def _remember_selection(self):
        self._restore_id = self._restore_id or self._selected_id

    def _restore_selection(self):
        target = self._restore_id or self._selected_id
        self._restore_id = None
        if target is None or not self._select_id(target):
            self._select_first()
        else:
            self._update_inspector()

    # --- selection -----------------------------------------------------

    def _select_id(self, recipe_id):
        '''Select by id in the table and gallery. False if it's filtered
        out or gone.'''
        src_row = self.source_model.row_for_id(recipe_id)
        if src_row < 0:
            return False
        idx = self.proxy.mapFromSource(self.source_model.index(src_row, 0))
        if not idx.isValid():
            return False
        current = self.table.currentIndex()
        if not current.isValid() or current.row() != idx.row():
            self.table.selectionModel().setCurrentIndex(
                idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        else:
            self._set_selected(recipe_id)
        self.table.scrollTo(idx)
        return True

    def _select_first(self):
        if self.stack.currentWidget() is self.gallery and self.gallery.visible_ids():
            self._select_id(self.gallery.visible_ids()[0])
        elif self.proxy.rowCount():
            self.table.selectionModel().setCurrentIndex(
                self.proxy.index(0, 0), QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        else:
            self._selected_id = None
            self.gallery.set_selected_id(None)
            self.inspector.show_recipe(None)

    def _on_current_changed(self, current, _previous):
        if current.isValid():
            self._set_selected(self.source_model.id_at_row(self.proxy.mapToSource(current).row()))

    def _set_selected(self, recipe_id):
        changed = recipe_id != self.inspector.current_id()
        self._selected_id = recipe_id
        self.gallery.set_selected_id(recipe_id)
        if changed:
            # Coalesce: holding ↓ updates the inspector once you pause.
            self._inspect_timer.start()

    def _update_inspector(self):
        src_row = self.source_model.row_for_id(self._selected_id) if self._selected_id else -1
        self.inspector.show_recipe(self.source_model.row_dict(src_row) if src_row >= 0 else None)

    def _on_gallery_clicked(self, recipe_id):
        self._select_id(recipe_id)
        # Give the Library focus so Enter / Space act on the selection.
        self.gallery.scroll.setFocus()

    def _open_id(self, recipe_id):
        if recipe_id is not None and self.source_model.row_for_id(recipe_id) >= 0:
            self.recipeIdActivated.emit(recipe_id)
            self.open_in_editor(recipe_id)

    def _on_table_activated(self, view_index):
        if view_index.isValid():
            self.rowActivated.emit(self.proxy.mapToSource(view_index).row())

    def _show_table_context_menu(self, point):
        view_index = self.table.indexAt(point)
        if view_index.isValid():
            rid = self.source_model.id_at_row(self.proxy.mapToSource(view_index).row())
            self._show_context_menu(rid, self.table.viewport().mapToGlobal(point))

    def _show_context_menu(self, recipe_id, global_pos):
        src_row = self.source_model.row_for_id(recipe_id)
        if src_row < 0:
            return
        menu = QMenu(self)
        for label, handler in self._context_actions:
            if label is None:
                menu.addSeparator()
                continue
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, r=src_row, h=handler: h(r))
        menu.exec(global_pos)

    def _toggle_tray_for_current(self):
        '''Space: on a recipe tab it toggles that recipe; on the Library
        the selected one.'''
        if self._compare_tray is None:
            return
        rid = self.selected_recipe_id()
        if rid is not None:
            self._compare_tray.toggle(rid)
