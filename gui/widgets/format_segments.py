'''Format picker for the recipe editor: one segment per recipe-format
tag plus "None", as a single connected control.

Emits selectionChanged(new_tag_id, prev_tag_id) — the same contract
as TagSelector — so the editor can route the change through its undo
stack. `set_selected` updates the control without emitting.
'''
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton

import db


_ROMAINE = '#347200'
_MUTED = '#55624c'


class FormatSegments(QFrame):
    selectionChanged = Signal(object, object)   # new tag id (or None), previous

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('FormatSegments')
        self.setStyleSheet(f'''
            QFrame#FormatSegments {{
                border: 1px solid #7d8771;
                border-radius: 8px;
                background: #ffffff;
            }}
            QFrame#FormatSegments QPushButton {{
                border: 0;
                padding: 0 12px;
                min-height: 32px;
                background: transparent;
                color: {_MUTED};
            }}
            QFrame#FormatSegments QPushButton:checked {{
                background: {_ROMAINE};
                color: #ffffff;
                font-weight: 600;
            }}
            QFrame#FormatSegments QPushButton:hover:!checked {{
                background: #f3ece0;
            }}
        ''')
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._current = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        options = [(t['id'], t['name']) for t in db.get_tags('recipe')] + [(None, 'None')]
        for tag_id, name in options:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setProperty('tagId', tag_id)
            btn.setToolTip('No format — e.g. a sub-recipe' if tag_id is None else
                           f'{name}: applies the {name} template')
            btn.clicked.connect(lambda _c=False, t=tag_id: self._on_clicked(t))
            self._group.addButton(btn)
            layout.addWidget(btn)

    def selected(self):
        return self._current

    def set_selected(self, tag_id):
        self._current = tag_id
        for btn in self._group.buttons():
            btn.setChecked(btn.property('tagId') == tag_id)

    def _on_clicked(self, tag_id):
        prev = self._current
        if tag_id == prev:
            return
        self._current = tag_id
        self.selectionChanged.emit(tag_id, prev)
