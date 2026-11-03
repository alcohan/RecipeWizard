'''Toolbar controls shared by the Recipes and Ingredients places, so the
dropdowns and the view switch match: 32 px tall, 6 px corners, the
same field border.

- ToolbarCombo: a QComboBox that draws its own chevron (the native
  Windows arrow sits in a square, differently styled box).
- SegmentedSwitch: a row of exclusive buttons in one rounded frame; the
  end buttons round their outer corners so the checked fill follows the
  frame instead of showing square corners inside it.
- ToggleSwitch: an on/off switch (a checkable button drawn as a track
  and knob) for settings like the Library's Include archived.
'''
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QPushButton


KALE = '#082c00'
ROMAINE = '#347200'
MUTED = '#55624c'
FIELD_BORDER = '#7d8771'
HEIGHT = 32
RADIUS = 6
_ARROW_W = 24


class ToolbarCombo(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f'''
            QComboBox {{ min-height: {HEIGHT - 2}px; max-height: {HEIGHT - 2}px;
                padding: 0 {_ARROW_W}px 0 10px; color: {KALE}; background: #ffffff;
                border: 1px solid {FIELD_BORDER}; border-radius: {RADIUS}px; }}
            QComboBox:hover {{ border-color: {KALE}; }}
            QComboBox:focus {{ border: 2px solid {ROMAINE}; padding: 0 {_ARROW_W - 1}px 0 9px; }}
            QComboBox::drop-down {{ width: 0; border: 0; }}
            QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
            QComboBox QAbstractItemView {{ border: 1px solid {FIELD_BORDER}; background: #ffffff;
                color: {KALE}; selection-background-color: #fff1da; selection-color: {KALE};
                outline: 0; }}
        ''')

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(MUTED), 1.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        cx, cy = self.width() - _ARROW_W / 2 - 2, self.height() / 2
        path = QPainterPath(QPointF(cx - 4, cy - 2))
        path.lineTo(cx, cy + 2)
        path.lineTo(cx + 4, cy - 2)
        painter.drawPath(path)


class SegmentedSwitch(QFrame):
    '''Exclusive buttons for (key, label) options. Emits changed(key)
    when the user picks one; set_current(key) doesn't emit.'''

    changed = Signal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName('SegmentedSwitch')
        inner = RADIUS - 1
        self.setStyleSheet(f'''
            QFrame#SegmentedSwitch {{ border: 1px solid {FIELD_BORDER}; border-radius: {RADIUS}px;
                background: #ffffff; }}
            QFrame#SegmentedSwitch QPushButton {{ border: 0; border-radius: 0; padding: 0 14px;
                min-height: {HEIGHT - 2}px; max-height: {HEIGHT - 2}px; background: #ffffff; color: {KALE}; }}
            QFrame#SegmentedSwitch QPushButton:hover:!checked {{ background: #f3ece0; }}
            QFrame#SegmentedSwitch QPushButton:checked {{ background: {ROMAINE}; color: #ffffff;
                font-weight: 600; }}
            QFrame#SegmentedSwitch QPushButton[edge="first"] {{
                border-top-left-radius: {inner}px; border-bottom-left-radius: {inner}px; }}
            QFrame#SegmentedSwitch QPushButton[edge="last"] {{
                border-top-right-radius: {inner}px; border-bottom-right-radius: {inner}px; }}
        ''')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self.buttons = {}
        for i, (key, label) in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setCursor(Qt.PointingHandCursor)
            if i == 0:
                btn.setProperty('edge', 'first')
            if i == len(options) - 1:
                btn.setProperty('edge', 'last')
            btn.clicked.connect(lambda _c=False, k=key: self.changed.emit(k))
            self._group.addButton(btn)
            self.buttons[key] = btn
            layout.addWidget(btn)

    def set_current(self, key):
        self.buttons[key].setChecked(True)

    def current(self):
        for key, btn in self.buttons.items():
            if btn.isChecked():
                return key
        return None


class ToggleSwitch(QAbstractButton):
    '''On/off switch: ROMAINE track with the knob right when on.'''

    W, H = 34, 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self):
        return QSize(self.W + 4, self.H + 4)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(2, 2, self.W, self.H)
        on = self.isChecked()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(ROMAINE if on else '#c9c2b2'))
        painter.drawRoundedRect(track, self.H / 2, self.H / 2)
        if self.hasFocus():
            painter.setPen(QPen(QColor(KALE), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(track.adjusted(-1, -1, 1, 1), self.H / 2 + 1, self.H / 2 + 1)
        d = self.H - 4
        x = track.right() - d - 2 if on else track.left() + 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#ffffff'))
        painter.drawEllipse(QRectF(x, track.top() + 2, d, d))
