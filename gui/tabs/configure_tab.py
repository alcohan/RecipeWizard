'''Configure place — setup and upkeep, behind a grouped section list.

Daily work gets a place of its own; everything touched rarely lives
here: formats & templates, ingredient categories, suppliers, library
health, data & backups, images and preferences.

Sections that already exist as widgets (Suppliers, Library health)
are hosted inline. Sections whose editors are still modal dialogs
show a short description plus a button that opens the dialog; they
move inline in a later slice.
'''
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QStackedWidget, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from gui.widgets.text_fit import text_width


# Evergreens tokens.
_KALE = '#082c00'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_SELECTED = '#fff1da'
_ALERT_BG = '#ffa94d'
_ALERT_ROLE = Qt.UserRole + 1


class _NavDelegate(QStyledItemDelegate):
    '''Nav rows as usual, plus an orange count pill on the right of a
    row that needs attention (set_section_alert).'''

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        count = index.data(_ALERT_ROLE)
        if not count:
            return
        font = QFont(option.font)
        font.setBold(True)
        font.setPixelSize(11)
        text = str(count)
        w, h = max(18, text_width(font, text) + 12), 18
        r = option.rect
        pill = QRectF(r.right() - 8 - w, r.center().y() - h / 2 + 1, w, h)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_ALERT_BG))
        painter.drawRoundedRect(pill, h / 2, h / 2)
        painter.setFont(font)
        painter.setPen(QColor(_KALE))
        painter.drawText(pill, Qt.AlignCenter, text)
        painter.restore()


class ConfigureTab(QWidget):
    '''Section nav on the left, the chosen section on the right.

    `add_group` starts a labelled group in the nav; `add_section`
    appends a page under the most recent group and returns its key so
    callers can jump to it with `show_section`.'''

    sectionChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._keys = []          # nav row → section key (None for group headers)
        self._items = {}         # section key → QListWidgetItem

        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        self.nav.setFrameShape(QFrame.NoFrame)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setStyleSheet(f'''
            QListWidget {{
                background: #fffaf2;
                border-right: 1px solid {_BORDER};
                padding: 12px 8px;
                outline: 0;
            }}
            QListWidget::item {{
                color: {_KALE};
                padding: 6px 10px;
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: {_SELECTED};
                color: {_KALE};
                font-weight: 600;
            }}
        ''')
        self.nav.setItemDelegate(_NavDelegate(self.nav))
        self.nav.currentRowChanged.connect(self._on_row_changed)

        self.pages = QStackedWidget()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.nav)
        layout.addWidget(self.pages, stretch=1)

    # --- building ------------------------------------------------------

    def add_group(self, title):
        item = QListWidgetItem(title.upper())
        item.setFlags(Qt.NoItemFlags)
        font = item.font()
        font.setPointSizeF(font.pointSizeF() * 0.8)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(Qt.GlobalColor.darkGray)
        self.nav.addItem(item)
        self._keys.append(None)

    def add_section(self, key, title, widget):
        item = QListWidgetItem(title)
        self.nav.addItem(item)
        self._keys.append(key)
        self._items[key] = item
        item.setData(Qt.UserRole, title)
        self.pages.addWidget(widget)
        widget.setProperty('configureKey', key)
        if self.nav.currentRow() < 0:
            self.nav.setCurrentItem(item)
        return key

    def set_section_count(self, key, count):
        '''Trailing count in the nav row ("Library health  8").'''
        item = self._items.get(key)
        if item is None:
            return
        title = item.data(Qt.UserRole)
        item.setText(f'{title}  {count}' if count else title)

    def set_section_alert(self, key, count, tooltip=''):
        '''An orange count pill on the nav row: this section has things
        to fix. Zero clears it.'''
        item = self._items.get(key)
        if item is None:
            return
        item.setText(item.data(Qt.UserRole))
        item.setData(_ALERT_ROLE, count or None)
        item.setToolTip(tooltip if count else '')

    # --- navigation ----------------------------------------------------

    def show_section(self, key):
        item = self._items.get(key)
        if item is not None:
            self.nav.setCurrentItem(item)

    def current_section(self):
        row = self.nav.currentRow()
        return self._keys[row] if 0 <= row < len(self._keys) else None

    def _on_row_changed(self, row):
        key = self._keys[row] if 0 <= row < len(self._keys) else None
        if key is None:
            return
        for i in range(self.pages.count()):
            if self.pages.widget(i).property('configureKey') == key:
                self.pages.setCurrentIndex(i)
                break
        self.sectionChanged.emit(key)


class LauncherPage(QWidget):
    '''Placeholder page for a section whose editor is still a modal
    dialog: a heading, a sentence on what it does, and buttons that
    open the dialogs. `actions` is a list of (label, callable).'''

    def __init__(self, title, description, actions, parent=None):
        super().__init__(parent)
        heading = QLabel(title)
        heading.setStyleSheet(f'font-size: 20px; font-weight: 650; color: {_KALE};')
        body = QLabel(description)
        body.setWordWrap(True)
        body.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')

        button_row = QHBoxLayout()
        for i, (label, handler) in enumerate(actions):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            if i == 0:
                btn.setDefault(True)
            button_row.addWidget(btn)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(heading)
        if description:
            layout.addWidget(body)
        layout.addLayout(button_row)
        layout.addStretch()
