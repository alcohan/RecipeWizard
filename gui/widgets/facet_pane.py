'''Shared left filter pane for the Recipes and Ingredients places:
collapsible sections of checkboxes with counts.

Section modes:
- "include": everything starts checked; unchecking hides those rows.
- "any" / "all" / "exclude": everything starts unchecked; checking
  shows rows with any / all of the checked items, or hides rows with
  any of them.

Sections collapse (the choice is remembered per place and section). A
collapsed section that's filtering says so in its header, so a hidden
filter never hides rows silently. Sections with more than five options
get an All / None toggle.

Subclasses declare SECTIONS and SETTINGS_PREFIX, fill each section
with `_fill(group, items)` and read checks with `checked(group)`.
'''
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)


KALE = '#082c00'
ROMAINE = '#347200'
MUTED = '#55624c'
BORDER = '#ebe1cd'
WARN = '#8a4a00'

_ALL_TOGGLE_MIN = 6   # show All / None when a section has more than five options


class FacetSection(QWidget):
    '''Header (arrow, title, filtered marker, All/None) over a body of
    rows.'''

    toggledAll = Signal(bool)    # True = check all

    def __init__(self, key, title, mode, default_open, settings_prefix, parent=None):
        super().__init__(parent)
        self.key, self.mode = key, mode
        self._title = title
        self._filtering = False
        self._settings_key = settings_prefix + key
        saved = QSettings().value(self._settings_key, default_open, type=bool)

        self.arrow = QToolButton()
        self.arrow.setAutoRaise(True)
        self.arrow.setCursor(Qt.PointingHandCursor)
        self.arrow.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.arrow.setStyleSheet(f'QToolButton {{ border: 0; color: {MUTED}; font-size: 11px;'
                                 ' font-weight: 600; letter-spacing: 1px; padding: 0; }')
        self.arrow.clicked.connect(self.toggle_open)
        self.marker = QLabel('filtered')
        self.marker.setStyleSheet(f'color: {WARN}; background: #fff0dc; border-radius: 8px;'
                                  ' padding: 0 6px; font-size: 11px; font-weight: 600;')
        self.marker.hide()
        self.all_btn = QPushButton('All')
        self.all_btn.setFlat(True)
        self.all_btn.setCursor(Qt.PointingHandCursor)
        self.all_btn.setStyleSheet(f'QPushButton {{ color: {ROMAINE}; border: 0; padding: 0 2px;'
                                   ' font-size: 12px; } QPushButton:hover { text-decoration: underline; }')
        self.all_btn.clicked.connect(lambda: self.toggledAll.emit(self.all_btn.text() == 'All'))
        self.all_btn.hide()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        head.addWidget(self.arrow)
        head.addWidget(self.marker)
        head.addStretch()
        head.addWidget(self.all_btn)

        self.body_widget = QWidget()
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(0, 4, 0, 0)
        self.body.setSpacing(7)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(head)
        layout.addWidget(self.body_widget)
        self._set_open(saved, persist=False)

    def is_open(self):
        return self.body_widget.isVisibleTo(self)

    def toggle_open(self):
        self._set_open(not self.body_widget.isVisibleTo(self))

    def _set_open(self, open_, persist=True):
        self.body_widget.setVisible(open_)
        self.arrow.setText(f'{"▾" if open_ else "▸"}  {self._title.upper()}')
        self.arrow.setToolTip('Collapse' if open_ else 'Expand')
        self.marker.setVisible(self._filtering and not open_)
        if persist:
            QSettings().setValue(self._settings_key, open_)

    def sync(self, boxes, filtering):
        '''Refresh the All/None label and the filtered marker.'''
        many = len(boxes) >= _ALL_TOGGLE_MIN
        self.all_btn.setVisible(many)
        if many:
            all_on = all(cb.isChecked() for cb in boxes.values())
            self.all_btn.setText('None' if all_on else 'All')
            self.all_btn.setToolTip('Uncheck every option' if all_on else 'Check every option')
        self.set_filtering(filtering)

    def set_filtering(self, filtering):
        self._filtering = filtering
        self.marker.setVisible(filtering and not self.is_open())


