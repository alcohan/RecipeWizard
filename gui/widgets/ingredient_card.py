'''Clickable ingredient card for the ingredients gallery view.

Shows a thumbnail (image or tag-colored letter fallback), the
ingredient name, and a small colored tag pill when categorized.
Mirrors _RecipeCard's interaction model: the whole frame is clickable
and emits `clicked(int)` with the ingredient id.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gui.widgets.ingredient_thumb import IngredientThumb


CARD_WIDTH = 180
CARD_HEIGHT = 200
_THUMB_SIZE = 100


class IngredientCard(QFrame):
    '''A card representing one ingredient. Children are transparent to
    mouse events so the frame's mousePressEvent always fires regardless
    of where on the card the user clicks.'''

    clicked = Signal(int)

    def __init__(self, ingredient_id, name, tag_name=None, tag_color=None, parent=None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id
        self.name = name or ''
        self.setObjectName('IngredientCard')
        self.setStyleSheet('''
            QFrame#IngredientCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QFrame#IngredientCard:hover {
                border-color: #2a7;
                background-color: #f5fff5;
            }
            QFrame#IngredientCard QLabel { border: 0; background: transparent; }
        ''')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)

        thumb = IngredientThumb(ingredient_id, size=_THUMB_SIZE)
        thumb.setAttribute(Qt.WA_TransparentForMouseEvents)

        name_label = QLabel(self.name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setStyleSheet('font-weight: bold;')
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        name_label.setToolTip(self.name)

        tag_row = QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.addStretch()
        if tag_name:
            chip = QLabel(tag_name)
            chip.setAttribute(Qt.WA_TransparentForMouseEvents)
            chip.setStyleSheet(
                f'background-color: {tag_color or "#888"};'
                ' color: white; font-size: 8pt; font-weight: bold;'
                ' padding: 2px 8px; border-radius: 8px;'
            )
            tag_row.addWidget(chip)
        tag_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 10)
        layout.setSpacing(6)
        layout.addWidget(thumb, alignment=Qt.AlignCenter)
        layout.addWidget(name_label)
        layout.addLayout(tag_row)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.ingredient_id)
        super().mousePressEvent(event)
