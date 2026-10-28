'''Left place-rail: five vertical slots that switch the main workspace.

Replaces the old QTabWidget-based navigation. The design is strict —
exactly five slots, labelled icons, ⌘1–⌘5. The rail never scrolls and
never holds more than five.

Icons come from the design canvas's inline SVGs, re-rendered via
QSvgRenderer so they recolor cleanly with the active-state tint.
'''
from PySide6.QtCore import QByteArray, QRectF, Qt, QSize, Signal
from PySide6.QtGui import (
    QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QToolButton, QVBoxLayout, QWidget,
)


RAIL_WIDTH = 84
_ICON_PX = 22
_ACTIVE_FG = '#1E3F78'
_ACTIVE_BG = '#E6EDF8'
_IDLE_FG = '#3F4641'

# Line-art paths lifted straight from the design canvas's SVGs. One
# path (or list of paths) per place. 24-unit viewBox, 1.8 stroke.
_ICON_PATHS = {
    'recipes': ['circle:12,12,8', 'M12 4v8l6 5'],
    'ingredients': ['M5 19c0-8 6-14 14-14 0 8-6 14-14 14z', 'M5 19l8-8'],
    'compare': ['M5 19V9M12 19V5M19 19v-7'],
    'suppliers': ['M4 17l5-5 4 3 7-8', 'M15 7h5v5'],
    'health': ['M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z', 'M9 12l2 2 4-4'],
}


def _icon_svg(key, stroke_hex):
    '''Compose an inline SVG for the given icon key with the requested
    stroke color. Each path is a straight <path d>, except the 'circle:'
    prefix which becomes a <circle>. One file-size trick: no fills,
    only strokes.'''
    pieces = []
    for p in _ICON_PATHS[key]:
        if p.startswith('circle:'):
            cx, cy, r = p[len('circle:'):].split(',')
            pieces.append(
                f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none"'
                f' stroke="{stroke_hex}" stroke-width="1.8"/>'
            )
        else:
            pieces.append(
                f'<path d="{p}" fill="none" stroke="{stroke_hex}"'
                f' stroke-width="1.8" stroke-linecap="round"'
                f' stroke-linejoin="round"/>'
            )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        + ''.join(pieces) + '</svg>'
    )


def _render_icon(key, color_hex, size=_ICON_PX, scale=2):
    '''Rasterize an SVG icon at (size*scale)² for high-DPI crispness,
    then set device pixel ratio so Qt treats it as a `size` icon.'''
    renderer = QSvgRenderer(QByteArray(_icon_svg(key, color_hex).encode('utf-8')))
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


class _RailButton(QToolButton):
    '''One rail slot. Icon above label, checkable, exclusive via
    QButtonGroup managed on PlaceRail. The icon recolors between
    idle and active states — we pre-render both pixmaps so :checked
    styling just flips which one shows.'''

    def __init__(self, icon_key, label, parent=None):
        super().__init__(parent)
        self._icon_key = icon_key
        self.setText(label)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setCheckable(True)
        self.setAutoRaise(True)
        self.setIconSize(QSize(_ICON_PX, _ICON_PX))
        self.setFixedWidth(RAIL_WIDTH - 16)
        self._idle_icon = _render_icon(icon_key, _IDLE_FG)
        self._active_icon = _render_icon(icon_key, _ACTIVE_FG)
        self.setIcon(self._idle_icon)
        self.toggled.connect(self._update_icon)
        self.setStyleSheet(f'''
            QToolButton {{
                color: {_IDLE_FG};
                background: transparent;
                border: none;
                border-radius: 10px;
                padding: 10px 4px;
                font-size: 11px;
                font-weight: 500;
            }}
            QToolButton:checked {{
                color: {_ACTIVE_FG};
                background: {_ACTIVE_BG};
                font-weight: 600;
            }}
            QToolButton:hover:!checked {{
                background: #ECEAE4;
            }}
        ''')
        self.setCursor(Qt.PointingHandCursor)

    def _update_icon(self, checked):
        self.setIcon(self._active_icon if checked else self._idle_icon)


class PlaceRail(QWidget):
    '''Vertical place switcher. The main window creates one, binds the
    QStackedWidget's current-index to placeChanged, and registers
    ⌘1-⌘N shortcuts on itself.

    Places are added via add_place(label, icon_key); indices are
    assigned in order and used by both the signal and the shortcuts.
    The design caps the rail at 5; add_place refuses more.'''

    placeChanged = Signal(int)

    MAX_PLACES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(RAIL_WIDTH)
        self.setAutoFillBackground(True)
        self.setStyleSheet('PlaceRail { background: #F7F6F2; border-right: 1px solid #E2E0D9; }')

        self._buttons = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 12, 8, 12)
        self._layout.setSpacing(4)
        # Trailing stretch; new buttons get inserted before it (and
        # before any "spacer" item set via add_spacer).
        self._layout.addStretch()

    def add_place(self, label, icon_key):
        '''Append a place. Returns its 0-based index for the caller to
        wire into QStackedWidget.setCurrentIndex. Raises if the rail is
        already at MAX_PLACES.'''
        if len(self._buttons) >= self.MAX_PLACES:
            raise RuntimeError(
                f'PlaceRail is capped at {self.MAX_PLACES} places by design')
        idx = len(self._buttons)
        btn = _RailButton(icon_key, label)
        btn.clicked.connect(lambda _checked=False, i=idx: self.set_current(i))
        self._buttons.append(btn)
        # Insert before the trailing stretch so new buttons stack
        # from the top. The stretch is always at `count() - 1`.
        self._layout.insertWidget(self._layout.count() - 1, btn)
        if idx == 0:
            btn.setChecked(True)
        return idx

    def add_spacer(self):
        '''Visually push remaining places to the bottom of the rail.
        The design keeps Library Health pinned at the bottom; call this
        between the 4th and 5th add_place.'''
        self._layout.insertStretch(self._layout.count() - 1)

    def set_current(self, index):
        '''Programmatically switch places. Idempotent, emits
        placeChanged only when the index actually moves.'''
        if not (0 <= index < len(self._buttons)):
            return
        if self._buttons[index].isChecked() and all(
                b.isChecked() == (i == index) for i, b in enumerate(self._buttons)
        ):
            # Already current; no churn.
            return
        for i, b in enumerate(self._buttons):
            b.blockSignals(True)
            b.setChecked(i == index)
            b.blockSignals(False)
        self.placeChanged.emit(index)

    def current(self):
        for i, b in enumerate(self._buttons):
            if b.isChecked():
                return i
        return 0

    def install_shortcuts(self, host):
        '''Register ⌘1..⌘N on `host` (the main window). Called once
        after add_place calls finish; adding a place later won't get a
        shortcut without a re-install.'''
        for i, _b in enumerate(self._buttons):
            seq = QKeySequence(f'Ctrl+{i + 1}')
            sc = QShortcut(seq, host)
            sc.activated.connect(lambda i=i: self.set_current(i))
