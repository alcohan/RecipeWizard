from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class SummaryCard(QFrame):
    '''A flat stat tile: big number on top, small label underneath. Reused
    on the home tab and intended to be reused on any future dashboard.

    When `clickable=True` the card emits `clicked` on left-press and gets
    a hover effect — used on the home tab so the count card doubles as a
    shortcut to its tab.'''

    clicked = Signal()

    def __init__(self, label, value=0, clickable=False, parent=None):
        super().__init__(parent)
        self.setObjectName('SummaryCard')
        self._clickable = clickable
        self._apply_style()
        self.setMinimumSize(140, 96)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        self.value_label = QLabel(str(value))
        self.value_label.setAlignment(Qt.AlignCenter)
        self.value_label.setStyleSheet('font-size: 28pt; font-weight: bold;')

        self.text_label = QLabel(label)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet('color: #666; font-size: 11pt;')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.value_label)
        layout.addWidget(self.text_label)

    def _apply_style(self):
        hover_rule = '''
            QFrame#SummaryCard:hover {
                border-color: #2a7;
                background-color: #f5fff5;
            }
        ''' if self._clickable else ''
        self.setStyleSheet(f'''
            QFrame#SummaryCard {{
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }}
            {hover_rule}
            QFrame#SummaryCard QLabel {{ border: 0; }}
        ''')

    def set_value(self, value):
        self.value_label.setText(str(value))

    def mousePressEvent(self, event):
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
