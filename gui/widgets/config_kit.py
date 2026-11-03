'''Shared pieces for Configure pages, per the Framework canvas's
Formats & templates page: a list column (heading, "+ New" button, a
note, rows) beside a detail area of labelled fields and cards.
'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout


KALE = '#082c00'
ROMAINE = '#347200'
ROMAINE_HOVER = '#285900'
MUTED = '#55624c'
BORDER = '#ebe1cd'
FIELD_BORDER = '#7d8771'
BG = '#fffaf2'
SELECTED = '#fff1da'
WARN = '#8a4a00'

LIST_STYLE = f'''
    QListWidget {{ border: 0; background: transparent; outline: 0; }}
    QListWidget::item {{ border: 1px solid {BORDER}; border-radius: 8px; background: #ffffff;
        color: {KALE}; padding: 8px 10px; margin-bottom: 6px; }}
    QListWidget::item:selected {{ border: 2px solid {ROMAINE}; background: {SELECTED}; color: {KALE}; }}
    QListWidget::item:hover:!selected {{ border-color: {FIELD_BORDER}; }}
'''


def heading(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {KALE}; font-size: 20px; font-weight: 650;')
    return lbl


def subheading(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {KALE}; font-size: 15px; font-weight: 600;')
    return lbl


def note(text):
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setMinimumWidth(1)
    lbl.setStyleSheet(f'color: {MUTED}; font-size: 12px;')
    return lbl


def eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def button(text, primary=False, danger=False):
    btn = QPushButton(text)
    btn.setAutoDefault(False)
    btn.setCursor(Qt.PointingHandCursor)
    if primary:
        btn.setStyleSheet(f'QPushButton {{ min-height: 30px; padding: 0 14px; border: 0; border-radius: 8px;'
                          f' background: {ROMAINE}; color: #ffffff; font-weight: 600; }}'
                          f' QPushButton:hover {{ background: {ROMAINE_HOVER}; }}')
    else:
        color = WARN if danger else KALE
        btn.setStyleSheet(f'QPushButton {{ min-height: 30px; padding: 0 12px; border: 1px solid {FIELD_BORDER};'
                          f' border-radius: 8px; background: #ffffff; color: {color}; }}'
                          ' QPushButton:hover { background: #f3ece0; }'
                          ' QPushButton:disabled { color: #a7ad9c; border-color: #d8d2c4; }')
    return btn


def field(width=None):
    edit = QLineEdit()
    edit.setStyleSheet(f'QLineEdit {{ min-height: 32px; padding: 0 10px; border: 1px solid {FIELD_BORDER};'
                       f' border-radius: 4px; background: #ffffff; color: {KALE}; }}'
                       f' QLineEdit:focus {{ border: 2px solid {ROMAINE}; padding: 0 9px; }}')
    if width:
        edit.setFixedWidth(width)
    return edit


def card():
    '''A white rounded card; returns (frame, its QVBoxLayout).'''
    frame = QFrame()
    frame.setObjectName('ConfigCard')
    frame.setStyleSheet(f'QFrame#ConfigCard {{ background: #ffffff; border: 1px solid {BORDER};'
                        ' border-radius: 8px; }')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 16)
    layout.setSpacing(10)
    return frame, layout
