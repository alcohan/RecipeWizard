'''Compare tray, docked — a strip of mini recipe cards that sits under
every place, above the status bar.

The tray has three states: collapsed to the status-bar chip, docked
as this strip, or expanded into the Analytics place. Ctrl+Shift+C and
the status-bar chip flip collapsed ↔ docked; "Expand to Analytics"
goes to the full view. The main window hides the strip while
Analytics is showing, since that place IS the expanded tray.
'''
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

import db
from gui.widgets.elided_label import ElidedLabel


_KALE = '#082c00'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_DEFAULT_FOOD_COST_TARGET = 0.28


class CompareTrayDock(QFrame):
    expandRequested = Signal()
    recipeActivated = Signal(int)

    def __init__(self, compare_tray, parent=None):
        super().__init__(parent)
        self._tray = compare_tray
        self.setObjectName('CompareTrayDock')
        self.setStyleSheet(f'''
            QFrame#CompareTrayDock {{
                background: #fffaf2;
                border-top: 1px solid {_BORDER};
            }}
        ''')

        title = QLabel('Compare tray')
        title.setStyleSheet(f'color: {_KALE}; font-weight: 650; font-size: 14px;')
        self._summary = QLabel('')
        self._summary.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')

        clear_btn = QPushButton('Clear')
        clear_btn.setFlat(True)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._tray.clear)
        expand_btn = QPushButton('Expand to Analytics')
        expand_btn.setCursor(Qt.PointingHandCursor)
        expand_btn.clicked.connect(self.expandRequested.emit)
        # No collapse button here: the status-bar chip that opened the
        # strip is the one toggle, so closing is a click in the same spot.

        header = QHBoxLayout()
        header.setSpacing(12)
        header.addWidget(title)
        header.addWidget(self._summary)
        header.addStretch()
        header.addWidget(clear_btn)
        header.addWidget(expand_btn)

        self._cards_host = QWidget()
        self._cards_layout = QHBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidget(self._cards_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFixedHeight(84)
        scroll.setStyleSheet('QScrollArea { background: transparent; }')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 10)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(scroll)

        self._tray.changed.connect(self.rebuild)
        self.rebuild()

    def rebuild(self):
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        ids = self._tray.ids()
        n = len(ids)
        self._summary.setText(
            f"{n} recipe{'s' if n != 1 else ''} · Space adds the selected recipe"
        )
        if not ids:
            hint = QLabel('Select a recipe and press Space to add it here.')
            hint.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')
            self._cards_layout.addWidget(hint)
        for rid in ids:
            try:
                recipe = db.recipe_info(rid)
            except Exception:
                continue
            card = _MiniCard(recipe)
            card.removeClicked.connect(self._tray.remove)
            card.activated.connect(self.recipeActivated.emit)
            self._cards_layout.addWidget(card)
        self._cards_layout.addStretch()


class _MiniCard(QFrame):
    '''Name with a remove ×, then cost · food cost % · kcal.'''

    removeClicked = Signal(int)
    activated = Signal(int)

    def __init__(self, recipe, parent=None):
        super().__init__(parent)
        self._id = recipe['Id']
        self.setObjectName('MiniCard')
        self.setFixedWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Double-click to open')
        self.setStyleSheet(f'''
            QFrame#MiniCard {{
                background: #ffffff;
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        ''')

        name = ElidedLabel(recipe['Name'])
        name.setStyleSheet(f'color: {_KALE}; font-weight: 600;')
        remove = QToolButton()
        remove.setText('×')
        remove.setAutoRaise(True)
        remove.setToolTip('Remove from tray')
        remove.clicked.connect(lambda: self.removeClicked.emit(self._id))

        top = QHBoxLayout()
        top.addWidget(name, stretch=1)
        top.addWidget(remove)

        stats = QLabel(_stats_text(recipe))
        stats.setTextFormat(Qt.RichText)
        stats.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 4, 8)
        layout.setSpacing(2)
        layout.addLayout(top)
        layout.addWidget(stats)

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self._id)
        super().mouseDoubleClickEvent(event)


def _stats_text(recipe):
    parts = []
    try:
        cost = float(recipe.get('CostRaw') or 0)
    except (TypeError, ValueError):
        cost = 0.0
    parts.append(f'<b style="color: {_KALE}">${cost:.2f}</b>')
    try:
        price = float(recipe.get('MenuPrice') or 0)
    except (TypeError, ValueError):
        price = 0.0
    if price > 0 and cost > 0:
        pct = cost / price
        target = QSettings().value('food_cost/target_pct', _DEFAULT_FOOD_COST_TARGET, type=float)
        style = ' style="color: #8a4a00; font-weight: 600"' if pct > target else ''
        parts.append(f'<span{style}>{pct * 100:.1f}%</span>')
    kcal = recipe.get('Calories')
    if kcal not in (None, ''):
        parts.append(f'{kcal} kcal')
    return ' · '.join(parts)
