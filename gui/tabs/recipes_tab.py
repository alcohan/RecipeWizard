'''Recipes place — filter + view toggle + action buttons wrapping a
stacked (wedge gallery, table) workspace. Modeled on IngredientsTab so
users switching between places get the same muscle memory for filter,
toggle, and context menus.

Gallery is the default view (users read wedges faster than table rows
when answering "which recipe"). The toggle choice persists under
QSettings('recipes/view').
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.widgets.recipe_gallery import RecipeGallery
from gui.widgets.view_toggle import ViewToggle


_SETTINGS_KEY = 'recipes/view'
_DEFAULT_VIEW = 'gallery'


class RecipesTab(QWidget):
    rowActivated = Signal(int)   # source-model row index — same shape as IngredientsTab
    recipeIdActivated = Signal(int)  # convenience: emits recipe id

    def __init__(self, source_model, context_actions, action_buttons,
                 compare_tray=None, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions
        self._compare_tray = compare_tray

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

        self.gallery = RecipeGallery(source_model)
        # RecipeGallery emits recipeClicked(recipe_id); translate to row
        # for parity with IngredientsTab, and keep the id-based signal
        # for callers who prefer it.
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

        layout = QVBoxLayout(self)
        layout.addLayout(header_row)
        layout.addWidget(self.stack, stretch=1)
        layout.addLayout(button_row)

        # Space toggles the currently-focused recipe in the compare
        # tray. Scoped to this place so Space elsewhere (inputs,
        # ingredients) is unaffected.
        if self._compare_tray is not None:
            space_sc = QShortcut(QKeySequence(Qt.Key_Space), self)
            space_sc.setContext(Qt.WidgetWithChildrenShortcut)
            space_sc.activated.connect(self._toggle_tray_for_current)

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

    def _on_view_changed(self, name):
        self.stack.setCurrentIndex(0 if name == 'gallery' else 1)
        QSettings().setValue(_SETTINGS_KEY, name)

    def _on_table_activated(self, view_index):
        if not view_index.isValid():
            return
        self.rowActivated.emit(self.proxy.mapToSource(view_index).row())

    def _emit_row_for_recipe(self, recipe_id):
        '''Look up a recipe's source-model row from its id so the
        gallery can emit the same rowActivated signal as the table.
        Matches IngredientsTab's semantics so the parent's handlers
        don't branch on view.'''
        model = self.source_model
        for i in range(model.rowCount()):
            if model.id_at_row(i) == recipe_id:
                self.rowActivated.emit(i)
                return

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
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()

    def _toggle_tray_for_current(self):
        '''Space handler. Figures out which recipe the user means — the
        selected table row, or the recipe whose card has focus — and
        toggles it in the tray.'''
        if self._compare_tray is None:
            return
        rid = None
        # Table view: use the current selection, mapped back to source.
        if self.stack.currentWidget() is self.table:
            idx = self.table.currentIndex()
            if idx.isValid():
                src_row = self.proxy.mapToSource(idx).row()
                rid = self.source_model.id_at_row(src_row)
        # Gallery view: Space on an unfocused gallery is a no-op for
        # now; cards don't take focus. A checkbox lives on each card
        # in a future commit; the keyboard path is table-only until
        # then.
        if rid is not None:
            self._compare_tray.toggle(rid)
