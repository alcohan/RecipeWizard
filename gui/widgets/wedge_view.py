from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel

import db
from utilities.wedge_renderer import render_recipe


class _WedgeRenderSignals(QObject):
    completed = Signal(QImage)


class _WedgeRenderTask(QRunnable):
    '''Background wedge render. Components are captured on the main thread
    (cheap SQLite query) and the heavy PIL work + PNG decode run on a pool
    worker — including decoding the PNG bytes into a QImage. The main
    thread then just does a cheap QPixmap.fromImage on the queued signal,
    so the 28-card gallery cold load doesn't block paint events while
    decoding sprites one-by-one.'''

    def __init__(self, components, size):
        super().__init__()
        self.components = components
        self.size = size
        self.signals = _WedgeRenderSignals()

    def run(self):
        image = QImage()
        try:
            png = render_recipe(self.components, size=self.size)
            if png:
                image.loadFromData(png)  # PNG decode happens on the worker
        except Exception as exc:
            print(f'wedge render failed: {exc}')
        try:
            self.signals.completed.emit(image)
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
        image = QImage()
        if png:
            image.loadFromData(png)
        self._apply_image(image)

    def render_async(self, pool=None):
        '''Background render. Use when rendering many wedges at once
        (home gallery) so the UI doesn't freeze while PIL works.'''
        pool = pool or QThreadPool.globalInstance()
        components = db.get_recipe_wedge_components(self.recipe_id)
        task = _WedgeRenderTask(components, self._size)
        # signals object lives on the task; the connection is auto-removed if
        # this WedgeView gets destroyed before the worker emits, so a late
        # callback never lands on a deleted widget.
        task.signals.completed.connect(self._apply_image)
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

    def _apply_image(self, image):
        '''QImage was decoded on a worker (or main, for sync refresh). Building
        the QPixmap is cheap — just GPU upload — so this stays fast even if
        all 28 callbacks land in quick succession.'''
        if image.isNull():
            return  # leave the placeholder visible
        self.setPixmap(QPixmap.fromImage(image))
