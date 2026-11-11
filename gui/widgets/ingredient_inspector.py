'''Right-hand inspector for the Ingredients place: a quick look at the
selected ingredient without opening it.

Photo (from the thumbnail cache), name, category · unit · tool, the
cost card (unit price, change since the previous price, price step
chart, case breakdown), which recipes use it and what the latest price
change did to each, allergens, and Edit / New price buttons, with
Archive / Restore under them.

Only the selected row's price history and usage are queried, when the
selection changes.
'''
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import db
from gui.models.ingredients_model import format_change, format_unit_price
from gui.thumbs import load_thumbnail
from gui.widgets.ingredient_table import tint
from gui.widgets.price_chart import PriceStepChart


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_UP_FG, _UP_BG = '#8a4a00', '#fff0dc'
_DOWN_FG, _DOWN_BG = '#24502A', '#E6EFE3'
_PHOTO_W, _PHOTO_H = 260, 120
_USAGE_PREVIEW = 3


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def _short_date(iso):
    try:
        return date.fromisoformat(str(iso)[:10]).strftime('%b %d').replace(' 0', ' ')
    except (TypeError, ValueError):
        return str(iso or '')


class IngredientInspector(QScrollArea):
    editRequested = Signal(int)
    newPriceRequested = Signal(int)
    recipeRequested = Signal(int)
    archiveRequested = Signal(int, bool)   # ingredient id, True = archive / False = restore

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f'QScrollArea {{ border: 0; border-left: 1px solid {_BORDER};'
                           ' background: #ffffff; }')
        self._id = None
        self._show_all_usage = False

        host = QWidget()
        host.setObjectName('InspectorHost')
        host.setStyleSheet(f'QWidget#InspectorHost {{ background: #ffffff; }}'
                           f' QLabel {{ color: {_KALE}; }}')
        self.setWidget(host)

        self.photo = QLabel()
        self.photo.setFixedSize(_PHOTO_W, _PHOTO_H)
        self.photo.setAlignment(Qt.AlignCenter)

        self.name = QLabel('')
        name_font = QFont()
        name_font.setFamilies(['Gooper Semicondensed', 'Fraunces', 'Georgia', 'serif'])
        name_font.setPixelSize(24)
        name_font.setBold(True)
        self.name.setFont(name_font)
        self.name.setWordWrap(True)
        self.meta = QLabel('')
        self.meta.setTextFormat(Qt.RichText)
        self.meta.setStyleSheet(f'color: {_MUTED};')

        # Cost card.
        card = QFrame()
        card.setObjectName('CostCard')
        card.setStyleSheet(f'QFrame#CostCard {{ border: 1px solid {_BORDER}; border-radius: 8px; }}')
        self.cost_title = _eyebrow('Cost')
        self.cost_chip = QLabel('')
        head = QHBoxLayout()
        head.addWidget(self.cost_title)
        head.addStretch()
        head.addWidget(self.cost_chip)
        self.cost_value = QLabel('')
        self.cost_value.setStyleSheet(f'color: {_KALE}; font-size: 28px; font-weight: 650;')
        self.chart = PriceStepChart(height=40)
        self.cost_detail = QLabel('')
        self.cost_detail.setWordWrap(True)
        self.cost_detail.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(6)
        cl.addLayout(head)
        cl.addWidget(self.cost_value)
        cl.addWidget(self.chart)
        cl.addWidget(self.cost_detail)

        self.usage_title = _eyebrow('Used in')
        # Headings and the meta line wrap rather than widen the panel
        # ("USED IN 7 RECIPES · 5 ARCHIVED · IMPACT OF THE CHANGE").
        for lbl in (self.name, self.meta, self.cost_title, self.usage_title):
            lbl.setWordWrap(True)
            lbl.setMinimumWidth(1)
        self._usage_rows = QVBoxLayout()
        self._usage_rows.setSpacing(6)
        self.usage_more = QLabel('')
        self.usage_more.setTextFormat(Qt.RichText)
        self.usage_more.setStyleSheet('font-size: 12px;')
        self.usage_more.linkActivated.connect(self._on_more)

        self.allergens = QLabel('')
        self.allergens.setWordWrap(True)

        self.edit_btn = QPushButton('Edit   Enter')
        self.edit_btn.setStyleSheet(
            f'QPushButton {{ height: 36px; border: 0; border-radius: 8px; background: {_ROMAINE};'
            f' color: #ffffff; font-weight: 600; }} QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        self.edit_btn.clicked.connect(lambda: self._id is not None and self.editRequested.emit(self._id))
        self.price_btn = QPushButton('New price…')
        self.price_btn.setStyleSheet(
            f'QPushButton {{ height: 36px; border: 1px solid #7d8771; border-radius: 8px;'
            f' background: #ffffff; color: {_KALE}; }} QPushButton:hover {{ background: #f3ece0; }}')
        self.price_btn.clicked.connect(lambda: self._id is not None and self.newPriceRequested.emit(self._id))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.edit_btn)
        buttons.addWidget(self.price_btn)
        self._archived = False
        self.archived_note = QLabel('Archived')
        self.archived_note.setStyleSheet(f'color: {_MUTED}; background: #f3ece0; border-radius: 6px;'
                                         ' padding: 4px 8px; font-size: 12px;')
        self.archive_btn = QPushButton('')
        self.archive_btn.setCursor(Qt.PointingHandCursor)
        self.archive_btn.setStyleSheet(
            f'QPushButton {{ border: 0; background: transparent; color: {_ROMAINE}; padding: 2px 0; }}'
            ' QPushButton:hover { text-decoration: underline; }')
        self.archive_btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.archive_btn.clicked.connect(
            lambda: self._id is not None and self.archiveRequested.emit(self._id, not self._archived))

        self.empty = QLabel('Select an ingredient')
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f'color: {_MUTED};')

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(16)
        bl.addWidget(self.photo)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(self.name)
        name_col.addWidget(self.meta)
        name_col.addWidget(self.archived_note, alignment=Qt.AlignLeft)
        bl.addLayout(name_col)
        bl.addWidget(card)
        usage_col = QVBoxLayout()
        usage_col.setSpacing(6)
        usage_col.addWidget(self.usage_title)
        usage_col.addLayout(self._usage_rows)
        usage_col.addWidget(self.usage_more)
        bl.addLayout(usage_col)
        allergen_col = QVBoxLayout()
        allergen_col.setSpacing(2)
        allergen_col.addWidget(_eyebrow('Allergens'))
        allergen_col.addWidget(self.allergens)
        bl.addLayout(allergen_col)
        bl.addStretch()
        bl.addLayout(buttons)
        bl.addWidget(self.archive_btn)

        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self.empty)
        layout.addWidget(self._body, stretch=1)
        self.show_ingredient(None)

    # --- content -------------------------------------------------------

    def current_id(self):
        return self._id

    def show_ingredient(self, row):
        '''`row` is an IngredientsModel row dict, or None to clear.'''
        if row is None:
            self._id = None
            self._body.hide()
            self.empty.show()
            return
        if row['Id'] != self._id:
            self._show_all_usage = False
        self._id = row['Id']
        self._row = row
        self.empty.hide()
        self._body.show()

        self._set_photo_placeholder(row)
        # A slow photo for a previous selection mustn't land on this one.
        load_thumbnail(row.get('ImageFilename'), _PHOTO_W,
                       lambda img, i=row['Id']: self._id == i and self._apply_photo(img))

        self.name.setText(row.get('Name') or '')
        dot = f'<span style="color: {row.get("TagColor") or "#a7ad9c"}">●</span>'
        bits = [row.get('TagName') or 'Uncategorized', row.get('Unit'), row.get('Portion')]
        self.meta.setText(f'{dot} ' + ' · '.join(b for b in bits if b))
        self._archived = bool(row.get('Archived'))
        self.archived_note.setVisible(self._archived)
        self.archive_btn.setText('Restore' if self._archived else 'Archive')

        unit = row.get('Unit') or 'unit'
        self.cost_title.setText(f'COST PER {unit.upper()}')
        cost = row.get('Cost')
        self.cost_value.setText(format_unit_price(cost) if cost else '—')
        prev, cur = row.get('PrevPrice'), row.get('PriceUnit')
        if prev and cur:
            pct = cur / prev - 1.0
            fg, bg = (_UP_FG, _UP_BG) if pct > 0.0005 else (_DOWN_FG, _DOWN_BG) if pct < -0.0005 else (_MUTED, '#f3ece0')
            arrow = '▲ ' if pct > 0.0005 else '▼ ' if pct < -0.0005 else ''
            self.cost_chip.setText(f'{arrow}{format_change(pct)} since {_short_date(row.get("PrevDate"))}')
            self.cost_chip.setStyleSheet(f'color: {fg}; background: {bg}; border-radius: 9px;'
                                         ' padding: 1px 8px; font-size: 12px; font-weight: 600;')
            self.cost_chip.show()
        else:
            self.cost_chip.hide()
        prices = db.get_ingredient_prices(row['Id'])
        self.chart.set_prices([(p['effective_date'], p['unit_price']) for p in prices])
        self.chart.setVisible(len(prices) > 1)
        if row.get('PriceCount'):
            parts = []
            if row.get('CasePrice') is not None and row.get('UnitsPerCase'):
                parts.append(f'${float(row["CasePrice"]):.2f} case ÷ {_fmt(row["UnitsPerCase"])} {unit}')
            parts.append(row.get('SupplierName') or 'No supplier')
            parts.append(_short_date(row.get('PriceDate')))
            self.cost_detail.setText(' · '.join(parts))
        else:
            self.cost_detail.setText('No price yet')

        self._fill_usage(row, prev, cur)
        text = row.get('Allergens') or 'None'
        if row.get('FacilityAllergens'):
            text += f"\nFacility: {row['FacilityAllergens']}"
        self.allergens.setText(text)
        self.allergens.setStyleSheet(f'color: {_KALE if row.get("Allergens") else _MUTED};')

    def _fill_usage(self, row, prev, cur):
        while self._usage_rows.count():
            item = self._usage_rows.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        usage = db.get_ingredient_usage(row['Id'])   # archived recipes last
        n = len(usage)
        n_archived = sum(1 for u in usage if u.get('Status') == 'archived')
        n_live = n - n_archived
        changed = bool(prev and cur and abs(cur - prev) > 1e-9)
        archived_bit = f' · {n_archived} ARCHIVED' if n_archived else ''
        if not n:
            self.usage_title.setText('NOT USED IN ANY RECIPE')
        elif changed:
            self.usage_title.setText(f"USED IN {n_live} RECIPE{'S' if n_live != 1 else ''}{archived_bit}"
                                     ' · CHANGE')
        else:
            self.usage_title.setText(f"USED IN {n_live} RECIPE{'S' if n_live != 1 else ''}{archived_bit}")
        shown = usage if self._show_all_usage else usage[:_USAGE_PREVIEW]
        for u in shown:
            archived = u.get('Status') == 'archived'
            color = _MUTED if archived else _KALE
            if changed:
                delta = float(u['Quantity'] or 0) * (cur - prev)
                value = f'{"+" if delta >= 0 else "−"}${abs(delta):.2f}'
            else:
                value = f'${float(u["LineCost"] or 0):.2f}'
            line = QLabel(f'<a href="{u["Id"]}" style="color: {color}; text-decoration: none">'
                          f'{u["Name"]}</a>'
                          + (f' <span style="color: {_MUTED}">· archived</span>' if archived else ''))
            line.setTextFormat(Qt.RichText)
            line.setWordWrap(True)   # long recipe names wrap instead of widening the panel
            line.setToolTip('Open in a tab')
            line.linkActivated.connect(lambda href: self.recipeRequested.emit(int(href)))
            amount = QLabel(f'<span style="color: {_MUTED}">{value}</span>' if archived else f'<b>{value}</b>')
            amount.setAlignment(Qt.AlignRight)
            wrap = QWidget()
            hl = QHBoxLayout(wrap)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.addWidget(line, stretch=1)
            hl.addWidget(amount)
            self._usage_rows.addWidget(wrap)
        if n > _USAGE_PREVIEW:
            label = 'Show fewer' if self._show_all_usage else f'Show all {n}'
            self.usage_more.setText(f'<a href="more" style="color: {_ROMAINE}">{label}</a>')
            self.usage_more.show()
        else:
            self.usage_more.hide()

    def _on_more(self, _href):
        self._show_all_usage = not self._show_all_usage
        if self._id is not None:
            self.show_ingredient(self._row)

    def _set_photo_placeholder(self, row):
        self.photo.setPixmap(QPixmap())
        self.photo.setText('No photo' if row.get('Flags', {}).get('no_photo') else '')
        self.photo.setStyleSheet(f'background: {tint(row.get("TagColor")).name()};'
                                 f' border-radius: 8px; color: {_MUTED}; font-size: 12px;')

    def _apply_photo(self, image):
        # Thumbnails are square; crop the middle band for the banner.
        y = max(0, (image.height() - _PHOTO_H) // 2)
        self.photo.setText('')
        self.photo.setPixmap(QPixmap.fromImage(image.copy(0, y, _PHOTO_W, _PHOTO_H)))


def _fmt(value):
    try:
        return '{:.2f}'.format(float(value)).rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(value or '')
