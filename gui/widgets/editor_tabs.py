'''QTabWidget that manages a set of open RecipeEditWidget instances.

Each tab is one recipe open for editing. Opening a recipe that's
already open just switches to its tab; closing the last tab emits
`allClosed` so the containing workspace can switch back to its
library view.

Keyboard: ⌘W closes the current tab, ⌃Tab cycles to the next.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QTabWidget

from gui.dialogs.recipe_edit import RecipeEditWidget


class EditorTabs(QTabWidget):
    allClosed = Signal()
    recipeOpened = Signal(int)
    recipeDeleted = Signal(int)   # a tab's recipe was deleted; parent should refresh its models

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self.tabCloseRequested.connect(self.close_tab)

        # ⌘W closes current, ⌃Tab cycles. Scoped so other places don't
        # intercept — Ctrl+W elsewhere might legitimately mean something
        # different (close window). Here it closes the tab.
        close_sc = QShortcut(QKeySequence('Ctrl+W'), self)
        close_sc.setContext(Qt.WidgetWithChildrenShortcut)
        close_sc.activated.connect(self._close_current)
        next_sc = QShortcut(QKeySequence('Ctrl+Tab'), self)
        next_sc.setContext(Qt.WidgetWithChildrenShortcut)
        next_sc.activated.connect(self._cycle_tab)

    # --- opening -------------------------------------------------------

    def open_recipe(self, recipe_id):
        '''If this recipe is already open, switch to its tab. Otherwise
        build a RecipeEditWidget and append it. Returns the final tab
        index.'''
        existing = self._index_of_recipe(recipe_id)
        if existing >= 0:
            self.setCurrentIndex(existing)
            return existing
        widget = RecipeEditWidget(recipe_id, parent=self)
        widget.titleChanged.connect(
            lambda name, w=widget: self._on_title_changed(w, name)
        )
        widget.recipeDeleted.connect(
            lambda _rid, w=widget: self._on_recipe_deleted(w, _rid)
        )
        idx = self.addTab(widget, widget.title())
        self.setCurrentIndex(idx)
        self.recipeOpened.emit(recipe_id)
        return idx

    # --- closing -------------------------------------------------------

    def close_tab(self, index):
        '''Flush pending edits via widget.close_requested(), then remove
        the tab. Fires allClosed if that was the last one.'''
        widget = self.widget(index)
        if widget is None:
            return
        if not widget.close_requested():
            # Future: a false return will mean "I have unsaved work,
            # please don't close me". Not reachable today (editor
            # auto-commits every edit).
            return
        self.removeTab(index)
        widget.deleteLater()
        if self.count() == 0:
            self.allClosed.emit()

    def close_all(self):
        '''Walk and close every tab, flushing each. Called by the parent
        on tear-down (window close) to ensure cost snapshots stamp.'''
        while self.count() > 0:
            self.close_tab(0)

    def _close_current(self):
        if self.currentIndex() >= 0:
            self.close_tab(self.currentIndex())

    def _cycle_tab(self):
        n = self.count()
        if n > 1:
            self.setCurrentIndex((self.currentIndex() + 1) % n)

    # --- internal ------------------------------------------------------

    def _index_of_recipe(self, recipe_id):
        for i in range(self.count()):
            w = self.widget(i)
            if getattr(w, 'recipe_id', None) == recipe_id:
                return i
        return -1

    def _on_title_changed(self, widget, name):
        idx = self.indexOf(widget)
        if idx >= 0:
            self.setTabText(idx, name)

    def _on_recipe_deleted(self, widget, recipe_id):
        '''The widget's _on_delete already removed the row from the DB
        and marked itself not-to-snapshot. Just remove the tab —
        close_requested would otherwise try to re-read the gone row.'''
        idx = self.indexOf(widget)
        if idx >= 0:
            self.removeTab(idx)
            widget.deleteLater()
        self.recipeDeleted.emit(recipe_id)
        if self.count() == 0:
            self.allClosed.emit()

    def handle_external_delete(self, recipe_id):
        '''Called when a recipe is deleted from outside the editor
        (library row context menu, bulk delete, etc.). Finds any
        matching open tab, flags its widget as deleted so tear-down
        skips the gone-row UPDATE paths, and removes the tab.'''
        idx = self._index_of_recipe(recipe_id)
        if idx < 0:
            return
        widget = self.widget(idx)
        widget.mark_deleted()
        self.removeTab(idx)
        widget.deleteLater()
        if self.count() == 0:
            self.allClosed.emit()

    # --- state helpers -------------------------------------------------

    def open_recipe_ids(self):
        '''List of recipe ids currently open in tabs, in tab order.
        Useful for persisting + restoring the editor state across
        app launches (not wired yet).'''
        return [self.widget(i).recipe_id for i in range(self.count())]
