'''Two-mode segmented control for switching between gallery and table views.

Modes are passed as (name, label) tuples; the caller is responsible
for persisting and restoring the choice (typically via QSettings).
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget


_QSS = '''
    QPushButton {
        background: white;
        border: 1px solid #ccc;
        padding: 4px 14px;
        font-size: 10pt;
    }
    QPushButton:checked {
        background: #2a7;
        color: white;
        border-color: #2a7;
    }
    QPushButton:hover:!checked {
        background: #f5fff5;
        border-color: #2a7;
    }
'''


class ViewToggle(QWidget):
    '''Emits `viewChanged(name)` when the user picks a different mode.
    Initial selection is the `current` argument, falling back to the
    first listed mode if `current` doesn't match.'''

    viewChanged = Signal(str)

    def __init__(self, modes, current=None, parent=None):
        super().__init__(parent)
        self._buttons = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for name, label in modes:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_QSS)
            self._buttons[name] = btn
            self._group.addButton(btn)
            layout.addWidget(btn)
            btn.toggled.connect(self._on_toggle)

        start = current if current in self._buttons else next(iter(self._buttons))
        self._buttons[start].setChecked(True)

    def _on_toggle(self, checked):
        # Only react to the press that switched into a mode; the matching
        # uncheck on the previous button fires the same signal.
        if not checked:
            return
        for name, btn in self._buttons.items():
            if btn.isChecked():
                self.viewChanged.emit(name)
                return

    def setCurrent(self, name):
        if name in self._buttons:
            self._buttons[name].setChecked(True)

    def current(self):
        for name, btn in self._buttons.items():
            if btn.isChecked():
                return name
        return None
