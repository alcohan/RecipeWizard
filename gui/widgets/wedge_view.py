from PySide6.QtCore import QObject, QRectF, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel

import config
import db
from gui import thumbs
from utilities.wedge_renderer import render_recipe


def recipe_photo(recipe_id):
    '''The recipe's photo filename when it's set and the file exists,
    else ''. A photo takes the wedge's place everywhere.'''
    name = db.get_recipe_image(recipe_id)
    return name if name and thumbs.source_path(name, config.RECIPE_IMAGES_PATH) else ''


def photo_image(filename, size):
    '''The recipe photo as a `size`×`size` QImage with rounded corners,
    from the shared thumbnail cache; a null QImage if it can't be read.
    Safe off the UI thread.'''
    square = thumbs.thumbnail_image(filename, size, config.RECIPE_IMAGES_PATH)
    if square is None or square.isNull():
        return QImage()
    out = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    path = QPainterPath()
    radius = max(3.0, size * 0.12)
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    painter.setClipPath(path)
    painter.drawImage(QRectF(0, 0, size, size), square)
    painter.end()
    return out


class _WedgeRenderSignals(QObject):
    completed = Signal(QImage)


class _WedgeRenderTask(QRunnable):
    '''Background wedge render. Components are captured on the main thread
    (cheap SQLite query) and the heavy PIL work + PNG decode run on a pool
    worker — including decoding the PNG bytes into a QImage. The main
    thread then just does a cheap QPixmap.fromImage on the queued signal,
    so the 28-card gallery cold load doesn't block paint events while
    decoding sprites one-by-one.'''

    def __init__(self, components, size, shape=None, shape_color=None, photo=''):
        super().__init__()
        self.components = components
        self.size = size
        self.shape = shape
        self.shape_color = shape_color
        self.photo = photo
        self.signals = _WedgeRenderSignals()

    def run(self):
        image = QImage()
        try:
            if self.photo:
                image = photo_image(self.photo, self.size)
            if image.isNull():
                png = render_recipe(
                    self.components, size=self.size,
                    shape=self.shape, shape_color=self.shape_color,
                )
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
    '''Renders the salad-wedge preview for a recipe — or the recipe's
    photo, when it has one (from the thumbnail cache, so it's as cheap
    as a wedge after the first time).

    Construction always shows a placeholder circle. Callers then choose:
      - `.refresh()`  — synchronous render (blocking, simple).
      - `.render_async()` — background render via QThreadPool; the
        placeholder stays visible until the worker finishes.

    Emits renderComplete() once the actual wedge has replaced the
    placeholder — callers (e.g. the home gallery) can wait on this to
    show the surrounding card only when it's actually ready, so the user
    sees cards pop in fully formed instead of placeholder→wedge churn.'''

    renderComplete = Signal()

    def __init__(self, recipe_id, size=220, defer=False, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._size = size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self._show_placeholder()
        if not defer:
            self.refresh()

    def _format_for_recipe(self):
        '''(shape_name, color_hex) from the recipe's format tag, or
        (None, None) if no format tag is set. shape is editable per-tag in
        the Tags Manager, so this is just a plain DB read.'''
        tag = db.get_recipe_tag(self.recipe_id)
        if not tag:
            return None, None
        return tag.get('shape'), tag.get('color')

    def refresh(self):
        '''Synchronous render. Suitable when only one wedge is being drawn
        (recipe edit dialog) — there's no perceived stutter for a single
        ~100ms PIL render.'''
        photo = recipe_photo(self.recipe_id)
        image = photo_image(photo, self._size) if photo else QImage()
        if image.isNull():
            shape, color = self._format_for_recipe()
            png = render_recipe(
                db.get_recipe_wedge_components(self.recipe_id),
                size=self._size, shape=shape, shape_color=color,
            )
            if png:
                image.loadFromData(png)
        self._apply_image(image)

    def render_async(self, pool=None):
        '''Background render. Use when rendering many wedges at once
        (home gallery) so the UI doesn't freeze while PIL works.'''
        pool = pool or QThreadPool.globalInstance()
        photo = recipe_photo(self.recipe_id)
        # With a photo the wedge is only the fallback for an unreadable
        # file; skip its queries.
        components = [] if photo else db.get_recipe_wedge_components(self.recipe_id)
        shape, color = (None, None) if photo else self._format_for_recipe()
        task = _WedgeRenderTask(components, self._size, shape, color, photo)
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
        self.renderComplete.emit()
