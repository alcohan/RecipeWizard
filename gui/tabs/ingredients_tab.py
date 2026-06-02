'''Ingredients tab — filter + view toggle + action buttons, wrapping
a stacked (gallery, table) content area.

Emits the same `rowActivated(int)` source-row-index signal as the
original `_BrowsePane`, so MainWindow's handlers don't need to know
which view the user picked. The toggle's choice is persisted in
`QSettings("ingredients/view")`; gallery is the default for a fresh
install since it's friendlier for users browsing what they have.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLineEdit, QMenu,
    QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from gui.models.filter_proxy import MultiColumnFilterProxy
from gui.widgets.ingredient_gallery import IngredientGallery
from gui.widgets.tag_badge import TagBadgeCellDelegate
from gui.widgets.view_toggle import ViewToggle


_SETTINGS_KEY = 'ingredients/view'
_DEFAULT_VIEW = 'gallery'


class IngredientsTab(QWidget):
    rowActivated = Signal(int)  # source-model row index

    def __init__(self, source_model, context_actions, action_buttons, parent=None):
        super().__init__(parent)
        self.source_model = source_model
        self._context_actions = context_actions

        saved = QSettings().value(_SETTINGS_KEY, _DEFAULT_VIEW, type=str)
        initial_view = saved if saved in ('gallery', 'table') else _DEFAULT_VIEW

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('\U0001F50D  Filter ingredients…')
        self.filter_edit.setClearButtonEnabled(True)

        self.toggle = ViewToggle(
            modes=[('gallery', '⊞ Gallery'), ('table', '☰ Table')],
            current=initial_view,
        )
        self.toggle.viewChanged.connect(self._on_view_changed)

        self.gallery = IngredientGallery(source_model, context_actions=context_actions)
        self.gallery.ingredientActivated.connect(self.rowActivated.emit)

        self.table = self._build_table(source_model)

        # Both views share the same filter text. Table goes through the
        # proxy (multi-column search + sorting); gallery has a simpler
        # name-only filter applied directly.
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

    def _build_table(self, source_model):
        '''Construct the same virtualized table the original _BrowsePane
        used: row-based selection, sortable headers, alternating colors,
        fixed row height for smooth scroll, and the colored Tag-pill
        delegate. Context menu mirrors the gallery's.'''
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

        tag_col = source_model.COLUMNS.index('Tag')
        table.setItemDelegateForColumn(tag_col, TagBadgeCellDelegate(table))
        return table

    def _on_view_changed(self, name):
        self.stack.setCurrentIndex(0 if name == 'gallery' else 1)
        QSettings().setValue(_SETTINGS_KEY, name)

    def _on_table_activated(self, view_index):
        if not view_index.isValid():
            return
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
