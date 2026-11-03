'''Update checks for the running window, on top of utilities.updates.

Startup check: at most once a day (updates/lastCheck), never while
GitHub's rate limit is in force (updates/notBefore), and only when
the preference is on. It runs on the worker pool and fails silently;
a newer release is announced through `updateAvailable`.

Help › Check for Updates… calls check_now(), which reports every
outcome — up to date, offline, rate-limited — to its callback.
'''
import time

from PySide6.QtCore import QObject, QSettings, QTimer, Signal

import config
from gui.workers import run_async
from utilities import updates


KEY_AUTO = 'updates/checkAutomatically'
KEY_PRERELEASES = 'updates/includePrereleases'
KEY_LAST = 'updates/lastCheck'
KEY_NOT_BEFORE = 'updates/notBefore'
DAY = 24 * 60 * 60
STARTUP_DELAY_MS = 4000


def check_automatically():
    return QSettings().value(KEY_AUTO, True, type=bool)


def include_prereleases():
    # On by default while every release is a pre-release.
    return QSettings().value(KEY_PRERELEASES, True, type=bool)


class UpdateService(QObject):
    '''Holds the newest release found this session, if any.'''

    updateAvailable = Signal(object)   # updates.Release

    def __init__(self, parent=None, fetch=updates.fetch_releases):
        super().__init__(parent)
        self._fetch = fetch
        self.release = None
        self._busy = False
        self._waiting = []   # manual-check callbacks for the check in flight

    def schedule_startup_check(self):
        QTimer.singleShot(STARTUP_DELAY_MS, self.check_if_due)

    def is_due(self, now=None):
        now = time.time() if now is None else now
        # Epoch seconds are stored as ints: value(type=float) goes
        # through a 32-bit float and is off by up to two minutes.
        s = QSettings()
        if now < s.value(KEY_NOT_BEFORE, 0, type=int):
            return False
        return now - s.value(KEY_LAST, 0, type=int) >= DAY

    def check_if_due(self):
        '''The quiet startup check: silent unless there's an update.'''
        if check_automatically() and self.is_due():
            self._check(None)

    def check_now(self, on_result):
        '''Manual check. on_result(status, value): ('update', Release),
        ('current', None), ('rate', RateLimited) or ('error', message).'''
        self._check(on_result)

    def _check(self, on_result):
        # A manual check during the startup one rides along with it.
        if on_result is not None:
            self._waiting.append(on_result)
        if self._busy:
            return
        self._busy = True
        current = config.__version__
        prereleases = include_prereleases()
        fetch = self._fetch

        def work():
            # Errors come back as values so RateLimited keeps its reset time.
            try:
                return 'ok', updates.newest_release(fetch(), current, prereleases)
            except updates.RateLimited as exc:
                return 'rate', exc
            except Exception as exc:
                return 'error', str(exc) or exc.__class__.__name__

        run_async(work, self._finished)

    def _finished(self, result):
        self._busy = False
        waiting, self._waiting = self._waiting, []
        kind, value = result
        s = QSettings()
        if kind == 'ok':
            s.setValue(KEY_LAST, int(time.time()))
            if value is not None:
                self.release = value
                self.updateAvailable.emit(value)
        elif kind == 'rate':
            s.setValue(KEY_NOT_BEFORE, int(value.reset_at))
        if kind == 'ok':
            kind = 'update' if value is not None else 'current'
        for on_result in waiting:
            on_result(kind, value)
