'''Configure › Print & branding: the header logo, accent color, header
label and footer line on printed recipe pages, with a live preview.
Kept in the library via gui.services.print_branding.
'''
import os

from PySide6.QtCore import QEvent, QRectF, QStandardPaths, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QScrollArea, QVBoxLayout,
    QWidget,
)

import db
from gui.printing.recipe_page import logo_drawer, render_images
from gui.services import print_branding as brand
from gui.widgets import config_kit as kit


class PrintPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._preview_id = None

        # logo
        logo_card, logo_l = kit.card()
        logo_l.addWidget(kit.eyebrow('Logo'))
        self.logo_label = QLabel()
        self.logo_label.setMinimumHeight(44)
        self.logo_label.setStyleSheet(f'color: {kit.MUTED};')
        logo_l.addWidget(self.logo_label)
        choose = kit.button('Choose image…')
        choose.clicked.connect(self._choose_logo)
        self.remove_logo_btn = kit.button('Remove logo')
        self.remove_logo_btn.clicked.connect(lambda: (brand.clear_logo(), self._changed()))
        row = QHBoxLayout()
        row.setSpacing(8)
        for b in (choose, self.remove_logo_btn):
            row.addWidget(b)
        row.addStretch()
        logo_l.addLayout(row)
        logo_l.addWidget(kit.note('SVG or PNG'))

        # text + color
        text_card, text_l = kit.card()
        text_l.addWidget(kit.eyebrow('Accent color'))
        self.accent_btn = kit.button('')
        self.accent_btn.clicked.connect(self._choose_accent)
        text_l.addWidget(self.accent_btn, alignment=Qt.AlignLeft)
        text_l.addWidget(kit.eyebrow('Header label'))
        self.header_edit = kit.field(320)
        self.header_edit.editingFinished.connect(
            lambda: (brand.set_header_label(self.header_edit.text().strip()), self._changed()))
        text_l.addWidget(self.header_edit)
        text_l.addWidget(kit.eyebrow('Footer text'))
        self.footer_edit = kit.field(320)
        self.footer_edit.editingFinished.connect(
            lambda: (brand.set_footer_text(self.footer_edit.text().strip()), self._changed()))
        text_l.addWidget(self.footer_edit)
        text_l.addWidget(kit.eyebrow('Disclaimer'))
        self.disclaimer_edit = QPlainTextEdit()
        self.disclaimer_edit.setFixedHeight(64)
        self.disclaimer_edit.setMaximumWidth(560)
        self.disclaimer_edit.setStyleSheet(
            f'QPlainTextEdit {{ border: 1px solid {kit.FIELD_BORDER}; border-radius: 4px; background: #ffffff;'
            f' color: {kit.KALE}; padding: 4px 6px; }}')
        self.disclaimer_edit.installEventFilter(self)
        text_l.addWidget(self.disclaimer_edit)
        reset = kit.button('Use the standard wording')
        reset.clicked.connect(lambda: (brand.set_disclaimer(None), self._changed()))
        text_l.addWidget(reset, alignment=Qt.AlignLeft)
        text_l.addWidget(kit.note('Leave blank for none'))

        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(kit.heading('Print & branding'))
        left.addWidget(logo_card)
        left.addWidget(text_card)
        left.addStretch()

        # preview
        self.preview = QLabel('')
        self.preview.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.preview.setStyleSheet(f'background: #ffffff; border: 1px solid {kit.BORDER}; border-radius: 8px;')
        right = QVBoxLayout()
        right.addWidget(kit.eyebrow('Preview'))
        right.addWidget(self.preview)
        right.addStretch()

        body = QWidget()
        cols = QHBoxLayout(body)
        cols.setContentsMargins(28, 20, 28, 28)
        cols.setSpacing(24)
        cols.addLayout(left, stretch=1)
        cols.addLayout(right)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)
        self._preview_timer.timeout.connect(self._render_preview)
        self._sync()

    def set_preview_recipe(self, recipe_id):
        '''Preview with this recipe (e.g. the Library's selection).'''
        if recipe_id and recipe_id != self._preview_id:
            self._preview_id = recipe_id
            self._preview_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync()   # a restore may have brought other branding

    def _changed(self):
        self._sync()

    def _sync(self):
        current = brand.current()
        for edit, key in ((self.header_edit, 'header'), (self.footer_edit, 'footer')):
            if not edit.hasFocus():
                edit.setText(current[key])
        if not self.disclaimer_edit.hasFocus():
            self.disclaimer_edit.setPlainText(current['disclaimer'])
        self.remove_logo_btn.setEnabled(current['logo'] is not None)
        draw = logo_drawer(current['logo'])
        if draw:
            pm = QPixmap(320, 40)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            draw(p, QRectF(0, 4, 320, 32))
            p.end()
            self.logo_label.setPixmap(pm)
        else:
            self.logo_label.setPixmap(QPixmap())
            self.logo_label.setText('No logo yet. Pages print without one.')
        color = current['accent']
        light = QColor(color).lightness() > 150
        self.accent_btn.setText(f'  {color.upper()}  ')
        self.accent_btn.setStyleSheet(
            f'QPushButton {{ min-height: 30px; padding: 0 14px; border: 1px solid {kit.FIELD_BORDER};'
            f' border-radius: 8px; background: {color}; color: {kit.KALE if light else "#ffffff"};'
            ' font-weight: 600; }')
        self._preview_timer.start()

    def eventFilter(self, obj, event):
        # The disclaimer box saves when focus leaves it, like the fields.
        if obj is self.disclaimer_edit and event.type() == QEvent.FocusOut:
            text = ' '.join(self.disclaimer_edit.toPlainText().split())
            if text != brand.current()['disclaimer']:
                brand.set_disclaimer(text)
                self._changed()
        return super().eventFilter(obj, event)

    def _choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose logo',
            QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or os.path.expanduser('~'),
            'Images (' + ' '.join('*' + e for e in brand.LOGO_EXTENSIONS) + ')')
        if path:
            try:
                brand.set_logo_file(path)
            except (OSError, ValueError) as exc:
                QMessageBox.information(self, 'Logo', str(exc))
                return
            self._changed()

    def _choose_accent(self):
        color = QColorDialog.getColor(QColor(brand.current()['accent']), self, 'Accent color')
        if color.isValid():
            brand.set_accent(color.name())
            self._changed()

    def _render_preview(self):
        if not self.isVisible():
            return
        rid = self._preview_id
        if rid is None:
            rows = db.query("SELECT Id FROM Recipes WHERE COALESCE(status, '') <> 'archived'"
                            ' ORDER BY updated_at DESC LIMIT 1;')['data']
            rid = rows[0]['Id'] if rows else None
        data = db.recipe_print_data(rid) if rid else None
        if data is None:
            self.preview.setText('Add a recipe to see a preview.')
            return
        images = render_images([data], brand.current(), dpi=72)
        pm = QPixmap.fromImage(images[0]).scaledToWidth(420, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.preview.setFixedSize(pm.width() + 2, pm.height() + 2)
