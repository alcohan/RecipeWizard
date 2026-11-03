'''The Recipes place's tab strip: a pinned Library tab followed by one
tab per open recipe (a RecipeEditWidget).

Library is always tab 0 and can't be closed, so home and every open
recipe sit side by side. Opening a recipe that's already open just
switches to its tab. Closing a recipe tab with unsaved changes asks
first (the widget's close_requested decides).

Styled per the Framework canvas: a warm strip with 40 px tabs, the
current one lifted onto white. Each recipe tab carries a small wedge
of its recipe, an unsaved dot and its own ×; Library carries the
recipe count and sits a little apart, since it's pinned.

Keyboard: Ctrl+W closes the current recipe tab, Ctrl+Tab cycles
through every tab including Library, Ctrl+0 jumps to Library (the
main window owns that shortcut via its View menu).
'''
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QTabBar, QTabWidget, QToolButton, QWidget,
)

from gui.dialogs.recipe_edit import RecipeEditWidget
from gui.widgets.wedge_view import WedgeView


LIBRARY_INDEX = 0

_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_STRIP = '#efe9de'

_STYLE = f'''
    EditorTabs {{ background: {_STRIP}; }}
    EditorTabs::pane {{ border: 0; border-top: 1px solid {_BORDER}; top: -1px; }}
    EditorTabs::tab-bar {{ left: 16px; }}
    EditorTabs > QStackedWidget {{ background: #fffaf2; }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        height: 40px;
        padding: 0 8px 0 12px;
        margin: 8px 2px 0 0;
        border: 1px solid transparent;
        border-bottom: 0;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        background: transparent;
        color: {_MUTED};
        font-size: 14px;
    }}
    QTabBar::tab:first {{ margin-right: 12px; padding-right: 14px; }}
    QTabBar::tab:hover:!selected {{ background: #f7f1e6; }}
    QTabBar::tab:selected {{
        background: #ffffff;
        border-color: {_BORDER};
        color: {_KALE};
        font-weight: 600;
    }}
'''


