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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.recipe_id)
        super().mousePressEvent(event)


class _RecipeGallery(QWidget):
    '''Scrollable grid of _RecipeCard widgets, refreshed whenever the source
    RecipesModel resets. 4 columns by default.'''

    recipeClicked = Signal(int)

    def __init__(self, recipes_model, columns=4, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._columns = columns

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidget(self.grid_container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._filter = ''

        self._model.modelReset.connect(self.refresh)
        self.refresh()

    def setFilterText(self, text):
        self._filter = (text or '').strip().lower()
        self._apply_filter()

    def _apply_filter(self):
        for i in range(self.grid.count()):
            card = self.grid.itemAt(i).widget()
            if isinstance(card, _RecipeCard):
                card.setVisible(not self._filter or self._filter in card.name.lower())

    def refresh(self):
        # Take down all cards. For 28 recipes this is cheap; if the gallery
        # ever scales past a few hundred, switch to an incremental diff.
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # First pass: place all cards with placeholder wedges (instant).
        # Second pass: queue background renders. PIL's C operations release
        # the GIL so workers actually parallelize. Cache hits from prior
        # renders return immediately; only changed/new recipes do real work.
        pool = QThreadPool.globalInstance()
        cards = []
        for i in range(self._model.rowCount()):
            row = self._model.row_dict(i)
            card = _RecipeCard(row['Id'], row['Name'])
            card.clicked.connect(self.recipeClicked.emit)
            self.grid.addWidget(card, i // self._columns, i % self._columns)
            cards.append(card)
        for card in cards:
            card.start_render(pool)
        # Re-apply any active filter so a refresh doesn't reveal cards
        # the user has filtered out.
        self._apply_filter()


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
