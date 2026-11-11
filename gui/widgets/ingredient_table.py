'''Delegates for the Ingredients table, per the Framework canvas.

- NameDelegate: a 32 px avatar (category-tinted tile with the initial)
  and the name in semibold ("Archived" underneath when it is). Avatars
  are painted, not photos — the table never decodes an image.
- CategoryDelegate: a dot in the category's color and its name.
- TwoLineDelegate: main text with a muted second line (Unit · tool).
- ChangeDelegate: the 90-day change — an amber "▲ +8.2%" pill at 5% or
  more, a red "No price" pill when there's no price, muted text
  otherwise.
- PlainDelegate: everything else, muted when the text is a placeholder.

All of them paint the selected row the canvas way: parmesan wash and a
romaine bar on the left edge (drawn by the first column).
'''
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from gui.models.ingredients_model import (
    ChangeRole, PRICE_UP_THRESHOLD, RowRole, SubTextRole, format_change,
)
from gui.widgets.tag_badge import TagColorRole
from gui.widgets.text_fit import elide, text_width


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_SELECTED = '#fff1da'
_UP_FG, _UP_BG = '#8a4a00', '#fff0dc'
_MISSING_FG, _MISSING_BG = '#b80700', '#ffe8e3'
_PLACEHOLDERS = ('—', 'Unused', '')


def tint(hex_color, amount=0.22):
    c = QColor(hex_color or '#a7ad9c')
    return QColor(255 - int((255 - c.red()) * amount),
                  255 - int((255 - c.green()) * amount),
                  255 - int((255 - c.blue()) * amount))


def _small(font):
    f = QFont(font)
    f.setPointSizeF(max(7.0, font.pointSizeF() * 0.85))
    return f


_ARCHIVED_OPACITY = 0.45


def _fade(painter, index):
    '''Archived rows draw faded from here on.'''
    if (index.data(RowRole) or {}).get('Archived'):
        painter.setOpacity(_ARCHIVED_OPACITY)


def _background(painter, option, index=None):
    '''The selection fill; then, given the index, fade an archived row.'''
    if option.state & QStyle.State_Selected:
        painter.fillRect(option.rect, QColor(_SELECTED))
    if index is not None:
        _fade(painter, index)


class NameDelegate(QStyledItemDelegate):
    AVATAR = 32

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _background(painter, option)
        rect = option.rect
        if option.state & QStyle.State_Selected:
            painter.fillRect(rect.x(), rect.y(), 3, rect.height(), QColor(_ROMAINE))
        _fade(painter, index)
        row = index.data(RowRole) or {}
        color = index.data(TagColorRole)

        # Avatar.
        ax = rect.x() + 12
        ay = rect.center().y() - self.AVATAR / 2
        av = QRectF(ax, ay, self.AVATAR, self.AVATAR)
        painter.setPen(Qt.NoPen)
        painter.setBrush(tint(color))
        painter.drawRoundedRect(av, 6, 6)
        bold = QFont(option.font)
        bold.setWeight(QFont.DemiBold)
        painter.setFont(bold)
        painter.setPen(QColor(_KALE))
        name = str(row.get('Name') or '')
        painter.drawText(av, Qt.AlignCenter, name[:1].upper())

        # Name, with "Archived" underneath when it is.
        x = int(av.right()) + 10
        w = rect.right() - x - 8
        sub = str(index.data(SubTextRole) or '')
        if sub:
            painter.drawText(QRectF(x, rect.y() + 4, w, rect.height() / 2 - 2), Qt.AlignLeft | Qt.AlignBottom,
                             elide(painter.font(), name, w))
            painter.setFont(_small(option.font))
            painter.setPen(QColor(_MUTED))
            painter.drawText(QRectF(x, rect.y() + rect.height() / 2, w, rect.height() / 2 - 4),
                             Qt.AlignLeft | Qt.AlignTop, sub)
        else:
            painter.drawText(QRectF(x, rect.y(), w, rect.height()), Qt.AlignLeft | Qt.AlignVCenter,
                             elide(painter.font(), name, w))
        painter.restore()


class CategoryDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _background(painter, option, index)
        rect = option.rect.adjusted(8, 0, -8, 0)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(index.data(TagColorRole) or '#a7ad9c'))
        painter.drawEllipse(QRectF(rect.x(), rect.center().y() - 3.5, 7, 7))
        painter.setFont(option.font)
        painter.setPen(QColor(_KALE))
        text = str(index.data(Qt.DisplayRole) or '')
        painter.drawText(QRectF(rect.x() + 13, rect.y(), rect.width() - 13, rect.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, elide(option.font, text, rect.width() - 13))
        painter.restore()


class TwoLineDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        _background(painter, option, index)
        rect = option.rect.adjusted(8, 4, -8, -4)
        painter.setFont(option.font)
        painter.setPen(QColor(_KALE))
        half = rect.height() / 2
        painter.drawText(QRectF(rect.x(), rect.y(), rect.width(), half + 2),
                         Qt.AlignLeft | Qt.AlignBottom, str(index.data(Qt.DisplayRole) or ''))
        painter.setFont(_small(option.font))
        painter.setPen(QColor(_MUTED))
        painter.drawText(QRectF(rect.x(), rect.y() + half, rect.width(), half),
                         Qt.AlignLeft | Qt.AlignTop, str(index.data(SubTextRole) or ''))
        painter.restore()


class ChangeDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _background(painter, option, index)
        row = index.data(RowRole) or {}
        pct = index.data(ChangeRole)
        rect = option.rect.adjusted(8, 0, -8, 0)
        small = _small(option.font)
        if not row.get('PriceCount'):
            self._pill(painter, rect, small, 'No price', _MISSING_FG, _MISSING_BG)
        elif pct is not None and pct >= PRICE_UP_THRESHOLD:
            self._pill(painter, rect, small, f'▲ {format_change(pct)}', _UP_FG, _UP_BG)
        else:
            painter.setFont(small)
            painter.setPen(QColor(_MUTED))
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, format_change(pct))
        painter.restore()

    def _pill(self, painter, rect, font, text, fg, bg):
        painter.setFont(font)
        bold = QFont(font)
        bold.setWeight(QFont.DemiBold)
        painter.setFont(bold)
        w = text_width(bold, text) + 14
        pill = QRectF(rect.x(), rect.center().y() - 9, w, 18)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(pill, 9, 9)
        painter.setPen(QColor(fg))
        painter.drawText(pill, Qt.AlignCenter, text)


class PlainDelegate(QStyledItemDelegate):
    '''Text cells; placeholders ("—", "Unused") are muted. Semibold for
    the Cost column, as in the canvas.'''

    def __init__(self, parent=None, bold=False, muted=False):
        super().__init__(parent)
        self._bold = bold
        self._muted = muted

    def paint(self, painter, option, index):
        painter.save()
        _background(painter, option, index)
        text = str(index.data(Qt.DisplayRole) or '')
        font = QFont(option.font)
        if self._bold and text not in _PLACEHOLDERS:
            font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        muted = self._muted or text in _PLACEHOLDERS
        painter.setPen(QColor(_MUTED if muted else _KALE))
        align = index.data(Qt.TextAlignmentRole) or int(Qt.AlignLeft | Qt.AlignVCenter)
        rect = option.rect.adjusted(8, 0, -12, 0)
        painter.drawText(rect, Qt.AlignmentFlag(align),
                         elide(painter.font(), text, rect.width()))
        painter.restore()
