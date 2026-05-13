from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel

import db
from utilities.wedge_renderer import render_recipe


class _WedgeRenderSignals(QObject):
    completed = Signal(bytes)


class _WedgeRenderTask(QRunnable):
    '''Background wedge render. Components are captured on the main thread
    (cheap SQLite query) and the heavy PIL work runs on a pool worker. Qt
    queues the completed signal back to the main thread.'''

    def __init__(self, components, size):
        super().__init__()
        self.components = components
        self.size = size
        self.signals = _WedgeRenderSignals()

    def run(self):
        try:
            png = render_recipe(self.components, size=self.size)
        except Exception as exc:
            print(f'wedge render failed: {exc}')
            png = None
        try:
            self.signals.completed.emit(png or b'')
        except RuntimeError:
            # Signal source got torn down (e.g. app exiting mid-render).
            # The receiver is gone too, so there's nothing to deliver.
            pass


class WedgeView(QLabel):
    '''Renders the salad-wedge preview for a recipe.

    Construction always shows a placeholder circle. Callers then choose:
      - `.refresh()`  — synchronous render (blocking, simple).
      - `.render_async()` — background render via QThreadPool; the
        placeholder stays visible until the worker finishes.'''

    def __init__(self, recipe_id, size=220, defer=False, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._show_placeholder()
        if not defer:
            self.refresh()

    def refresh(self):
        '''Synchronous render. Suitable when only one wedge is being drawn
        (recipe edit dialog) — there's no perceived stutter for a single
        ~100ms PIL render.'''
        png = render_recipe(db.get_recipe_wedge_components(self.recipe_id), size=self._size)
        self._apply_png(png or b'')

    def render_async(self, pool=None):
        '''Background render. Use when rendering many wedges at once
        (home gallery) so the UI doesn't freeze while PIL works.'''
        pool = pool or QThreadPool.globalInstance()
        components = db.get_recipe_wedge_components(self.recipe_id)
        task = _WedgeRenderTask(components, self._size)
        # signals object lives on the task; the connection is auto-removed if
        # this WedgeView gets destroyed before the worker emits, so a late
        # callback never lands on a deleted widget.
        task.signals.completed.connect(self._apply_png)
        pool.start(task)

    def _show_placeholder(self):
        '''Draw a quick grey circle so the card has visible content before the
        actual wedge arrives.'''
        pixmap = QPixmap(self._size, self._size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = max(6, self._size // 30)
        rect = QRectF(margin, margin, self._size - 2 * margin, self._size - 2 * margin)
        painter.setPen(QPen(QColor('#ccc'), 2))
        painter.setBrush(QColor('#f5f5f5'))
        painter.drawEllipse(rect)
        painter.end()
        self.setPixmap(pixmap)

    def _apply_png(self, png_bytes):
        if not png_bytes:
            return  # leave the placeholder visible
        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        self.setPixmap(pixmap)
