'''Ingredients place, per the Framework canvas: a toolbar (title,
filter, "N of M", Gallery/Table, New ingredient), the filter pane on the
left, the table or gallery in the middle, and the inspector on the
right.

Both views and the inspector read one IngredientsModel; the table goes
through IngredientsFacetProxy and the gallery uses the proxy's
accepts_row, so the two always show the same ingredients. Selection is
kept by ingredient id across model refreshes (an edit elsewhere doesn't
lose your place).

Emits `rowActivated(int)` (source row) for Edit, like before, plus
`newIngredientRequested`, `newPriceRequested(int)` and
`recipeRequested(int)` for the main window to route.
'''
from PySide6.QtCore import QItemSelectionModel, Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QPushButton, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from gui.models.ingredients_facet_proxy import IngredientsFacetProxy
from gui.widgets.ingredient_gallery import IngredientGallery
from gui.widgets.ingredient_inspector import IngredientInspector
from gui.widgets.ingredient_table import (
    ChangeDelegate, NameDelegate, PlainDelegate, TwoLineDelegate,
)
from gui.widgets.ingredients_facet_pane import IngredientsFacetPane
from gui.widgets.toolbar_controls import SegmentedSwitch


_SETTINGS_KEY = 'ingredients/view'
_DEFAULT_VIEW = 'table'

_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"


