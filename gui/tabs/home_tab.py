'''Home dashboard tab: summary count cards on top, a clickable grid of
recipe-wedge cards below. New future widgets/sections should slot into
HomeTab's vertical layout the same way.'''
from PySide6.QtCore import Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea,
    QVBoxLayout, QWidget,
)

import db
from gui.widgets.summary_card import SummaryCard
from gui.widgets.wedge_view import WedgeView


class _RecipeCard(QFrame):
    '''Wedge preview + recipe name. Whole frame is clickable; children are
    transparent to mouse events so the frame's mousePressEvent always fires.'''

    clicked = Signal(int)

    def __init__(self, recipe_id, name, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.name = name or ''
        # Hidden until the wedge actually renders, so cold-load shows a
        # quiet progressive populate instead of 28 placeholder→wedge swaps.
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
        _RecipeGallery._relayout consults _wedge_ready to decide whether
        to make this card visible.'''
        self._wedge_ready = True
        # Only show now if the card isn't being filtered out.
        gallery = self.parent()
        while gallery is not None and not isinstance(gallery, _RecipeGallery):
            gallery = gallery.parent()
        if gallery is not None:
            gallery._reveal_if_ready(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.recipe_id)
        super().mousePressEvent(event)


class _RecipeGallery(QWidget):
    '''Scrollable, responsive grid of _RecipeCard widgets. Column count is
    derived from the current viewport width — resizing the window reflows
    the cards into more or fewer columns without rebuilding any widgets.
    Filtered-out cards are removed from the grid (not just hidden) so the
    remaining ones pack tight.'''

    CARD_WIDTH = 220
    CARD_SPACING = 12
    SCROLLBAR_RESERVE = 24  # avoid column-count oscillation at the threshold

    recipeClicked = Signal(int)

    def __init__(self, recipes_model, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._cards = []
        # Reasonable starting guess: the viewport has no width yet on construction,
        # so this avoids a visible 1-column flash that snaps to N columns once
        # the first resizeEvent fires with the actual size.
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
        '''Re-place existing _RecipeCard widgets in the grid for the current
        column count and active filter. No widgets are destroyed.

        Cards stay hidden until their wedge has rendered (see
        _wedge_ready) so cold load doesn't show a sea of placeholders
        churning into wedges; instead, cards pop in fully-formed.

        Updates are suppressed during the rearrangement so the brief
        "everything removed from the layout" intermediate state never
        reaches the screen.'''
        self.grid_container.setUpdatesEnabled(False)
        try:
            for card in self._cards:
                self.grid.removeWidget(card)
            visible_index = 0
            for card in self._cards:
                matches_filter = not self._filter or self._filter in card.name.lower()
                # Even if the card matches the filter, keep it hidden until
                # its wedge is actually painted.
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
        '''Called by a card when its wedge has finished rendering. Show the
        card now (if filter allows) without touching anyone else's
        position — its grid cell was already reserved in _relayout.'''
        if not self._filter or self._filter in card.name.lower():
            card.setVisible(True)

    def refresh(self):
        # Tear down old cards entirely (model has been replaced).
        for card in self._cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self._cards = []

        # Don't recompute _current_columns here — at construction time the
        # scroll viewport has no real width, and during a later refresh the
        # value is already correct from the most recent resizeEvent.

        # First pass: construct all cards with placeholder wedges (instant).
        # Second pass: queue background renders. PIL's C operations release
        # the GIL so workers actually parallelize. Cache hits from prior
        # renders return immediately; only changed/new recipes do real work.
        pool = QThreadPool.globalInstance()
        for i in range(self._model.rowCount()):
            row = self._model.row_dict(i)
            card = _RecipeCard(row['Id'], row['Name'])
            card.clicked.connect(self.recipeClicked.emit)
            self._cards.append(card)

        self._relayout()
        for card in self._cards:
            card.start_render(pool)


class HomeTab(QWidget):
    '''Top-level home tab. Emits recipeClicked(int) when a gallery card is
    activated — the MainWindow listens and opens the recipe edit dialog.'''

    recipeClicked = Signal(int)

    def __init__(self, ingredients_model, recipes_model, parent=None):
        super().__init__(parent)
        self._ingredients_model = ingredients_model
        self._recipes_model = recipes_model

        self.ingredients_card = SummaryCard('Ingredients')
        self.recipes_card = SummaryCard('Recipes')
        self.suppliers_card = SummaryCard('Suppliers')

        cards_row = QHBoxLayout()
        cards_row.addWidget(self.ingredients_card)
        cards_row.addWidget(self.recipes_card)
        cards_row.addWidget(self.suppliers_card)
        cards_row.addStretch()

        section_label = QLabel('Recipes')
        section_label.setStyleSheet('font-size: 13pt; font-weight: bold; padding: 4px 0;')

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('\U0001F50D  Filter recipes…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setMaximumWidth(280)

        section_row = QHBoxLayout()
        section_row.addWidget(section_label)
        section_row.addStretch()
        section_row.addWidget(self.filter_edit)

        self.gallery = _RecipeGallery(recipes_model)
        self.gallery.recipeClicked.connect(self.recipeClicked.emit)
        self.filter_edit.textChanged.connect(self.gallery.setFilterText)

        layout = QVBoxLayout(self)
        layout.addLayout(cards_row)
        layout.addSpacing(8)
        layout.addLayout(section_row)
        layout.addWidget(self.gallery, stretch=1)

        ingredients_model.modelReset.connect(self._refresh_counts)
        recipes_model.modelReset.connect(self._refresh_counts)
        self._refresh_counts()

    def _refresh_counts(self):
        self.ingredients_card.set_value(self._ingredients_model.rowCount())
        self.recipes_card.set_value(self._recipes_model.rowCount())
        # Suppliers don't have a top-level model in MainWindow; query directly.
        # Cheap (small table) and runs only on a model reset.
        self.suppliers_card.set_value(len(db.get_suppliers()))

    def focus_filter(self):
        '''Called by the main window's Ctrl+F shortcut when Home is active.'''
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()
