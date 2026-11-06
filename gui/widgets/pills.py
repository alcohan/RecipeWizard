'''Rounded pill labels for tags, diets and the like.

    Pill(text, fg, bg, border=None)   one pill, sized to its text
    PillRow()                          a single line of pills; the ones
                                       that don't fit fold into "+N"
    pill_colors(hex)                   (fg, bg) for a tag's configured color

Both paint themselves, so the ends are always fully round (a styled
QLabel's border-radius goes boxy as soon as the label is taller than
twice the radius) and labels are never clipped mid-letter: a pill
either fits, is elided with "…", or folds into the "+N" count.
'''
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from gui.widgets.text_fit import elide, text_width


_KALE = '#082c00'
_MUTED = '#55624c'
_DEFAULT = '#64748b'
PAD_X = 8
PAD_Y = 2
SPACING = 4


def pill_font():
    f = QFont()
    f.setPixelSize(11)
    f.setWeight(QFont.DemiBold)
    return f


def pill_colors(color_hex):
    '''Text and fill for a pill painted in a tag's own color: dark text
    on light colors, white on dark ones.'''
    bg = QColor(color_hex or _DEFAULT)
    if not bg.isValid():
        bg = QColor(_DEFAULT)
    r, g, b = bg.redF(), bg.greenF(), bg.blueF()
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (_KALE if luminance > 0.6 else '#ffffff'), bg.name()


def _metrics():
    return QFontMetrics(pill_font())


def pill_height():
    return _metrics().height() + PAD_Y * 2


def pill_width(text):
    return text_width(pill_font(), text) + PAD_X * 2


def paint_pill(painter, rect, text, fg, bg, border=None):
    '''Draw one pill filling `rect` (a QRectF), eliding the text to fit.'''
    painter.setRenderHint(QPainter.Antialiasing)
    radius = rect.height() / 2
    if border:
        painter.setPen(QPen(QColor(border), 1))
        rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    else:
        painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(bg))
    painter.drawRoundedRect(rect, radius, radius)
    font = pill_font()
    painter.setFont(font)
    painter.setPen(QColor(fg))
    inner = rect.adjusted(PAD_X, 0, -PAD_X, 0)
    shown = elide(font, text, inner.width())
    painter.drawText(inner, Qt.AlignCenter, shown)


class Pill(QWidget):
    '''One pill. It keeps its natural width; squeezed below that (by a
    max width or a narrow parent) the text is elided and the full text
    goes in the tooltip.'''

    def __init__(self, text, fg=_KALE, bg='#f3ece0', border=None, parent=None):
        super().__init__(parent)
        self.text, self.fg, self.bg, self.border = text, fg, bg, border
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setMinimumWidth(min(pill_width(text), pill_width('…') + 24))
        self.setFixedHeight(pill_height())

    def sizeHint(self):
        return QSize(pill_width(self.text), pill_height())

    def resizeEvent(self, event):
        self.setToolTip(self.text if self.width() < pill_width(self.text) - 1 else '')
        super().resizeEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        paint_pill(p, QRectF(self.rect()), self.text, self.fg, self.bg, self.border)


class PillRow(QWidget):
    '''A one-line row of pills. As many as fit are shown, in order; the
    rest fold into a trailing "+N". hidden_texts() names the folded ones.'''

    MORE = (_MUTED, '#f3ece0', None)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pills = []   # (text, fg, bg, border)
        self.setFixedHeight(pill_height())
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_pills(self, pills):
        self._pills = [tuple(p) + (None,) * (4 - len(p)) for p in pills]
        self.update()

    def _fit(self, width):
        '''How many pills show at `width`: the most that fit alongside
        the "+N" pill they'd leave.'''
        widths = [pill_width(p[0]) for p in self._pills]
        n = len(widths)
        for k in range(n, -1, -1):
            used = sum(widths[:k]) + SPACING * max(k - 1, 0)
            if k < n:
                used += (SPACING if k else 0) + pill_width(f'+{n - k}')
            if used <= width:
                return k
        return 0

    def hidden_texts(self, width=None):
        k = self._fit(self.width() if width is None else width)
        return [p[0] for p in self._pills[k:]]

    def sizeHint(self):
        w = sum(pill_width(p[0]) for p in self._pills) + SPACING * max(len(self._pills) - 1, 0)
        return QSize(w, pill_height())

    def paintEvent(self, event):
        if not self._pills:
            return
        p = QPainter(self)
        h = self.height()
        n = len(self._pills)
        k = self._fit(self.width())
        x = 0.0
        if k == 0:
            # Not even one fits beside the count: elide the first one.
            more_w = pill_width(f'+{n - 1}') + SPACING if n > 1 else 0
            text, fg, bg, border = self._pills[0]
            w = max(self.width() - more_w, 0)
            paint_pill(p, QRectF(0, 0, w, h), text, fg, bg, border)
            x, k = w + SPACING, 1
        else:
            for text, fg, bg, border in self._pills[:k]:
                w = pill_width(text)
                paint_pill(p, QRectF(x, 0, w, h), text, fg, bg, border)
                x += w + SPACING
        if k < n:
            label = f'+{n - k}'
            fg, bg, border = self.MORE
            paint_pill(p, QRectF(x, 0, pill_width(label), h), label, fg, bg, border)