class EditorTabs(QTabWidget):
    recipeOpened = Signal(int)
    recipeDeleted = Signal(int)   # a tab's recipe was deleted; parent should refresh its models
    recipeSaved = Signal(int)     # a tab saved; parent should refresh its models
    newTabRequested = Signal()    # the "+" button
    currentEditorChanged = Signal(object)  # RecipeEditWidget or None (Library)
    dirtyChanged = Signal()       # any tab's unsaved-edit count changed

    def __init__(self, library_widget, compare_tray=None, parent=None):
        super().__init__(parent)
        self._compare_tray = compare_tray
        # Close buttons are our own (_TabTail), so the unsaved dot can
        # sit beside the × the way the canvas draws it.
        self.setTabsClosable(False)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self.tabBar().setDrawBase(False)
        self.tabBar().setExpanding(False)

        self.addTab(library_widget, 'Library')
        # Pinned: a library glyph, no close button.
        glyph = QLabel('▦')
        glyph.setStyleSheet(f'color: {_ROMAINE}; font-size: 15px; background: transparent;')
        self.tabBar().setTabButton(LIBRARY_INDEX, QTabBar.LeftSide, _inset(glyph, left=6))
        self.tabBar().setTabButton(LIBRARY_INDEX, QTabBar.RightSide, None)
        self.setTabToolTip(LIBRARY_INDEX, 'Library (pinned) · Ctrl+0')

        plus = QToolButton()
        plus.setText('+')
        plus.setToolTip('New recipe (Ctrl+N)')
        plus.setAutoRaise(True)
        plus.setFixedSize(32, 32)
        plus.setStyleSheet(f'QToolButton {{ border: 0; border-radius: 6px; font-size: 18px;'
                           f' color: {_MUTED}; background: transparent; }}'
                           f' QToolButton:hover {{ background: #f7f1e6; color: {_KALE}; }}')
        plus.clicked.connect(self.newTabRequested.emit)
        self.setCornerWidget(_TabCorner(plus), Qt.TopRightCorner)

        self.currentChanged.connect(
            lambda _i: self.currentEditorChanged.emit(self.current_editor())
        )

        # Ctrl+W closes current, Ctrl+Tab / Ctrl+Shift+Tab cycle.
        # Window-wide, so they work wherever focus is (after a restart it
        # starts in the header, outside this widget); Qt skips window
        # shortcuts on hidden widgets, so other places aren't affected.
        for keys, handler in ((QKeySequence('Ctrl+W'), self.close_current),
                              (QKeySequence.NextChild, lambda: self._cycle_tab(1)),
                              (QKeySequence.PreviousChild, lambda: self._cycle_tab(-1))):
            sc = QShortcut(keys, self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(handler)

        # Middle-click closes a tab, like a browser.
        self.tabBar().installEventFilter(self)

    # --- opening -------------------------------------------------------

    def open_recipe(self, recipe_id):
        '''If this recipe is already open, switch to its tab. Otherwise
        build a RecipeEditWidget and append it. Returns the tab index.'''
        existing = self._index_of_recipe(recipe_id)
        if existing >= 0:
            self.setCurrentIndex(existing)
            return existing
        widget = RecipeEditWidget(recipe_id, compare_tray=self._compare_tray, parent=self)
        widget.libraryRequested.connect(self.show_library)
        widget.openRecipeRequested.connect(self.open_recipe)
        widget.titleChanged.connect(lambda _name, w=widget: self._sync_tab_text(w))
        widget.dirtyCountChanged.connect(lambda _n: self.dirtyChanged.emit())
        widget.saved.connect(self.recipeSaved.emit)
        widget.recipeDeleted.connect(
            lambda _rid, w=widget: self._on_recipe_deleted(w, _rid)
        )
        idx = self.addTab(widget, widget.title())
        bar = self.tabBar()
        # A small wedge of the recipe, redrawn as its components change.
        icon = WedgeView(recipe_id, size=24)
        icon.setStyleSheet('background: transparent;')
        widget.undo_stack.indexChanged.connect(lambda _i, v=icon: v.refresh())
        bar.setTabButton(idx, QTabBar.LeftSide, _inset(icon, left=6))
        tail = _TabTail(widget.title())
        tail.closeClicked.connect(lambda w=widget: self.close_tab(self.indexOf(w)))
        widget.modifiedChanged.connect(tail.set_unsaved)
        widget.titleChanged.connect(tail.set_title)
        bar.setTabButton(idx, QTabBar.RightSide, tail)
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
        previous = self.currentWidget()
        self.setCurrentIndex(index)
        if not widget.close_requested():
            return False
        self.removeTab(index)
        widget.deleteLater()
        # Closing a background tab (× or middle-click) keeps you where you were.
        if previous is not widget and self.indexOf(previous) >= 0:
            self.setCurrentWidget(previous)
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

    def _cycle_tab(self, step=1):
        n = self.count()
        if n > 1:
            self.setCurrentIndex((self.currentIndex() + step) % n)

    def eventFilter(self, obj, event):
        if (obj is self.tabBar() and event.type() == QEvent.MouseButtonRelease
                and event.button() == Qt.MiddleButton):
            index = obj.tabAt(event.position().toPoint())
            if index > LIBRARY_INDEX:
                self.close_tab(index)
            return True
        return super().eventFilter(obj, event)

    # --- internal ------------------------------------------------------

    def _index_of_recipe(self, recipe_id):
        for i in range(1, self.count()):
            if getattr(self.widget(i), 'recipe_id', None) == recipe_id:
                return i
        return -1

    def _sync_tab_text(self, widget):
        idx = self.indexOf(widget)
        if idx >= 0:
            self.setTabText(idx, widget.title())

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


def _inset(widget, left=0, right=0):
    '''Wrap a tab side widget so it sits clear of the tab's edge (tab
    padding in the stylesheet doesn't apply to side widgets).'''
    box = QWidget()
    box.setStyleSheet('background: transparent;')
    layout = QHBoxLayout(box)
    layout.setContentsMargins(left, 0, right, 0)
    layout.addWidget(widget)
    return box


class _TabTail(QWidget):
    '''Right side of a recipe tab: the unsaved dot (romaine, shown
    while the recipe has unsaved edits) and a × close button.'''

    closeClicked = Signal()

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: transparent;')
        # The dot always takes its space and only changes color: QTabBar
        # sizes side widgets once, so showing a hidden dot later would
        # squeeze the × out (and make the tab jump in width).
        self._dot = QLabel()
        self._dot.setFixedSize(8, 8)
        self.set_unsaved(False)
        self._close = QToolButton()
        self._close.setText('×')
        self._close.setFixedSize(20, 20)
        self._close.setAutoRaise(True)
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setStyleSheet(f'QToolButton {{ border: 0; border-radius: 4px; font-size: 15px;'
                                  f' color: {_MUTED}; background: transparent; }}'
                                  f' QToolButton:hover {{ background: {_STRIP}; color: {_KALE}; }}')
        self._close.clicked.connect(self.closeClicked.emit)
        self.set_title(title)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)   # keep the × off the tab's edge
        layout.setSpacing(6)
        layout.addWidget(self._dot)
        layout.addWidget(self._close)

    def set_unsaved(self, unsaved):
        self.unsaved = bool(unsaved)
        color = _ROMAINE if unsaved else 'transparent'
        self._dot.setStyleSheet(f'background: {color}; border-radius: 4px;')
        self._dot.setToolTip('Unsaved changes' if unsaved else '')

    def set_title(self, title):
        self._close.setToolTip(f'Close {title} (Ctrl+W)')


class _TabCorner(QWidget):
    '''Right-hand corner of the tab strip: the "+" button and a muted
    keyboard hint.'''

    def __init__(self, plus_button, parent=None):
        super().__init__(parent)
        self.setStyleSheet('background: transparent;')
        hint = QLabel('Ctrl+Tab next tab · Ctrl+W close · Ctrl+0 Library')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 16, 0)
        layout.setSpacing(12)
        layout.addWidget(plus_button)
        layout.addWidget(hint)
