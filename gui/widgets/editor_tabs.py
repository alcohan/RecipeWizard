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

Library is still tab 0 (so indexes mean the same everywhere), but its
tab is hidden and drawn instead by a fixed button left of the tab bar.
Recipe names are shortened to a fixed width (full name in the
tooltip), so with many recipes open the tab bar scrolls rather than
squeezing names to a letter, and Library always stays in view. The
▾ in the corner lists every open recipe.

Keyboard: Ctrl+W closes the current recipe tab, Ctrl+Tab cycles
through every tab including Library, Ctrl+0 jumps to Library (the
main window owns that shortcut via its View menu).
'''
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QTabBar, QTabWidget, QToolButton, QWidget,
)
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap

from gui.widgets.text_fit import elide, literal

from gui.dialogs.recipe_edit import RecipeEditWidget
from gui.widgets.wedge_view import WedgeView


LIBRARY_INDEX = 0

_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_STRIP = '#efe9de'
_TAB_TEXT_MAX = 150     # px of recipe name on a tab; longer names end in …

_STYLE = f'''
    EditorTabs {{ background: {_STRIP}; }}
    EditorTabs::pane {{ border: 0; border-top: 1px solid {_BORDER}; top: -1px; }}
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

    def __init__(self, library_widget, parent=None):
        super().__init__(parent)
        # Close buttons are our own (_TabTail), so the unsaved dot can
        # sit beside the × the way the canvas draws it.
        self.setTabsClosable(False)
        self.setDocumentMode(True)
        self.setUsesScrollButtons(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_STYLE)
        self.tabBar().setDrawBase(False)
        self.tabBar().setExpanding(False)
        # Names are shortened by _tab_text, not by Qt: Qt's eliding
        # squeezes every tab to a letter or two once many are open.
        self.tabBar().setElideMode(Qt.ElideNone)

        self.addTab(library_widget, 'Library')
        # Pinned: the tab itself is hidden; the button left of the bar
        # stands in for it, so it never shrinks or scrolls away.
        self.tabBar().setTabVisible(LIBRARY_INDEX, False)
        self.library_button = _LibraryButton()
        self.library_button.clicked.connect(self.show_library)
        self.setCornerWidget(_inset(self.library_button, left=16, right=10), Qt.TopLeftCorner)
        self.setCurrentIndex(LIBRARY_INDEX)

        plus = QToolButton()
        plus.setText('+')
        plus.setToolTip('New recipe (Ctrl+N)')
        plus.setAutoRaise(True)
        plus.setFixedSize(32, 32)
        plus.setStyleSheet(f'QToolButton {{ border: 0; border-radius: 6px; font-size: 18px;'
                           f' color: {_MUTED}; background: transparent; }}'
                           f' QToolButton:hover {{ background: #f7f1e6; color: {_KALE}; }}')
        plus.clicked.connect(self.newTabRequested.emit)
        # Every open recipe, for when there are more than fit.
        self.list_button = QToolButton()
        self.list_button.setText('▾')
        self.list_button.setToolTip('Open recipes')
        self.list_button.setFixedSize(32, 32)
        self.list_button.setPopupMode(QToolButton.InstantPopup)
        self.list_button.setStyleSheet(plus.styleSheet() + ' QToolButton::menu-indicator { image: none; }')
        menu = QMenu(self.list_button)
        menu.aboutToShow.connect(lambda m=menu: self._fill_tab_menu(m))
        self.list_button.setMenu(menu)
        self.list_button.hide()
        self.setCornerWidget(_TabCorner(self.list_button, plus), Qt.TopRightCorner)

        self.currentChanged.connect(
            lambda _i: self.currentEditorChanged.emit(self.current_editor())
        )
        self.currentChanged.connect(lambda i: self.library_button.setChecked(i == LIBRARY_INDEX))
        self.library_button.setChecked(True)

        # Ctrl+W closes current, Ctrl+Tab / Ctrl+Shift+Tab cycle.
        # Window-wide, so they work wherever focus is (after a restart it
        # starts in the header, outside this widget); Qt skips window
        # shortcuts on hidden widgets, so other places aren't affected.
        # Backward needs Ctrl+Shift+Tab as well as Qt's Ctrl+Shift+Backtab:
        # the key can arrive either way, and one no shortcut takes falls
        # to QTabWidget's own cycling, which skips the hidden Library tab.
        previous = [QKeySequence('Ctrl+Shift+Tab')] + QKeySequence.keyBindings(QKeySequence.PreviousChild)
        for keys, handler in (([QKeySequence('Ctrl+W')], self.close_current),
                              (QKeySequence.keyBindings(QKeySequence.NextChild), lambda: self._cycle_tab(1)),
                              (previous, lambda: self._cycle_tab(-1))):
            sc = QShortcut(self)
            sc.setKeys(keys)
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
        widget = RecipeEditWidget(recipe_id, parent=self)
        widget.libraryRequested.connect(self.show_library)
        widget.openRecipeRequested.connect(self.open_recipe)
        widget.titleChanged.connect(lambda _name, w=widget: self._sync_tab_text(w))
        widget.dirtyCountChanged.connect(lambda _n: self.dirtyChanged.emit())
        widget.saved.connect(self.recipeSaved.emit)
        widget.recipeDeleted.connect(
            lambda _rid, w=widget: self._on_recipe_deleted(w, _rid)
        )
        idx = self.addTab(widget, _tab_text(widget.title()))
        self.setTabToolTip(idx, widget.title())
        bar = self.tabBar()
        # A small wedge of the recipe, redrawn as its components change.
        icon = WedgeView(recipe_id, size=24)
        _clear_background(icon)
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

    def tabInserted(self, index):
        super().tabInserted(index)
        self._sync_list_button()

    def tabRemoved(self, index):
        super().tabRemoved(index)
        self._sync_list_button()

    def _sync_list_button(self):
        # Shown from two open recipes on (tabInserted runs for Library
        # before the button exists).
        if hasattr(self, 'list_button'):
            self.list_button.setVisible(self.count() > 2)

    def _fill_tab_menu(self, menu):
        menu.clear()
        current = self.currentIndex()
        for i in range(1, self.count()):
            w = self.widget(i)
            dirty = getattr(self.tabBar().tabButton(i, QTabBar.RightSide), 'unsaved', False)
            act = menu.addAction(literal(w.title()) + ('  •' if dirty else ''))
            act.setCheckable(True)
            act.setChecked(i == current)
            act.triggered.connect(lambda _c=False, w=w: self.setCurrentWidget(w))

    def show_library(self):
        self.setCurrentIndex(LIBRARY_INDEX)

    def set_library_count(self, n):
        self.setTabText(LIBRARY_INDEX, f'Library  {n}')
        self.library_button.set_count(n)

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
        elif self.count() == 1:
            self.setCurrentIndex(LIBRARY_INDEX)
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
            self.setTabText(idx, _tab_text(widget.title()))
            self.setTabToolTip(idx, widget.title())

    def _remove_widget(self, widget):
        idx = self.indexOf(widget)
        if idx >= 0:
            self.removeTab(idx)
            widget.deleteLater()
        if self.count() == 1:
            self.setCurrentIndex(LIBRARY_INDEX)
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


