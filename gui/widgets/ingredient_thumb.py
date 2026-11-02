'''Square thumbnail widget for an ingredient.

Prefers the ingredient's ImageFilename when present; falls back to a
tag-colored tile carrying the ingredient's first initial so image-less
ingredients still convey their category at a glance.

Used by both the home tab's "Recently edited" strip and the ingredients
gallery card, so the visual treatment stays consistent.
'''
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

import config
import db


class IngredientThumb(QLabel):
    '''Square thumbnail for an ingredient.

    Pass name/image_filename/tag_color directly when the caller already
    has them (e.g. from a row in IngredientsModel) — the gallery builds
    hundreds of these at once and a per-thumb db.get_ingredients() call
    is what was making cold-open take seconds. When any of those args
    is None, the thumb falls back to a single DB lookup, which still
    works for one-off callers but should be avoided in tight loops.'''

    def __init__(self, ingredient_id, size, *, name=None, image_filename=None,
                 tag_color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)

        if name is None or image_filename is None or tag_color is None:
            try:
                ing = db.get_ingredients(ingredient_id) or {}
            except Exception:
                ing = {}
            if name is None:
                name = ing.get('Name')
            if image_filename is None:
                image_filename = ing.get('ImageFilename')
            if tag_color is None:
                tag_color = ing.get('TagColor')

        pixmap = _load_ingredient_pixmap(image_filename, size)
        if pixmap is not None:
            self.setStyleSheet('background: transparent; border-radius: 4px;')
            self.setPixmap(pixmap)
            return

        # Letter-on-tag-color fallback. Font size scales with the tile so
        # the same widget reads well at the 56px recents thumb and the
        # bigger gallery-card sizes.
        color = tag_color or '#bbb'
        nm = (name or '').strip()
        initial = nm[0].upper() if nm else '?'
        font_pt = max(10, int(size * 0.36))
        self.setStyleSheet(
            f'background-color: {color}; border-radius: 4px;'
            f' color: white; font-weight: bold; font-size: {font_pt}pt;'
        )
        self.setText(initial)


def _load_ingredient_pixmap(filename, size):
    if not filename:
        return None
    path = os.path.join(config.INGREDIENTS_PATH, filename)
    if not os.path.isfile(path):
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    return pixmap.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
