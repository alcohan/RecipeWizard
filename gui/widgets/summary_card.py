from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class SummaryCard(QFrame):
    '''A flat stat tile: big number on top, small label underneath. Reused
    on the home tab and intended to be reused on any future dashboard.'''

    def __init__(self, label, value=0, parent=None):
        super().__init__(parent)
        self.setObjectName('SummaryCard')
        self.setStyleSheet('''
            QFrame#SummaryCard {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QFrame#SummaryCard QLabel { border: 0; }
        ''')
        self.setMinimumSize(140, 96)

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

    def set_value(self, value):
        self.value_label.setText(str(value))
