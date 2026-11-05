'''Delegates for the recipe editor's components grid.

- NameDelegate: category dot, name, and a small pill for sub-recipes,
  template-added rows and how portion rules size the row ("base 50%",
  "fixed", "by hand"). Rows changed since the last save get the
  canvas's selected treatment: parmesan wash plus a romaine bar on the
  left edge (painted here, since it spans the row's first cell).
- QuantityDelegate: numeric-only inline editor; paints the quantity
  with a muted "was 3.5" beneath it when it differs from the saved one.
- ShareDelegate: a thin bar, category-colored, as wide as the row's
  share of the recipe's cost.
'''
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QLineEdit, QStyle, QStyledItemDelegate

from gui.models.components_model import ChangedRole, KindRole, PortionRole, ShareRole, WasRole
from gui.widgets.tag_badge import TagColorRole


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_CHANGED_BG = '#fff1da'
_SUBRECIPE_BG = '#e9f1d9'
_SUBRECIPE_FG = '#285900'
_TEMPLATE_BG = '#efe9de'
_RULE_BG, _RULE_FG = '#e6efe3', '#24502A'
_HAND_BG, _HAND_FG = '#fff0dc', '#8a4a00'


def _portion_pill(portion):
    '''(text, background, foreground) for a row portion rules size.'''
    if not portion:
        return None
    if portion['state'] == 'hand':
        return 'by hand', _HAND_BG, _HAND_FG
    if portion['state'] == 'fixed':
        return 'fixed', _RULE_BG, _RULE_FG
    if portion['siblings'] >= 2 and portion['pct'] is not None:
        return f'base {portion["pct"]:.0%}', _RULE_BG, _RULE_FG
    return 'base', _RULE_BG, _RULE_FG


def _paint_background(painter, option, index):
    '''Selection, else the changed-row wash. Returns the text color.'''
    if option.state & QStyle.State_Selected:
        painter.fillRect(option.rect, option.palette.highlight())
        return option.palette.highlightedText().color()
    if index.data(ChangedRole):
        painter.fillRect(option.rect, QColor(_CHANGED_BG))
    fg = index.data(Qt.ForegroundRole)
    return fg if isinstance(fg, QColor) else QColor(_KALE)


class ChangedRowDelegate(QStyledItemDelegate):
    '''Plain text cells that still pick up the changed-row wash. Painted
    directly: the table's ::item stylesheet would override a
    backgroundBrush set in initStyleOption.'''

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        # Template rows read as "managed by the format": italic, in the
        # table's own font (a fresh QFont from the model would reset
        # the size).
        if index.data(KindRole) == 'template':
            option.font.setItalic(True)

    def paint(self, painter, option, index):
        if index.data(ChangedRole) and not (option.state & QStyle.State_Selected):
            painter.fillRect(option.rect, QColor(_CHANGED_BG))
        super().paint(painter, option, index)


class NameDelegate(QStyledItemDelegate):
    PAD_X = 12
    DOT = 8

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        text_color = _paint_background(painter, option, index)
        rect = option.rect

        if index.data(ChangedRole) and not (option.state & QStyle.State_Selected):
            painter.fillRect(rect.x(), rect.y(), 3, rect.height(), QColor(_ROMAINE))

        x = rect.x() + self.PAD_X
        cy = rect.center().y()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(index.data(TagColorRole) or '#94a3b8'))
        painter.drawEllipse(QRectF(x, cy - self.DOT / 2 + 0.5, self.DOT, self.DOT))
        x += self.DOT + 8

        font = QFont(option.font)
        font.setItalic(index.data(KindRole) == 'template')
        if index.data(ChangedRole):
            font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(text_color)

        kind = index.data(KindRole)
        pill = {'recipe': 'sub-recipe', 'template': 'template'}.get(kind)
        pill_bg = QColor(_SUBRECIPE_BG if kind == 'recipe' else _TEMPLATE_BG)
        pill_fg = QColor(_SUBRECIPE_FG if kind == 'recipe' else _MUTED)
        portion_pill = None if pill else _portion_pill(index.data(PortionRole))
        if portion_pill:
            pill, bg, fg = portion_pill
            pill_bg, pill_fg = QColor(bg), QColor(fg)
        fm = painter.fontMetrics()
        pill_w = 0
        if pill:
            pill_font = QFont(option.font)
            pill_font.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.8))
            pill_w = _text_width(pill_font, pill) + 12
        name_w = rect.right() - x - (pill_w + 8 if pill else 0) - 4
        name = fm.elidedText(str(index.data(Qt.DisplayRole) or ''), Qt.ElideRight, name_w)
        painter.drawText(x, rect.y(), name_w, rect.height(), Qt.AlignVCenter | Qt.AlignLeft, name)

        if pill:
            px = x + fm.horizontalAdvance(name) + 8
            pill_rect = QRectF(px, cy - 9, pill_w, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(pill_bg)
            painter.drawRoundedRect(pill_rect, 4, 4)
            painter.setFont(pill_font)
            painter.setPen(pill_fg)
            painter.drawText(pill_rect, Qt.AlignCenter, pill)
        painter.restore()


class QuantityDelegate(QStyledItemDelegate):
    '''Inline numeric editor plus the "was" annotation.'''

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        validator = QDoubleValidator(0.0001, 1_000_000.0, 4, editor)
        validator.setNotation(QDoubleValidator.StandardNotation)
        editor.setValidator(validator)
        editor.setAlignment(Qt.AlignRight)
        editor.setStyleSheet(f'border: 2px solid {_ROMAINE}; border-radius: 5px;'
                             ' padding: 0 4px; background: #ffffff;')
        return editor

    def paint(self, painter, option, index):
        was = index.data(WasRole)
        painter.save()
        text_color = _paint_background(painter, option, index)
        rect = option.rect.adjusted(6, 0, -8, 0)
        font = QFont(option.font)
        font.setItalic(index.data(KindRole) == 'template')
        if index.data(ChangedRole):
            font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(text_color)
        qty = str(index.data(Qt.DisplayRole) or '')
        if was:
            top = rect.adjusted(0, 2, 0, -rect.height() // 2 + 2)
            painter.drawText(top, Qt.AlignRight | Qt.AlignVCenter, qty)
            small = QFont(option.font)
            small.setPointSizeF(max(7.0, option.font.pointSizeF() * 0.8))
            painter.setFont(small)
            painter.setPen(QColor(_MUTED))
            bottom = rect.adjusted(0, rect.height() // 2 - 2, 0, -2)
            painter.drawText(bottom, Qt.AlignRight | Qt.AlignVCenter, f'was {was}')
        else:
            painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, qty)
        painter.restore()


class ShareDelegate(QStyledItemDelegate):
    BAR_H = 6

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        _paint_background(painter, option, index)
        share = float(index.data(ShareRole) or 0)
        rect = option.rect.adjusted(8, 0, -8, 0)
        if share > 0:
            w = max(2.0, rect.width() * share)
            bar = QRectF(rect.x(), rect.center().y() - self.BAR_H / 2, w, self.BAR_H)
            painter.setPen(QPen(Qt.NoPen))
            painter.setBrush(QColor(index.data(TagColorRole) or '#94a3b8'))
            painter.drawRoundedRect(bar, 3, 3)
        painter.restore()


def _text_width(font, text):
    return QFontMetrics(font).horizontalAdvance(text)