class IngredientsTab(QWidget):
    rowActivated = Signal(int)  # source-model row index
    newIngredientRequested = Signal()
    newPriceRequested = Signal(int)   # ingredient id
    recipeRequested = Signal(int)     # recipe id
    importRequested = Signal()        # Import purchases…

    def __init__(self, source_model, context_actions, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions
        self._selected_id = None

        self._inspect_timer = QTimer(self)
        self._inspect_timer.setSingleShot(True)
        self._inspect_timer.setInterval(60)
        self._inspect_timer.timeout.connect(self._update_inspector)

        self.proxy = IngredientsFacetProxy(self)
        self.proxy.setSourceModel(source_model)

        toolbar = self._build_toolbar()
        self.facets = IngredientsFacetPane()
        self.facets.changed.connect(self._apply_facets)
        self.table = self._build_table()
        self.gallery = IngredientGallery(source_model, context_actions=context_actions)
        # Single click selects (and fills the inspector); double-click
        # or Enter opens the editor — in both views.
        self.gallery.ingredientClicked.connect(self._on_gallery_clicked)
        self.gallery.ingredientActivated.connect(self.rowActivated.emit)
        self.gallery.set_row_filter(self.proxy.accepts_row)
        self.inspector = IngredientInspector()
        self.inspector.editRequested.connect(self._edit_id)
        self.inspector.newPriceRequested.connect(self.newPriceRequested.emit)
        self.inspector.recipeRequested.connect(self.recipeRequested.emit)

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

        self.stack = QStackedWidget()
        self.stack.addWidget(self.gallery)
        self.stack.addWidget(table_wrap)
        saved = QSettings().value(_SETTINGS_KEY, _DEFAULT_VIEW, type=str)
        self._set_view(saved if saved in ('gallery', 'table') else _DEFAULT_VIEW, persist=False)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.facets)
        body.addWidget(self.stack, stretch=1)
        body.addWidget(self.inspector)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar)
        layout.addLayout(body, stretch=1)

        self.filter_edit.textChanged.connect(self._on_text)
        source_model.modelAboutToBeReset.connect(self._remember_selection)
        source_model.modelReset.connect(self._on_model_reset)
        # Lazy: the filter pane and inspector fill on first show, and a
        # model reset while hidden only marks them stale — the app starts
        # on Recipes and may never visit this place.
        self._stale = True

        # Enter opens the selected ingredient. (QAbstractItemView's
        # `activated` isn't used: on some styles it fires on a single
        # click, and a single click should only select.)
        # Scoped to the whole place (table, gallery, filter field), and
        # both Return and the keypad's Enter.
        for key in (Qt.Key_Return, Qt.Key_Enter):
            enter = QShortcut(QKeySequence(key), self)
            enter.setContext(Qt.WidgetWithChildrenShortcut)
            enter.activated.connect(lambda: self._edit_id(self._selected_id))

    # --- building ------------------------------------------------------

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName('IngToolbar')
        bar.setStyleSheet(f'QFrame#IngToolbar {{ background: #ffffff; border-bottom: 1px solid {_BORDER}; }}'
                          f' QLabel {{ color: {_KALE}; }}')
        title = QLabel('Ingredients')
        title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')

        field = QFrame()
        field.setObjectName('IngFilter')
        field.setStyleSheet(f'QFrame#IngFilter {{ border: 1px solid {_FIELD_BORDER}; border-radius: 4px;'
                            ' background: #ffffff; }')
        field.setMaximumWidth(420)
        fl = QHBoxLayout(field)
        fl.setContentsMargins(10, 2, 10, 2)
        glass = QLabel('⌕')
        glass.setStyleSheet(f'color: {_MUTED}; font-size: 15px;')
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter by name, supplier or allergen')
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

        self.view_switch = SegmentedSwitch([('gallery', 'Gallery'), ('table', 'Table')])
        self.view_switch.changed.connect(self._set_view)

        new_btn = QPushButton('New ingredient   Ctrl+Shift+N')
        new_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 16px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        new_btn.clicked.connect(self.newIngredientRequested.emit)

        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 10, 20, 10)
        row.setSpacing(16)
        row.addWidget(title)
        row.addWidget(field, stretch=1)
        row.addWidget(self.count_label)
        row.addStretch()
        import_btn = QPushButton('Import purchases…')
        import_btn.setToolTip('Ctrl+Shift+I')
        import_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {_FIELD_BORDER};'
            f' border-radius: 8px; background: #ffffff; color: {_KALE}; }}'
            ' QPushButton:hover { background: #f3ece0; }')
        import_btn.clicked.connect(self.importRequested.emit)

        row.addWidget(self.view_switch)
        row.addWidget(import_btn)
        row.addWidget(new_btn)
        return bar

    def _build_table(self):
        '''Virtualized table: fixed 44 px rows, delegates paint
        everything (no per-cell widgets), sortable headers.'''
        table = QTableView()
        table.setModel(self.proxy)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # Unsorted until a header is clicked: source order is category
        # order, then name ("sorted by category"). The "no sort"
        # indicator goes on first — enabling sorting sorts by the
        # indicator's column, which would otherwise be column 0.
        table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        table.setSortingEnabled(True)
        table.horizontalHeader().sortIndicatorChanged.connect(lambda *_: self._after_filter())
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(44)
        table.setStyleSheet(f'''
            QTableView {{ background: #ffffff; border: 0; border-radius: 8px; color: {_KALE};
                selection-background-color: #fff1da; selection-color: {_KALE}; }}
            QTableView::item {{ border-top: 1px solid #f3ece0; }}
            QHeaderView::section {{ background: #ffffff; color: {_MUTED}; border: 0;
                border-bottom: 1px solid {_BORDER}; padding: 8px 8px; font-size: 11px;
                font-weight: 600; }}
        ''')
        cols = self.source_model.COLUMNS
        table.setItemDelegateForColumn(cols.index('Name'), NameDelegate(table))
        table.setItemDelegateForColumn(cols.index('Unit'), TwoLineDelegate(table))
        table.setItemDelegateForColumn(cols.index('Change'), ChangeDelegate(table))
        table.setItemDelegateForColumn(cols.index('Cost'), PlainDelegate(table, bold=True))
        table.setItemDelegateForColumn(cols.index('Supplier'), PlainDelegate(table, muted=True))
        for name in ('Calories', 'Allergens', 'UsedIn'):
            table.setItemDelegateForColumn(cols.index(name), PlainDelegate(table))
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        # Name takes the slack but never drops below a readable width;
        # past that the table scrolls sideways instead of crushing names.
        header.setMinimumSectionSize(48)
        for name, width in (('Unit', 104), ('Cost', 84), ('Change', 92), ('Supplier', 110),
                            ('Calories', 56), ('Allergens', 110), ('UsedIn', 68)):
            header.setSectionResizeMode(cols.index(name), QHeaderView.Interactive)
            table.setColumnWidth(cols.index(name), width)
        self._fixed_width = sum(table.columnWidth(i) for i in range(len(cols)) if cols[i] != 'Name')
        header.setSectionResizeMode(cols.index('Name'), QHeaderView.Interactive)
        table.setColumnWidth(cols.index('Name'), 240)
        table.viewport().installEventFilter(self)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_table_context_menu)
        table.doubleClicked.connect(self._on_table_activated)
        table.selectionModel().currentRowChanged.connect(self._on_current_changed)
        return table

    def eventFilter(self, obj, event):
        # Name stretches into whatever width is left, down to 180 px.
        if obj is self.table.viewport() and event.type() == event.Type.Resize:
            name_col = self.source_model.COLUMNS.index('Name')
            self.table.setColumnWidth(name_col, max(180, obj.width() - self._fixed_width))
        return super().eventFilter(obj, event)

    # --- view + filtering ----------------------------------------------

    def _set_view(self, name, persist=True):
        self.view_switch.set_current(name)
        self.stack.setCurrentIndex(0 if name == 'gallery' else 1)
        if persist:
            QSettings().setValue(_SETTINGS_KEY, name)

    def _on_text(self, text):
        self.proxy.setFilterText(text)
        self._after_filter()

    def _apply_facets(self):
        self.proxy.set_facets(*self.facets.selection())
        self._after_filter()

    def _after_filter(self):
        self.gallery.set_row_filter(self.proxy.accepts_row)
        shown, total = self.proxy.rowCount(), self.source_model.rowCount()
        sorted_by = 'sorted by category' if self.table.horizontalHeader().sortIndicatorSection() < 0 \
            else 'sorted by ' + self.source_model.HEADERS[
                self.source_model.COLUMNS[self.table.horizontalHeader().sortIndicatorSection()]].lower()
        self.count_label.setText(f'{shown} of {total} · {sorted_by}')
        # Keep the inspector on a visible ingredient.
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
        self.facets.set_library(self.source_model.rows())
        self.proxy.set_facets(*self.facets.selection())
        self._after_filter()
        # Defer re-selection until the view has caught up with the reset.
        QTimer.singleShot(0, self._restore_selection)

    def _remember_selection(self):
        self._restore_id = self._selected_id

    def _restore_selection(self):
        target = getattr(self, '_restore_id', None) or self._selected_id
        self._restore_id = None
        if target is None or not self._select_id(target):
            self._select_first()

    # --- selection -----------------------------------------------------

    def _select_id(self, ingredient_id):
        src_row = self.source_model.row_for_id(ingredient_id)
        if src_row < 0:
            return False
        idx = self.proxy.mapFromSource(self.source_model.index(src_row, 0))
        if not idx.isValid():
            return False
        self.table.selectionModel().setCurrentIndex(
            idx, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        self.table.scrollTo(idx)
        return True

    def _select_first(self):
        if self.proxy.rowCount():
            self.table.selectionModel().setCurrentIndex(
                self.proxy.index(0, 0), QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        else:
            self._selected_id = None
            self.inspector.show_ingredient(None)

    def _on_current_changed(self, current, _previous):
        if not current.isValid():
            return
        src_row = self.proxy.mapToSource(current).row()
        self._selected_id = self.source_model.row_dict(src_row)['Id']
        self.gallery.set_selected_id(self._selected_id)
        # Coalesce: holding ↓ through the table updates the inspector
        # once you pause, not once per row (each update queries the
        # row's prices and usage).
        self._inspect_timer.start()

    def _update_inspector(self):
        src_row = self.source_model.row_for_id(self._selected_id) if self._selected_id else -1
        self.inspector.show_ingredient(self.source_model.row_dict(src_row) if src_row >= 0 else None)

    def _on_gallery_clicked(self, src_row):
        self._select_id(self.source_model.id_at_row(src_row))

    def _edit_id(self, ingredient_id):
        if ingredient_id is None:
            return
        src_row = self.source_model.row_for_id(ingredient_id)
        if src_row >= 0:
            self.rowActivated.emit(src_row)

    def _on_table_activated(self, view_index):
        if view_index.isValid():
            self.rowActivated.emit(self.proxy.mapToSource(view_index).row())

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
        '''Called by the main window's Ctrl+F shortcut.'''
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()
