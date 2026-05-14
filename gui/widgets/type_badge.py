'''Shared "ingredient" / "recipe" pill-badge primitive.

Used by:
- the Add Component picker, where the badge goes next to the row's
  name + unit text (rendered by a wider delegate that calls our
  paint helper for just the badge part);
- the Components table on the recipe edit dialog, where the Type
  column is replaced wholesale with the badge via TypeBadgeCellDelegate.

Two pieces:
  - paint_type_badge(): draws the pill inside an available rect and
    returns the rect it occupied (so callers can lay out subsequent
    content after it).
  - TypeBadgeCellDelegate: a drop-in QStyledItemDelegate that paints the
    cell as just the badge, sized from the cell's DisplayRole text.'''
from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate


INGREDIENT_BADGE_COLOR = QColor('#16a34a')   # green
RECIPE_BADGE_COLOR = QColor('#7c3aed')        # violet

_BADGE_PAD_X = 10
_BADGE_PAD_Y = 2
_BADGE_FONT_SCALE = 0.85


def _badge_font(base_font):
    f = QFont(base_font)
    f.setBold(True)
    f.setPointSizeF(base_font.pointSizeF() * _BADGE_FONT_SCALE)
    return f


def paint_type_badge(painter, available_rect, mode, base_font):
    '''Draw a colored pill badge for `mode` (e.g. "ingredient" / "recipe")
    vertically centered inside `available_rect`. The badge is sized to its
    text plus padding. Returns the rect the badge occupied.

    Restores the painter's font on exit. Caller is responsible for save/
    restore of pen/brush/render-hint state if needed.'''
    bf = _badge_font(base_font)
    painter.setFont(bf)
    fm = QFontMetrics(bf)

    text = mode or ''
    badge_w = fm.horizontalAdvance(text) + _BADGE_PAD_X * 2
    badge_h = fm.height() + _BADGE_PAD_Y * 2
    badge_x = available_rect.x()
    badge_y = available_rect.y() + (available_rect.height() - badge_h) // 2
    badge_rect = QRect(badge_x, badge_y, badge_w, badge_h)

    color = RECIPE_BADGE_COLOR if mode == 'recipe' else INGREDIENT_BADGE_COLOR
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)
    painter.setPen(Qt.white)
    painter.drawText(badge_rect, Qt.AlignCenter, text)

    painter.setFont(base_font)
    return badge_rect


def badge_size_hint(mode, base_font, cell_padding=16):
    '''Natural width/height to display the badge in a table cell. Used by
    TypeBadgeCellDelegate.sizeHint so resizeColumnsToContents picks a
    sensible width.'''
    bf = _badge_font(base_font)
    fm = QFontMetrics(bf)
    text = mode or ''
    w = fm.horizontalAdvance(text) + _BADGE_PAD_X * 2 + cell_padding
    h = fm.height() + _BADGE_PAD_Y * 2 + 8
    return QSize(w, h)


class TypeBadgeCellDelegate(QStyledItemDelegate):
    '''Paints a table cell as a single centered pill badge, reading the
    mode from the cell's DisplayRole text ("ingredient" or "recipe").'''

    LEFT_PAD = 8

    def paint(self, painter, option, index):
        mode = index.data(Qt.DisplayRole)
        if mode not in ('ingredient', 'recipe'):
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        inset = option.rect.adjusted(self.LEFT_PAD, 0, -self.LEFT_PAD, 0)
        paint_type_badge(painter, inset, mode, option.font)
        painter.restore()

    def sizeHint(self, option, index):
        mode = index.data(Qt.DisplayRole) or 'ingredient'
        return badge_size_hint(mode, option.font, cell_padding=self.LEFT_PAD * 2)
