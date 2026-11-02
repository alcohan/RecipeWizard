'''The Recipes place's tab strip: a pinned Library tab followed by one
tab per open recipe (a RecipeEditWidget).

Library is always tab 0 and can't be closed, so home and every open
recipe sit side by side. Opening a recipe that's already open just
switches to its tab. Closing a recipe tab with unsaved changes asks
first (the widget's close_requested decides).

Keyboard: Ctrl+W closes the current recipe tab, Ctrl+Tab cycles
through every tab including Library, Ctrl+0 jumps to Library (the
main window owns that shortcut via its View menu).
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QTabBar, QTabWidget, QToolButton, QWidget,
)

from gui.dialogs.recipe_edit import RecipeEditWidget


LIBRARY_INDEX = 0


class EditorTabs(QTabWidget):
    recipeOpened = Signal(int)
    recipeDeleted = Signal(int)   # a tab's recipe was deleted; parent should refresh its models
    recipeSaved = Signal(int)     # a tab saved; parent should refresh its models
    newTabRequested = Signal()    # the "+" button
    currentEditorChanged = Signal(object)  # RecipeEditWidget or None (Library)
    dirtyChanged = Signal()       # any tab's unsaved-edit count changed

    def __init__(self, library_widget, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self.tabCloseRequested.connect(self.close_tab)

        self.addTab(library_widget, 'Library')
        # Pinned: no close button on the Library tab.
        self.tabBar().setTabButton(LIBRARY_INDEX, QTabBar.RightSide, None)
        self.tabBar().setTabButton(LIBRARY_INDEX, QTabBar.LeftSide, None)

        plus = QToolButton()
        plus.setText('+')
        plus.setToolTip('New recipe (Ctrl+N)')
        plus.setAutoRaise(True)
        plus.clicked.connect(self.newTabRequested.emit)
        self.setCornerWidget(_TabCorner(plus), Qt.TopRightCorner)

        self.currentChanged.connect(
            lambda _i: self.currentEditorChanged.emit(self.current_editor())
        )

        # Ctrl+W closes current, Ctrl+Tab cycles. Scoped so other places
        # don't intercept.
        close_sc = QShortcut(QKeySequence('Ctrl+W'), self)
        close_sc.setContext(Qt.WidgetWithChildrenShortcut)
        close_sc.activated.connect(self.close_current)
        next_sc = QShortcut(QKeySequence('Ctrl+Tab'), self)
        next_sc.setContext(Qt.WidgetWithChildrenShortcut)
        next_sc.activated.connect(self._cycle_tab)

    # --- opening -------------------------------------------------------

    def open_recipe(self, recipe_id):
        '''If this recipe is already open, switch to its tab. Otherwise
        build a RecipeEditWidget and append it. Returns the tab index.'''
        existing = self._index_of_recipe(recipe_id)
        if existing >= 0:
            self.setCurrentIndex(existing)
            return existing
        widget = RecipeEditWidget(recipe_id, parent=self)
        widget.titleChanged.connect(lambda _name, w=widget: self._sync_tab_text(w))
        widget.modifiedChanged.connect(lambda _m, w=widget: self._sync_tab_text(w))
        widget.dirtyCountChanged.connect(lambda _n: self.dirtyChanged.emit())
        widget.saved.connect(self.recipeSaved.emit)
        widget.recipeDeleted.connect(
            lambda _rid, w=widget: self._on_recipe_deleted(w, _rid)
        )
        idx = self.addTab(widget, widget.title())
        self.setCurrentIndex(idx)
        self.recipeOpened.emit(recipe_id)
        return idx

    def show_library(self):
        self.setCurrentIndex(LIBRARY_INDEX)

    def set_library_count(self, n):
        self.setTabText(LIBRARY_INDEX, f'Library  {n}')

    # --- closing -------------------------------------------------------

    def close_tab(self, index):
        '''Ask the widget to close (it may prompt about unsaved edits),
        then remove the tab. Returns False if the user cancelled.'''
        if index == LIBRARY_INDEX:
            return True
        widget = self.widget(index)
        if widget is None:
            return True
        self.setCurrentIndex(index)
        if not widget.close_requested():
            return False
        self.removeTab(index)
        widget.deleteLater()
        self.dirtyChanged.emit()
        return True

    def close_all(self):
        '''Close every recipe tab, left to right. Stops and returns
        False at the first one the user refuses to close.'''
        while self.count() > 1:
            if not self.close_tab(1):
                return False
        return True

    def close_current(self):
        if self.currentIndex() > LIBRARY_INDEX:
            self.close_tab(self.currentIndex())

    def _cycle_tab(self):
        n = self.count()
        if n > 1:
            self.setCurrentIndex((self.currentIndex() + 1) % n)

    # --- internal ------------------------------------------------------

    def _index_of_recipe(self, recipe_id):
        for i in range(1, self.count()):
            if getattr(self.widget(i), 'recipe_id', None) == recipe_id:
                return i
        return -1

    def _sync_tab_text(self, widget):
        idx = self.indexOf(widget)
        if idx >= 0:
            # Bullet marks unsaved edits, as in the canvas tab strip.
            self.setTabText(idx, widget.title() + ('  •' if widget.modified else ''))

    def _remove_widget(self, widget):
        idx = self.indexOf(widget)
        if idx >= 0:
            self.removeTab(idx)
            widget.deleteLater()
        self.dirtyChanged.emit()

    def _on_recipe_deleted(self, widget, recipe_id):
        '''The widget's _on_delete already removed the row from the DB
        and marked itself not-to-snapshot. Just remove the tab.'''
        self._remove_widget(widget)
        self.recipeDeleted.emit(recipe_id)

    def handle_external_delete(self, recipe_id):
        '''Called when a recipe is deleted from outside the editor
        (library row context menu, etc.). Flags the widget as deleted
        so tear-down skips the gone-row paths, and removes the tab.'''
        idx = self._index_of_recipe(recipe_id)
        if idx < 0:
            return
        widget = self.widget(idx)
        widget.mark_deleted()
        self._remove_widget(widget)

    # --- state helpers -------------------------------------------------

    def current_editor(self):
        '''The RecipeEditWidget in the current tab, or None on Library.'''
        idx = self.currentIndex()
        return self.widget(idx) if idx > LIBRARY_INDEX else None

    def editors(self):
        return [self.widget(i) for i in range(1, self.count())]

    def open_recipe_ids(self):
        '''Recipe ids open in tabs, in tab order — persisted so tabs
        survive restarts.'''
        return [w.recipe_id for w in self.editors()]


class _TabCorner(QWidget):
    '''Right-hand corner of the tab strip: the "+" button and a muted
    keyboard hint.'''

    def __init__(self, plus_button, parent=None):
        super().__init__(parent)
        hint = QLabel('Ctrl+Tab next tab · Ctrl+W close · Ctrl+0 Library')
        hint.setStyleSheet('color: #55624c; font-size: 11px;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(plus_button)
        layout.addWidget(hint)
