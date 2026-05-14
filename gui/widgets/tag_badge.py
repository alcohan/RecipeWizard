'''Colored pill-badge primitive for tags.

Two pieces:
  - paint_tag_badge(): draws a pill inside an available rect given a text
    and a fill color. Used by anything that wants to paint a tag badge
    inline (e.g. the component picker's row delegate).
  - TagBadgeCellDelegate: a QStyledItemDelegate that paints a table/list
    cell as a colored badge, reading the badge text from DisplayRole and
    the hex color from TagColorRole (= Qt.UserRole + 1). If DisplayRole
    is empty the cell renders blank.
'''
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate


# Custom role for the tag's hex color string; sibling to Qt.DisplayRole on
# the same cell. Plucked out of the Qt.UserRole range so it can't collide
# with the default Qt.UserRole some other column might be using.
TagColorRole = Qt.UserRole + 1


_DEFAULT_COLOR = '#64748b'  # slate grey for "no tag" / missing color
_BADGE_PAD_X = 10
_BADGE_PAD_Y = 2
_BADGE_FONT_SCALE = 0.85


def _badge_font(base_font):
    f = QFont(base_font)
    f.setBold(True)
    f.setPointSizeF(base_font.pointSizeF() * _BADGE_FONT_SCALE)
    return f


def paint_tag_badge(painter, available_rect, text, color_hex, base_font):
    '''Draw a colored pill containing `text`, vertically centered inside
    `available_rect`. Returns the rect the badge actually occupied.'''
    bf = _badge_font(base_font)
    painter.setFont(bf)
    fm = QFontMetrics(bf)
    text = text or ''
    badge_w = fm.horizontalAdvance(text) + _BADGE_PAD_X * 2
    badge_h = fm.height() + _BADGE_PAD_Y * 2
    badge_x = available_rect.x()
    badge_y = available_rect.y() + (available_rect.height() - badge_h) // 2
    badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)

    color = QColor(color_hex or _DEFAULT_COLOR)
    if not color.isValid():
        color = QColor(_DEFAULT_COLOR)

    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)
    painter.setPen(Qt.white)
    painter.drawText(badge_rect, Qt.AlignCenter, text)
    painter.setFont(base_font)
    return badge_rect


def tag_badge_size(text, base_font, cell_padding=16):
    bf = _badge_font(base_font)
    fm = QFontMetrics(bf)
    text = text or ''
    w = fm.horizontalAdvance(text) + _BADGE_PAD_X * 2 + cell_padding
    h = fm.height() + _BADGE_PAD_Y * 2 + 8
    return QSize(w, h)


class TagBadgeCellDelegate(QStyledItemDelegate):
    '''Paints a table cell as a colored pill badge sourced from model data.
    Reads the badge text from DisplayRole and the color hex from TagColorRole.
    If DisplayRole is empty the cell renders blank.'''

    LEFT_PAD = 8

    def paint(self, painter, option, index):
        text = index.data(Qt.DisplayRole) or ''
        if not text:
            # Still draw the selection highlight so the row reads as selected,
            # then leave the cell otherwise blank.
            if option.state & QStyle.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())
            return
        color_hex = index.data(TagColorRole) or _DEFAULT_COLOR
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        inset = option.rect.adjusted(self.LEFT_PAD, 0, -self.LEFT_PAD, 0)
        paint_tag_badge(painter, inset, text, color_hex, option.font)
        painter.restore()

    def sizeHint(self, option, index):
        text = index.data(Qt.DisplayRole) or ''
        return tag_badge_size(text, option.font, cell_padding=self.LEFT_PAD * 2)
