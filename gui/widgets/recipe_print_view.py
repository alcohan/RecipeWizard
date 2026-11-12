'''A recipe's Print view: what its printed page says, with a live
preview, Print and Export PDF.

Settings kept with the recipe (as undoable edits; the editor pushes
them): the main Nutrition Facts title, and which components get a
panel of their own. "Portion tools" is for this preview and these
buttons only.
'''
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

import db
from gui.printing.recipe_page import render_images
from gui.services import print_branding
from gui.widgets.text_fit import literal
from utilities import recipe_print

_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'

_CONTROLS_W = 280
_PAGE_MAX_W = 720
_LETTER_W_IN = 8.5

_BUTTON = f'''
    QPushButton {{ height: 32px; padding: 0 12px; border: 1px solid {_FIELD_BORDER};
        border-radius: 8px; background: #ffffff; color: {_KALE}; }}
    QPushButton:hover {{ background: #f3ece0; }}
'''
_PRIMARY = f'''
    QPushButton {{ height: 32px; padding: 0 16px; border: 0; border-radius: 8px;
        background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}
    QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}
'''


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def _note(text):
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
    return lbl


class RecipePrintView(QWidget):
    titleEdited = Signal(object, object)          # before, after (None: automatic)
    cardToggled = Signal(object, object, object)  # key, before, after (None: default)

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._data = None
        self._card_boxes = []

        card = QFrame()
        card.setObjectName('PrintControls')
        card.setFixedWidth(_CONTROLS_W)
        card.setStyleSheet(f'QFrame#PrintControls {{ background: #ffffff; border: 1px solid {_BORDER};'
                           ' border-radius: 8px; }')
        controls = QVBoxLayout(card)
        controls.setContentsMargins(16, 14, 16, 16)
        controls.setSpacing(8)

        controls.addWidget(_eyebrow('Nutrition title'))
        self.title_edit = QLineEdit()
        self.title_edit.setClearButtonEnabled(True)
        self.title_edit.editingFinished.connect(self._on_title_edited)
        controls.addWidget(self.title_edit)
        self.title_note = _note('')
        controls.addWidget(self.title_note)

        controls.addSpacing(8)
        controls.addWidget(_eyebrow('Nutrition cards'))
        controls.addWidget(_note('Components with their own panel'))
        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(4)
        controls.addLayout(self.cards_box)

        controls.addSpacing(8)
        controls.addWidget(_eyebrow('Show'))
        self.portions_check = QCheckBox('Portion tools')
        self.portions_check.setChecked(False)
        self.portions_check.toggled.connect(lambda _on: self._render_later())
        controls.addWidget(self.portions_check)

        controls.addSpacing(12)
        self.print_btn = QPushButton('Print…')
        self.print_btn.setStyleSheet(_PRIMARY)
        self.print_btn.clicked.connect(self._print)
        self.pdf_btn = QPushButton('Export PDF…')
        self.pdf_btn.setStyleSheet(_BUTTON)
        self.pdf_btn.clicked.connect(self._export_pdf)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.pdf_btn)
        buttons.addStretch()
        controls.addLayout(buttons)

        left = QVBoxLayout()
        left.addWidget(card)
        left.addStretch()

        self.pages_box = QVBoxLayout()
        self.pages_box.setSpacing(16)
        self.page_count = _note('')
        preview = QVBoxLayout()
        preview.setSpacing(8)
        preview.addWidget(self.page_count)
        preview.addLayout(self.pages_box)
        preview.addStretch()
        self._preview_host = QWidget()
        self._preview_host.setLayout(preview)
        self._preview_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        preview.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)
        row.addLayout(left)
        row.addWidget(self._preview_host, stretch=1)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self._render)
        self._last_width = None

    # --- data ----------------------------------------------------------

    def refresh(self):
        '''Re-read the recipe and redraw. Called when shown and after
        every edit or undo.'''
        self._data = db.recipe_print_data(self.recipe_id)
        if self._data is None:
            return
        d = self._data
        if not self.title_edit.hasFocus():
            self.title_edit.setText(d['title_override'] or '')
        automatic = recipe_print.nutrition_title(d['name'], bool(d['cards']))
        self.title_edit.setPlaceholderText(automatic or 'None')
        self.title_note.setText('Blank for automatic')
        self._rebuild_cards()
        self._render_later()

    def _rebuild_cards(self):
        for box in self._card_boxes:
            box.hide()
            box.deleteLater()
        self._card_boxes = []
        options = self._data['card_options']
        if not options:
            box = _note('No components yet')
            self.cards_box.addWidget(box)
            self._card_boxes.append(box)
            return
        for opt in options:
            box = QCheckBox(literal(f"{opt['name']}"))
            box.setToolTip(f"Per {opt['serving']}")
            box.setChecked(opt['shown'])
            box.toggled.connect(lambda on, o=opt: self._on_card_toggled(o, on))
            self.cards_box.addWidget(box)
            self._card_boxes.append(box)

    def _on_title_edited(self):
        if self._data is None:
            return
        before = self._data['title_override']
        after = self.title_edit.text().strip() or None
        if after != before:
            self.titleEdited.emit(before, after)

    def _on_card_toggled(self, opt, on):
        before = opt['shown'] if opt['shown'] != opt['default'] else None
        after = on if on != opt['default'] else None
        if after != before:
            self.cardToggled.emit(opt['key'], before, after)

    # --- preview -------------------------------------------------------

    def _page_data(self):
        if self._data is None:
            return None
        if self.portions_check.isChecked():
            return self._data
        return recipe_print.without_portions(self._data)

    def _render_later(self):
        self._render_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._data is not None and self._preview_width() != self._last_width:
            self._render_later()

    def _preview_width(self):
        return max(240, min(_PAGE_MAX_W, self._preview_host.width() - 4))

    def _render(self):
        data = self._page_data()
        if data is None or not self.isVisible():
            return
        width = self._preview_width()
        self._last_width = width
        ratio = self.devicePixelRatioF()
        images = render_images([data], print_branding.current(), dpi=width * ratio / _LETTER_W_IN)
        while self.pages_box.count():
            item = self.pages_box.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        for img in images:
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(ratio)
            page = QLabel()
            page.setPixmap(pm)
            # Height fixed, width free to shrink: a narrower window
            # re-renders rather than scrolling sideways.
            page.setFixedHeight(round(pm.height() / ratio) + 2)
            page.setMaximumWidth(round(pm.width() / ratio) + 2)
            page.setMinimumWidth(1)
            page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            page.setStyleSheet(f'background: #ffffff; border: 1px solid {_BORDER};')
            self.pages_box.addWidget(page, alignment=Qt.AlignLeft)
        n = len(images)
        self.page_count.setText('1 page' if n == 1 else f'{n} pages')

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # --- output --------------------------------------------------------

    def _print(self):
        from gui.printing.print_dialog import print_recipes
        print_recipes(self, [self.recipe_id], portions=self.portions_check.isChecked())

    def _export_pdf(self):
        from gui.printing.print_dialog import export_pdf
        export_pdf(self, [self.recipe_id], portions=self.portions_check.isChecked())
