'''Responsive wedge-card gallery for recipes.

Used by both the (now-defunct) HomeTab and the Recipes place. Each
card shows the recipe's wedge preview plus its name; clicking emits
`recipeClicked(int)` with the recipe id. Wedges render asynchronously
via QThreadPool so cold-open stays responsive; cards reveal only when
their wedge finishes to avoid a sea of placeholders flicker-swapping
into the final art.
'''
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from gui.widgets.wedge_view import WedgeView


class RecipeCard(QFrame):
    '''Wedge preview + recipe name. Whole frame is clickable; children
    are transparent to mouse events so the frame's mousePressEvent
    always fires regardless of where on the card the user clicks.'''

    clicked = Signal(int)

    def __init__(self, recipe_id, name, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.name = name or ''
        # Hidden until the wedge actually renders, so cold-load shows a
        # quiet progressive populate instead of N placeholder→wedge swaps.
        self._wedge_ready = False
        self.setObjectName('RecipeCard')
        self.setStyleSheet('''
            QFrame#RecipeCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QFrame#RecipeCard:hover {
                border-color: #2a7;
                background-color: #f5fff5;
            }
            QFrame#RecipeCard QLabel { border: 0; }
        ''')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(220, 220)

        self.wedge = WedgeView(recipe_id, size=140, defer=True)
        self.wedge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.wedge.renderComplete.connect(self._on_wedge_ready)

        name_label = QLabel(name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet('padding: 4px; font-weight: bold;')
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.wedge, alignment=Qt.AlignCenter)
        layout.addWidget(name_label)

    def start_render(self, pool):
        self.wedge.render_async(pool)

    def _on_wedge_ready(self):
        '''Worker finished — the card can show its final, populated state.
        RecipeGallery._relayout consults _wedge_ready to decide whether
        to make this card visible.'''
        self._wedge_ready = True
        gallery = self.parent()
        while gallery is not None and not isinstance(gallery, RecipeGallery):
            gallery = gallery.parent()
        if gallery is not None:
            gallery._reveal_if_ready(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.recipe_id)
        super().mousePressEvent(event)


class RecipeGallery(QWidget):
    '''Scrollable, responsive grid of RecipeCard widgets. Column count
    is derived from the current viewport width — resizing the window
    reflows the cards into more or fewer columns without rebuilding
    any widgets. Filtered-out cards are removed from the grid (not
    just hidden) so the remaining ones pack tight.'''

    CARD_WIDTH = 220
    CARD_SPACING = 12
    SCROLLBAR_RESERVE = 24  # avoid column-count oscillation at the threshold

    recipeClicked = Signal(int)

    def __init__(self, recipes_model, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._cards = []
        # Reasonable starting guess: the viewport has no width yet on
        # construction, so this avoids a visible 1-column flash that
        # snaps to N columns once the first resizeEvent fires.
        self._current_columns = 4
        self._filter = ''

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(self.CARD_SPACING)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.grid_container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        self._model.modelReset.connect(self.refresh)
        self.refresh()

    def setFilterText(self, text):
        self._filter = (text or '').strip().lower()
        self._relayout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_cols = self._columns_for_width(self.scroll.viewport().width())
        if new_cols != self._current_columns:
            self._current_columns = new_cols
            self._relayout()

    def _columns_for_width(self, width):
        usable = max(self.CARD_WIDTH, width - self.SCROLLBAR_RESERVE)
        return max(1, (usable + self.CARD_SPACING) // (self.CARD_WIDTH + self.CARD_SPACING))

    def _relayout(self):
        '''Re-place existing RecipeCard widgets in the grid for the
        current column count and active filter. No widgets are
        destroyed. Cards stay hidden until their wedge has rendered
        (see _wedge_ready) so cold load doesn't show a sea of
        placeholders churning into wedges; instead, cards pop in
        fully-formed. Updates are suppressed during the rearrangement
        so the brief "everything removed" intermediate state never
        reaches the screen.'''
        self.grid_container.setUpdatesEnabled(False)
        try:
            for card in self._cards:
                self.grid.removeWidget(card)
            visible_index = 0
            for card in self._cards:
                matches_filter = not self._filter or self._filter in card.name.lower()
                card.setVisible(matches_filter and card._wedge_ready)
                if matches_filter:
                    self.grid.addWidget(
                        card,
                        visible_index // self._current_columns,
                        visible_index % self._current_columns,
                    )
                    visible_index += 1
        finally:
            self.grid_container.setUpdatesEnabled(True)

    def _reveal_if_ready(self, card):
        '''Called by a card when its wedge has finished rendering.
        Shows the card now (if filter allows) without touching anyone
        else's position — its grid cell was already reserved in _relayout.'''
        if not self._filter or self._filter in card.name.lower():
            card.setVisible(True)

    def refresh(self):
        '''Tear down + rebuild from the current model. Called on
        __init__ and whenever the model resets.'''
        for card in self._cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self._cards = []

        pool = QThreadPool.globalInstance()
        for i in range(self._model.rowCount()):
            row = self._model.row_dict(i)
            card = RecipeCard(row['Id'], row['Name'])
            card.clicked.connect(self.recipeClicked.emit)
            self._cards.append(card)

        self._relayout()
        for card in self._cards:
            card.start_render(pool)
