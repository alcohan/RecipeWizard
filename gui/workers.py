'''Run a blocking call (network, disk) off the UI thread.

    run_async(fn, on_done, on_error)

`fn()` runs on a worker; `on_done(result)` or `on_error(message)` then
runs on the UI thread. The task is held until it reports back — once
QThreadPool.start() returns nothing else references it, and if Python
collected it the result would be silently dropped.
'''
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:   # surfaced to the UI as a message
            self.signals.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.signals.done.emit(result)


_POOL = QThreadPool()
_POOL.setMaxThreadCount(2)
_IN_FLIGHT = set()


def run_async(fn, on_done, on_error=None):
    task = _Task(fn)
    _IN_FLIGHT.add(task)

    def finish(callback, value):
        _IN_FLIGHT.discard(task)
        if callback is not None:
            callback(value)

    task.signals.done.connect(lambda v: finish(on_done, v), Qt.QueuedConnection)
    task.signals.failed.connect(lambda m: finish(on_error, m), Qt.QueuedConnection)
    _POOL.start(task)
    return task