def _tab_text(title):
    '''A recipe name shortened to fit _TAB_TEXT_MAX, measured bold (the
    current tab is bold, and the tab mustn't change width with it).'''
    font = QFont()
    font.setPixelSize(14)
    font.setBold(True)
    return literal(elide(font, title or '', _TAB_TEXT_MAX))


_ICON = 24   # same as the wedge on a recipe tab


def _library_icon():
    '''Two stacked recipe cards, the front one carrying a wedge in four
    category colors: the collection that the recipe tabs come from.'''
    icon = QIcon()
    for ratio in (1, 2):
        pm = QPixmap(_ICON * ratio, _ICON * ratio)
        pm.setDevicePixelRatio(ratio)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor('#7d8771'), 1.2))
        p.setBrush(QColor('#fff1da'))
        p.drawRoundedRect(QRectF(7, 1.5, 15, 17), 3, 3)       # back card
        p.setBrush(QColor('#ffffff'))
        p.drawRoundedRect(QRectF(2, 5.5, 15, 17), 3, 3)       # front card
        p.setPen(Qt.NoPen)
        wedge = QRectF(4.5, 8.5, 10, 10)
        for i, color in enumerate(('#347200', '#ff8c00', '#c9007a', '#d9b26a')):
            p.setBrush(QColor(color))
            p.drawPie(wedge, (90 - i * 90) * 16, -90 * 16)
        p.end()
        icon.addPixmap(pm)
    return icon


class _LibraryButton(QToolButton):
    '''The pinned Library "tab": icon, name and recipe count, drawn
    lifted onto white while Library is showing.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Library (pinned) · Ctrl+0')
        self.setFixedHeight(48)   # 40 px tab plus the 8 px margin above, like recipe tabs
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIcon(_library_icon())
        self.setIconSize(QSize(_ICON, _ICON))
        self.setStyleSheet(f'''
            QToolButton {{
                margin-top: 8px; padding: 0 14px 0 10px;
                border: 1px solid transparent; border-bottom: 0;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                background: transparent; color: {_MUTED}; font-size: 14px;
            }}
            QToolButton:hover:!checked {{ background: #f7f1e6; }}
            QToolButton:checked {{ background: #ffffff; border-color: {_BORDER}; color: {_KALE}; font-weight: 600; }}
        ''')
        self.set_count(None)

    def set_count(self, n):
        # Leading spaces: QToolButton has no icon-to-text spacing setting.
        self.setText('  Library' + (f'  {n}' if n is not None else ''))


def _clear_background(widget):
    '''A transparent background for this widget alone. A bare
    "background: transparent;" style sheet also reaches every child and
    the tooltips they show, which Windows then draws as black boxes.'''
    widget.setProperty('clearBackground', True)
    widget.setStyleSheet('*[clearBackground="true"] { background: transparent; }')


def _inset(widget, left=0, right=0):
    '''Wrap a tab side widget so it sits clear of the tab's edge (tab
    padding in the stylesheet doesn't apply to side widgets).'''
    box = QWidget()
    _clear_background(box)
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
        _clear_background(self)
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
    '''Right-hand corner of the tab strip: the open-recipes list, the "+"
    button and a muted keyboard hint.'''

    def __init__(self, list_button, plus_button, parent=None):
        super().__init__(parent)
        _clear_background(self)
        hint = QLabel('Ctrl+Tab next tab · Ctrl+W close')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 16, 0)
        layout.setSpacing(12)
        layout.addWidget(list_button)
        layout.addWidget(plus_button)
        layout.addWidget(hint)
