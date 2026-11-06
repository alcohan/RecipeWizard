'''Measuring and eliding text so a box sized for a label always fits it.

QFontMetrics.horizontalAdvance() returns whole pixels and can round
DOWN, while text is laid out at its fractional width. At 100% display
scaling the widths happen to be whole, but at 125% or 150% (common on
1080p laptops) "Core" measures 23 px and lays out at 23.2 px, so a pill
sized to the measurement elides its own label to "C…". Measure with
text_width() (rounded up) and elide with elide() (which allows the
sub-pixel slack) instead.
'''
import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetricsF


def text_width(font, text):
    '''Width of `text` in `font`, rounded up to whole pixels.'''
    return math.ceil(QFontMetricsF(font).horizontalAdvance(text or ''))


def elide(font, text, width):
    '''`text`, shortened with "…" only when it really doesn't fit `width`.'''
    text = text or ''
    fm = QFontMetricsF(font)
    if fm.horizontalAdvance(text) <= width + 0.5:
        return text
    return fm.elidedText(text, Qt.ElideRight, width)


def overflows(font, text, width):
    return QFontMetricsF(font).horizontalAdvance(text or '') > width + 0.5


def literal(text):
    '''`text` for a tab, menu item, button, checkbox or radio label, which
    read & as a shortcut marker and hide it ("Plane & Simple" showed as
    "Plane  Simple"). Use it for anything a user typed.'''
    return (text or '').replace('&', '&&')
