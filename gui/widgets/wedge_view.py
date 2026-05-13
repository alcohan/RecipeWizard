from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

import db
from utilities.wedge_renderer import render_recipe


class WedgeView(QLabel):
    '''Renders the salad-wedge preview for a recipe. Refresh re-queries the
    direct components and re-rasterizes via utilities.wedge_renderer.'''

    def __init__(self, recipe_id, size=220, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.refresh()

    def refresh(self):
        png = render_recipe(db.get_recipe_wedge_components(self.recipe_id), size=self._size)
        if png:
            pixmap = QPixmap()
            pixmap.loadFromData(png)
            self.setPixmap(pixmap)
        else:
            self.clear()
            self.setText('(no preview)')