class FacetPane(QScrollArea):
    changed = Signal()

    SECTIONS = ()          # (key, title, mode, open by default)
    SETTINGS_PREFIX = ''
    WIDTH = 240

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f'QScrollArea {{ border: 0; border-right: 1px solid {BORDER};'
                           ' background: #fffaf2; }')
        host = QWidget()
        host.setObjectName('FacetHost')
        host.setStyleSheet(f'QWidget#FacetHost {{ background: #fffaf2; }}'
                           f' QCheckBox {{ color: {KALE}; spacing: 8px; }}')
        self._layout = QVBoxLayout(host)
        self._layout.setContentsMargins(18, 20, 18, 20)
        self._layout.setSpacing(18)
        self.setWidget(host)

        self._groups = {}
        self._state = {}   # (group, key) → checked
        for key, title, mode, default_open in self.SECTIONS:
            section = FacetSection(key, title, mode, default_open, self.SETTINGS_PREFIX)
            section.toggledAll.connect(lambda on, k=key: self._set_all(k, on))
            self._layout.addWidget(section)
            self._groups[key] = {'section': section, 'boxes': {}, 'mode': mode}
        self._layout.addStretch()

    def section(self, group):
        return self._groups[group]['section']

    # --- building ------------------------------------------------------

    def _default_checked(self, group, key):
        return self._groups[group]['mode'] == 'include'

    def _fill(self, group, items):
        '''items: (key, label, dot color or None, count, count color or
        None[, tooltip]). Checkbox state is kept by key across refills.'''
        g = self._groups[group]
        body = g['section'].body
        while body.count():
            w = body.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        g['boxes'] = {}
        for key, label, dot, count, count_color, *rest in items:
            row = QWidget()
            if rest and rest[0]:
                row.setToolTip(rest[0])
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(6)
            cb = QCheckBox()
            cb.setChecked(self._state.get((group, key), self._default_checked(group, key)))
            cb.toggled.connect(lambda checked, gk=(group, key): self._on_toggled(gk, checked))
            hl.addWidget(cb)
            if dot:
                d = QLabel()
                d.setFixedSize(10, 10)
                d.setStyleSheet(f'background: {dot}; border-radius: 5px;')
                hl.addWidget(d)
            text = QLabel(label)
            text.setStyleSheet(f'color: {KALE};')
            # Clicking the label toggles too, like a <label for>.
            text.mousePressEvent = lambda _e, c=cb: c.toggle()
            hl.addWidget(text, stretch=1)
            n = QLabel(str(count))
            weight = '600' if count_color and count_color != MUTED else '400'
            n.setStyleSheet(f'color: {count_color or MUTED}; font-weight: {weight};')
            hl.addWidget(n)
            body.addWidget(row)
            g['boxes'][key] = cb
        self._sync_section(group)

    # --- changes -------------------------------------------------------

    def _on_toggled(self, group_key, checked):
        self._state[group_key] = checked
        self._sync_section(group_key[0])
        self.changed.emit()

    def _set_all(self, group, on):
        '''All / None: one filter update, not one per checkbox.'''
        for key, cb in self._groups[group]['boxes'].items():
            cb.blockSignals(True)
            cb.setChecked(on)
            cb.blockSignals(False)
            self._state[(group, key)] = on
        self._sync_section(group)
        self.changed.emit()

    def _filtering(self, group):
        '''Changed from the section's defaults (a default that hides
        rows, like Sub-recipes, isn't flagged).'''
        return any(cb.isChecked() != self._default_checked(group, k)
                   for k, cb in self._groups[group]['boxes'].items())

    def _sync_section(self, group):
        g = self._groups[group]
        g['section'].sync(g['boxes'], self._filtering(group))

    # --- reading -------------------------------------------------------

    def checked(self, group):
        return {k for k, cb in self._groups[group]['boxes'].items() if cb.isChecked()}

    def included(self, group):
        '''For an include section: None when everything is checked (no
        filter), else the set of checked keys.'''
        on = self.checked(group)
        return None if len(on) == len(self._groups[group]['boxes']) else on

    def clear(self):
        for group, g in self._groups.items():
            for key, cb in g['boxes'].items():
                on = self._default_checked(group, key)
                cb.blockSignals(True)
                cb.setChecked(on)
                cb.blockSignals(False)
                self._state[(group, key)] = on
            self._sync_section(group)
        self.changed.emit()
