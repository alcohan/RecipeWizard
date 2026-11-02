'''Ingredient photo thumbnails: a disk cache plus background loading.

Ingredient photos are big (most of the sample set is 1667×1667 PNG,
~2 MB each). Decoding and scaling them on the UI thread is what made the
Ingredients place take seconds to open: ~45 ms per photo, every time the
gallery rebuilt.

`load_thumbnail(filename, size, receiver)` returns immediately; a worker
reads the cached thumbnail (or makes it once from the original and saves
it under <data>/thumbs/<size>/) and hands a QImage to
`receiver(image)` on the UI thread. Cache files are keyed by the source
file's name, size and mtime, so replacing a photo makes a fresh thumb.

`thumbnail_image(filename, size)` is the synchronous form, for callers
already off the UI thread (the wedge renderer).
'''
import hashlib
import os
import threading

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QImageReader

import config


def _cache_dir(size):
    path = os.path.join(config.user_data_dir(), 'thumbs', str(size))
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path(source, size):
    st = os.stat(source)
    key = f'{os.path.basename(source)}|{st.st_size}|{int(st.st_mtime)}'
    digest = hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]
    stem = os.path.splitext(os.path.basename(source))[0][:40]
    return os.path.join(_cache_dir(size), f'{stem}-{digest}.png')


def source_path(filename):
    '''Full path of an ingredient photo, or None if unset / missing.'''
    if not filename:
        return None
    path = os.path.join(config.INGREDIENTS_PATH, filename)
    return path if os.path.isfile(path) else None


def thumbnail_image(filename, size):
    '''Square QImage of the photo cropped to fill `size`×`size`, from
    the cache when possible. None when there's no usable photo.'''
    source = source_path(filename)
    if source is None:
        return None
    try:
        cached = _cache_path(source, size)
    except OSError:
        return None
    if os.path.isfile(cached):
        image = QImage(cached)
        if not image.isNull():
            return image
    reader = QImageReader(source)
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        return None
    image = image.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    # Centre-crop to a square, matching the gallery's cover fit.
    if image.width() != size or image.height() != size:
        x = (image.width() - size) // 2
        y = (image.height() - size) // 2
        image = image.copy(x, y, size, size)
    _atomic_save(image, cached)
    return image


def _atomic_save(image, path):
    '''Write to a temp name, then rename: two workers making the same
    thumbnail, or one reading while another writes, never see a
    half-written file.'''
    tmp = f'{path}.{os.getpid()}.{threading.get_ident()}.tmp'
    try:
        if image.save(tmp, 'PNG'):
            os.replace(tmp, path)
    except OSError:
        pass   # an unwritable cache just means regenerating next time
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


class _Signals(QObject):
    done = Signal(object)


class _ThumbTask(QRunnable):
    def __init__(self, filename, size):
        super().__init__()
        self.filename = filename
        self.size = size
        self.signals = _Signals()

    def run(self):
        self.signals.done.emit(thumbnail_image(self.filename, self.size))


# A dedicated pool so a gallery's worth of thumbnails doesn't queue
# behind (or starve) the recipe wedges on the global pool.
_POOL = QThreadPool()
_POOL.setMaxThreadCount(max(2, min(4, QThreadPool.globalInstance().maxThreadCount() // 2)))
_IN_FLIGHT = set()


def load_thumbnail(filename, size, receiver):
    '''Start loading; `receiver(QImage)` runs on the UI thread when the
    image is ready (not at all if there's no photo). The connection
    goes away with the receiver's object, so a widget destroyed before
    the load finishes is never called.'''
    if source_path(filename) is None:
        return
    task = _ThumbTask(filename, size)
    # Hold the task until it delivers: once start() returns nothing else
    # references it, and if Python collects it its signals object goes
    # too, silently dropping the result.
    _IN_FLIGHT.add(task)

    def deliver(image):
        _IN_FLIGHT.discard(task)
        if image is not None and not image.isNull():
            receiver(image)

    task.signals.done.connect(deliver, Qt.QueuedConnection)
    owner = getattr(receiver, '__self__', None)
    if isinstance(owner, QObject):
        # Tie delivery to the receiving widget's lifetime.
        owner.destroyed.connect(lambda *_: _safe_disconnect(task.signals))
    _POOL.start(task)


def _safe_disconnect(signals):
    try:
        signals.done.disconnect()
    except (RuntimeError, TypeError):
        pass


__all__ = ['load_thumbnail', 'thumbnail_image', 'source_path']
