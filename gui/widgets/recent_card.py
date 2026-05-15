'''Compact "recently edited" card for the home tab.

Each card shows a small thumbnail (recipe wedge or ingredient image),
the item's name, and a relative timestamp. Clicking anywhere on the
card emits `activated(kind, id)` so the home tab can route to the right
edit dialog without callers needing to know which is which.
'''
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QThreadPool
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from gui.widgets.ingredient_thumb import IngredientThumb
from gui.widgets.wedge_view import WedgeView


_THUMB_SIZE = 56
_CARD_WIDTH = 220
_CARD_HEIGHT = 76


def _relative_time(when_str):
    '''Format a sqlite-style "YYYY-MM-DD HH:MM:SS" UTC timestamp as a
    short relative phrase ("just now", "5m ago", "3d ago") or a fallback
    date once it crosses a week.'''
    if not when_str:
        return ''
    try:
        when = datetime.strptime(when_str, '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return ''
    # sqlite datetime('now') returns UTC; compare against UTC now.
    delta = datetime.utcnow() - when
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes}m ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours}h ago'
    days = hours // 24
    if days < 7:
        return f'{days}d ago'
    return when.strftime('%b %d')


class RecentItemCard(QFrame):
    '''A clickable summary tile for one recently-edited item.'''

    activated = Signal(str, int)  # (kind, id)

    def __init__(self, kind, item_id, name, when_str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.item_id = item_id
        self.setObjectName('RecentItemCard')
        self.setFixedSize(_CARD_WIDTH, _CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('''
            QFrame#RecentItemCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QFrame#RecentItemCard:hover {
                border-color: #2a7;
                background-color: #f5fff5;
            }
            QFrame#RecentItemCard QLabel { border: 0; background: transparent; }
        ''')

        thumb = self._build_thumb(kind, item_id)
        thumb.setAttribute(Qt.WA_TransparentForMouseEvents)

        name_label = QLabel(name or '')
        name_label.setStyleSheet('font-weight: bold;')
        # Truncate at the visible width — no word wrap on a 1-line cell.
        name_label.setTextFormat(Qt.PlainText)
        name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        name_label.setToolTip(name or '')

        time_label = QLabel(_relative_time(when_str))
        time_label.setStyleSheet('color: #888; font-size: 9pt;')
        time_label.setToolTip(when_str or '')
        time_label.setAttribute(Qt.WA_TransparentForMouseEvents)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addStretch()
        text_col.addWidget(name_label)
        text_col.addWidget(time_label)
        text_col.addStretch()

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 10, 6)
        row.setSpacing(8)
        row.addWidget(thumb)
        row.addLayout(text_col, stretch=1)

    def _build_thumb(self, kind, item_id):
        if kind == 'recipe':
            # Defer + async render so a strip of 6 doesn't block the UI thread.
            wedge = WedgeView(item_id, size=_THUMB_SIZE, defer=True)
            wedge.render_async(QThreadPool.globalInstance())
            return wedge
        # Ingredient: scaled image if we have one, otherwise a tag-colored letter.
        return IngredientThumb(item_id, size=_THUMB_SIZE)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.kind, self.item_id)
        super().mousePressEvent(event)
