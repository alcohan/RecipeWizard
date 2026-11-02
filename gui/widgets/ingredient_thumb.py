'''Square thumbnail widget for an ingredient.

Shows a tag-colored tile with the ingredient's initial straight away,
then swaps in the photo when the background loader (gui.thumbs) has it
— from the thumbnail cache, so after the first time it's near-instant.
Building a gallery of these never decodes a photo on the UI thread.

Used by the ingredients gallery cards, the Ingredients inspector and
the Edit ingredient dialog, so the visual treatment stays consistent.
'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QLabel

import db
from gui.thumbs import load_thumbnail


class IngredientThumb(QLabel):
    '''Square thumbnail for an ingredient.

    Pass name/image_filename/tag_color directly when the caller already
    has them (e.g. from a row in IngredientsModel) — the gallery builds
    hundreds of these at once and a per-thumb db.get_ingredients() call
    is what was making cold-open take seconds. When any of those args
    is None, the thumb falls back to a single DB lookup, which still
    works for one-off callers but should be avoided in tight loops.

    `tint=True` draws the fallback tile as a pale wash of the category
    color with a kale initial (the Framework canvas's avatar style)
    instead of a solid color with a white initial.'''

    def __init__(self, ingredient_id, size, *, name=None, image_filename=None,
                 tag_color=None, radius=4, tint=False, parent=None):
        super().__init__(parent)
        self._size = size
        self._radius = radius
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

        self._show_initial(name, tag_color, tint)
        load_thumbnail(image_filename, size, self._apply_image)

    def _show_initial(self, name, tag_color, tint):
        # Font size scales with the tile so the same widget reads well at
        # the 32px table avatar and the bigger gallery-card sizes.
        nm = (name or '').strip()
        initial = nm[0].upper() if nm else '?'
        font_px = max(11, int(self._size * 0.42))
        color = QColor(tag_color or '#bbbbbb')
        if tint:
            wash = QColor(255 - int((255 - color.red()) * 0.22),
                          255 - int((255 - color.green()) * 0.22),
                          255 - int((255 - color.blue()) * 0.22))
            style = f'background-color: {wash.name()}; color: #082c00;'
        else:
            style = f'background-color: {color.name()}; color: white;'
        self.setStyleSheet(f'{style} border-radius: {self._radius}px;'
                           f' font-weight: 600; font-size: {font_px}px;')
        self.setText(initial)

    def _apply_image(self, image):
        self.setText('')
        self.setStyleSheet(f'background: transparent; border-radius: {self._radius}px;')
        self.setPixmap(QPixmap.fromImage(image))
