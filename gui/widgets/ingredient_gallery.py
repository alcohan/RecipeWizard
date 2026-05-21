'''Responsive grid of IngredientCard widgets.

Mirrors home_tab._RecipeGallery's reflow-on-resize behavior but
specialized for ingredients: synchronous thumbnail rendering (no
wedge-rendering threadpool), and context menu actions matching the
table view so right-click "Edit / Delete" works the same way regardless
of which view the user has chosen.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QMenu, QScrollArea, QVBoxLayout, QWidget,
)

from gui.widgets.ingredient_card import IngredientCard, CARD_WIDTH


_CARD_SPACING = 12
_SCROLLBAR_RESERVE = 24  # avoid column-count oscillation at the threshold


class IngredientGallery(QWidget):
    '''Card grid backed by an IngredientsModel. Emits `ingredientActivated`
    with the source-model row index on left-click, matching the table
    view's `rowActivated` signal so callers can route both through the
    same handler.'''

    ingredientActivated = Signal(int)

    def __init__(self, source_model, context_actions=None, parent=None):
        super().__init__(parent)
        self._model = source_model
        self._context_actions = context_actions or []
        self._cards = []
        self._current_columns = 4
        self._filter = ''
        # Lazy build: don't construct any cards until the gallery is first
        # shown. On app launch the user is on the Home tab and may never
        # switch to Ingredients; building hundreds of cards eagerly was
        # making cold-open slow for users with large libraries.
        self._stale = True

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(_CARD_SPACING)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.grid_container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        self._model.modelReset.connect(self._on_model_reset)

    def setFilterText(self, text):
        self._filter = (text or '').strip().lower()
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_columns()

    def showEvent(self, event):
        '''On first show, build the cards. Then (and on every subsequent
        show) recompute columns — resizeEvent doesn't reliably fire when
        this widget is the inactive child of a QStackedWidget (the
        ingredients tab's gallery/table stack), so if the user resized
        the window while the table was active, the gallery would
        otherwise carry the old column count when it next appears.'''
        super().showEvent(event)
        if self._stale:
            self.refresh()
            self._stale = False
        self._sync_columns()

    def _on_model_reset(self):
        '''Mark stale, but only do the expensive rebuild if we're
        actually visible. Otherwise wait for the next showEvent. This is
        what makes startup cheap: the IngredientsModel resets on every
        save (including saves the user does on other tabs), which would
        otherwise force a rebuild of every card whether the gallery is
        showing or not.'''
        self._stale = True
        if self.isVisible():
            self.refresh()
            self._stale = False

    def _sync_columns(self):
        new_cols = self._columns_for_width(self.scroll.viewport().width())
        if new_cols != self._current_columns:
            self._current_columns = new_cols
            self._relayout()

    def _columns_for_width(self, width):
        usable = max(CARD_WIDTH, width - _SCROLLBAR_RESERVE)
        return max(1, (usable + _CARD_SPACING) // (CARD_WIDTH + _CARD_SPACING))

    def _relayout(self):
        '''Re-place existing cards in the grid for the current column
        count and active filter. No widgets are destroyed.

        Visibility ordering matters: setVisible(True) on a widget that
        hasn't been parented (no addWidget yet) promotes it to a
        top-level window briefly — the OS shows it as its own window
        until the next addWidget reparents it. On cold open with N
        ingredients that flashes N tiny windows. So we hide everything
        first (False on an unparented widget is safe — it never goes
        to top-level), then addWidget to parent, and only then
        setVisible(True) on the now-parented widget.'''
        self.grid_container.setUpdatesEnabled(False)
        try:
            for card in self._cards:
                self.grid.removeWidget(card)
                card.setVisible(False)
            visible_index = 0
            for card in self._cards:
                matches_filter = not self._filter or self._filter in card._search_text
                if not matches_filter:
                    continue
                self.grid.addWidget(
                    card,
                    visible_index // self._current_columns,
                    visible_index % self._current_columns,
                )
                card.setVisible(True)
                visible_index += 1
        finally:
            self.grid_container.setUpdatesEnabled(True)

    def refresh(self):
        # Tear down old cards (model has been replaced).
        for card in self._cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self._cards = []

        for i in range(self._model.rowCount()):
            row = self._model.row_dict(i)
            card = IngredientCard(
                row['Id'], row.get('Name'),
                tag_name=row.get('TagName'),
                tag_color=row.get('TagColor'),
                image_filename=row.get('ImageFilename'),
            )
            # Stamp the source-row index on the card so context-menu actions
            # can call back to the same handlers as the table view.
            card._row = i
            # Precompute a multi-field search blob so the gallery's filter
            # behaves the same way the table's MultiColumnFilterProxy does
            # (substring match across name, tag, portion/unit, calories).
            card._search_text = ' '.join(
                str(row.get(k) or '')
                for k in ('Name', 'TagName', 'Portion', 'Unit', 'Calories')
            ).lower()
            card.clicked.connect(lambda _id, r=i: self.ingredientActivated.emit(r))
            if self._context_actions:
                card.setContextMenuPolicy(Qt.CustomContextMenu)
                card.customContextMenuRequested.connect(
                    lambda point, c=card: self._show_context_menu(c, point)
                )
            self._cards.append(card)

        self._relayout()

    def _show_context_menu(self, card, point):
        menu = QMenu(card)
        for label, handler in self._context_actions:
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, h=handler, r=card._row: h(r))
        menu.exec(card.mapToGlobal(point))
