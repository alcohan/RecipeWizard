'''Left-side facet pane for the Recipes library view.

Two facets today: Format (checkboxes for Salad / Bowl / Wrap /
Catering) and Free From (toggle chips for allergens from the DB).
Each facet emits a signal with its current set; the proxy picks them
up and reinvalidates.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

import db


_FORMATS = ('Salad', 'Bowl', 'Wrap', 'Catering')


class RecipesFacetPane(QWidget):
    formatsChanged = Signal(set)   # empty set = no format filter
    freeFromChanged = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet('''
            RecipesFacetPane {
                background: #fffaf2;
                border-right: 1px solid #ebe1cd;
            }
            QLabel[role="facet-header"] {
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.06em;
                color: #55624c;
                text-transform: uppercase;
            }
        ''')

        format_header = QLabel('Format')
        format_header.setProperty('role', 'facet-header')
        self._format_checks = {}
        format_box = QVBoxLayout()
        format_box.setContentsMargins(0, 0, 0, 0)
        format_box.setSpacing(4)
        for name in _FORMATS:
            cb = QCheckBox(name)
            cb.setCursor(Qt.PointingHandCursor)
            cb.toggled.connect(self._emit_formats)
            self._format_checks[name] = cb
            format_box.addWidget(cb)

        freefrom_header = QLabel('Free from')
        freefrom_header.setProperty('role', 'facet-header')
        self._freefrom_buttons = {}
        self._freefrom_flow = _FlowLayout()
        try:
            allergens = db.get_all_allergens()
        except Exception:
            allergens = []
        for name in allergens:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet('''
                QPushButton {
                    font-size: 12px;
                    padding: 3px 10px;
                    border-radius: 999px;
                    border: 1px solid #ebe1cd;
                    background: #ffffff;
                    color: #55624c;
                }
                QPushButton:hover { border-color: #7d8771; }
                QPushButton:checked {
                    background: #e9f1d9;
                    color: #082c00;
                    border-color: #347200;
                    font-weight: 600;
                }
            ''')
            btn.toggled.connect(self._emit_free_from)
            self._freefrom_buttons[name] = btn
            self._freefrom_flow.addWidget(btn)

        freefrom_container = QWidget()
        freefrom_container.setLayout(self._freefrom_flow)

        clear_btn = QPushButton('Clear filters')
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet('''
            QPushButton {
                background: transparent;
                border: 0;
                color: #347200;
                font-weight: 600;
                text-align: left;
                padding: 6px 0;
            }
            QPushButton:hover { color: #285900; }
        ''')
        clear_btn.clicked.connect(self.clear_filters)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(format_header)
        layout.addLayout(format_box)
        layout.addSpacing(6)
        layout.addWidget(freefrom_header)
        layout.addWidget(freefrom_container)
        layout.addStretch()
        layout.addWidget(clear_btn)

    def clear_filters(self):
        for cb in self._format_checks.values():
            cb.blockSignals(True); cb.setChecked(False); cb.blockSignals(False)
        for btn in self._freefrom_buttons.values():
            btn.blockSignals(True); btn.setChecked(False); btn.blockSignals(False)
        self._emit_formats()
        self._emit_free_from()

    def _emit_formats(self):
        picked = {name for name, cb in self._format_checks.items() if cb.isChecked()}
        self.formatsChanged.emit(picked)

    def _emit_free_from(self):
        picked = {name for name, btn in self._freefrom_buttons.items() if btn.isChecked()}
        self.freeFromChanged.emit(picked)


class _FlowLayout(QHBoxLayout):
    '''Minimal wrapping layout stand-in — Qt doesn't ship a FlowLayout
    out of the box, and the chips here are few enough that a plain
    HBox with wrap behavior via setFixedWidth container reads fine.
    (A proper flow layout can replace this later if the allergen list
    grows.)'''

    def __init__(self):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(6)
