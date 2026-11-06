'''Startup splash: a kale card with the app name, the version, what's
loading right now and a progress bar. app.py shows it before anything
heavy is imported, then calls step() at each stage of startup.

Startup runs on the main thread, so the card can only repaint when a
step is reported; step() repaints right away and keeps Windows from
marking the window as not responding.

Only Qt is imported here, so the card appears as early as possible.
'''
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget


_BG = QColor('#082c00')          # kale, as in the app header
_INK = QColor('#fff1da')         # parmesan
_MUTED = QColor(255, 241, 218, 150)
_ACCENT = QColor('#bbca00')      # avocado
_TRACK = QColor(255, 241, 218, 40)

_W, _H = 440, 250
_RADIUS = 12
_PAD = 32


def _font(px, weight=QFont.Normal):
    f = QFont('Segoe UI')
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


class Splash(QWidget):
    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(_W, _H)
        self._version = ''
        self._message = 'Starting…'
        self._progress = 0.0
        screen = QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - _W // 2, geo.center().y() - _H // 2)

    def set_version(self, text):
        self._version = text or ''
        self._repaint()

    def step(self, message, progress):
        '''Show `message` with the bar at `progress` (0–1). The bar
        never moves backwards.'''
        self._message = message
        self._progress = max(self._progress, min(1.0, float(progress)))
        self._repaint()

    def _repaint(self):
        if self.isVisible():
            self.repaint()
            QApplication.processEvents()

    def show(self):
        super().show()
        self.raise_()
        self._repaint()

    def finish(self, window):
        '''Close once `window` is showing.'''
        self.step('Ready', 1.0)
        window.raise_()
        window.activateWindow()
        self.close()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        card = QPainterPath()
        card.addRoundedRect(QRectF(0, 0, _W, _H), _RADIUS, _RADIUS)
        p.fillPath(card, _BG)
        p.setClipPath(card)

        # Monogram, matching the header's but larger.
        mono = QRectF(_PAD, _PAD, 44, 42)
        p.setPen(Qt.NoPen)
        p.setBrush(_ACCENT)
        p.drawRoundedRect(mono, 7, 7)
        p.setPen(_BG)
        p.setFont(_font(22, QFont.Bold))
        p.drawText(mono, Qt.AlignCenter, 'R')

        p.setPen(_INK)
        p.setFont(_font(26, QFont.DemiBold))
        p.drawText(QRectF(_PAD + 60, _PAD - 4, _W, 34), Qt.AlignLeft | Qt.AlignVCenter, 'RecipeWizard')
        if self._version:
            p.setPen(_MUTED)
            p.setFont(_font(13))
            p.drawText(QRectF(_PAD + 61, _PAD + 28, _W, 18), Qt.AlignLeft | Qt.AlignVCenter, self._version)

        # What's loading, just above the bar.
        bar_y = _H - _PAD - 4
        p.setPen(_INK)
        p.setFont(_font(13))
        text_rect = QRectF(_PAD, bar_y - 30, _W - 2 * _PAD, 20)
        message = p.fontMetrics().elidedText(self._message, Qt.ElideRight, int(text_rect.width()))
        p.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, message)

        track = QRectF(_PAD, bar_y, _W - 2 * _PAD, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(_TRACK)
        p.drawRoundedRect(track, 2, 2)
        if self._progress > 0:
            done = QRectF(track.x(), track.y(), max(4.0, track.width() * self._progress), track.height())
            p.setBrush(_ACCENT)
            p.drawRoundedRect(done, 2, 2)
        p.end()
