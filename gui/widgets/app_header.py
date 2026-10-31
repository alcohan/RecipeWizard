'''Top app bar — kale background, parmesan text, five place names
along the left with an avocado underline on the active one, and a
"prices as of" freshness line pinned to the right.

Replaces PlaceRail from the earlier left-rail design iteration. The
API intentionally mirrors it (add_place, set_current, install_shortcuts,
placeChanged) so main_window swaps one widget for the other without
other code changes.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


# Evergreens tokens — the brand's app-bar palette.
_CHROME_BG = '#082c00'            # kale
_ON_CHROME = '#fff1da'            # parmesan
_CHROME_ACCENT = '#bbca00'        # avocado
_HEADER_HEIGHT = 44


class AppHeader(QFrame):
    '''Horizontal navigation band. Five places max (⌘1-⌘5), avocado
    underline on the active place, "prices as of" pinned right.

    `icon_key` is accepted on add_place for parity with the old rail
    but ignored — the app bar is text-only per the current design.'''

    placeChanged = Signal(int)
    MAX_PLACES = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('AppHeader')
        self.setFixedHeight(_HEADER_HEIGHT)
        self.setStyleSheet(f'''
            QFrame#AppHeader {{
                background: {_CHROME_BG};
                border: 0;
            }}
            QFrame#AppHeader QLabel {{
                color: {_ON_CHROME};
                background: transparent;
            }}
        ''')
        self._buttons = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(0)

        # Logo monogram — small avocado-filled pill with "R" in kale.
        # Later we can swap for a real SVG mark; for now this is enough
        # to carry the brand ink at the leftmost position.
        monogram = QLabel('R')
        monogram.setAlignment(Qt.AlignCenter)
        monogram.setFixedSize(26, 24)
        monogram.setStyleSheet(
            f'background: {_CHROME_ACCENT}; color: {_CHROME_BG};'
            ' border-radius: 4px; font-weight: 700; font-size: 13px;'
        )
        layout.addWidget(monogram)

        # Thin kale→parmesan divider.
        divider = QLabel()
        divider.setFixedSize(1, 20)
        divider.setStyleSheet(f'background: {_ON_CHROME};')
        layout.addSpacing(12)
        layout.addWidget(divider)
        layout.addSpacing(12)

        # App name — reads as a left-aligned title before the place list.
        app_name = QLabel('RecipeWizard')
        app_name.setStyleSheet('color: #fff1da; font-weight: 600; font-size: 14px;')
        layout.addWidget(app_name)
        layout.addSpacing(24)

        # Container for place buttons so we can insert later (before the
        # right-side freshness label).
        self._places_row = QHBoxLayout()
        self._places_row.setContentsMargins(0, 0, 0, 0)
        self._places_row.setSpacing(0)
        layout.addLayout(self._places_row)

        layout.addStretch()

        # Right-side freshness label — "Prices as of Oct 14".
        self._freshness_label = QLabel('')
        self._freshness_label.setStyleSheet('color: #fff1da; font-size: 13px;')
        layout.addWidget(self._freshness_label)

    def add_place(self, label, _icon_key=None):
        if len(self._buttons) >= self.MAX_PLACES:
            raise RuntimeError(
                f'AppHeader is capped at {self.MAX_PLACES} places by design')
        idx = len(self._buttons)
        btn = _PlaceButton(label)
        btn.clicked.connect(lambda _checked=False, i=idx: self.set_current(i))
        self._buttons.append(btn)
        self._places_row.addWidget(btn)
        if idx == 0:
            btn.set_active(True)
        return idx

    def add_spacer(self):
        '''Compatibility no-op. The left rail used this to push Health
        to the bottom; the top bar lays places left-to-right so it has
        no equivalent position.'''
        return

    def set_current(self, index):
        if not (0 <= index < len(self._buttons)):
            return
        already = self._buttons[index].is_active()
        for i, b in enumerate(self._buttons):
            b.set_active(i == index)
        if not already:
            self.placeChanged.emit(index)

    def current(self):
        for i, b in enumerate(self._buttons):
            if b.is_active():
                return i
        return 0

    def install_shortcuts(self, host):
        '''Register ⌘1..⌘N on `host`. Call once after all add_place
        calls finish.'''
        for i, _b in enumerate(self._buttons):
            sc = QShortcut(QKeySequence(f'Ctrl+{i + 1}'), host)
            sc.activated.connect(lambda i=i: self.set_current(i))

    def set_freshness(self, text):
        '''"Prices as of Oct 14" — set by main_window from the latest
        supplier-price date. Empty string hides the label.'''
        self._freshness_label.setText(text or '')
        self._freshness_label.setVisible(bool(text))


class _PlaceButton(QPushButton):
    '''Clickable place name on the kale bar. Active state draws the
    avocado underline + bold weight — not a background flood.'''

    def __init__(self, label, parent=None):
        super().__init__(label, parent)
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(_HEADER_HEIGHT)
        self._active = False
        self._apply_style()

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f'''
                QPushButton {{
                    color: {_ON_CHROME};
                    background: transparent;
                    border: 0;
                    border-bottom: 3px solid {_CHROME_ACCENT};
                    padding: 0 14px;
                    font-size: 14px;
                    font-weight: 650;
                }}
            ''')
        else:
            self.setStyleSheet(f'''
                QPushButton {{
                    color: {_ON_CHROME};
                    background: transparent;
                    border: 0;
                    border-bottom: 3px solid transparent;
                    padding: 0 14px;
                    font-size: 14px;
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    border-bottom: 3px solid rgba(187, 202, 0, 0.4);
                }}
            ''')

    def set_active(self, active):
        self._active = bool(active)
        self._apply_style()

    def is_active(self):
        return self._active
