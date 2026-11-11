'''Edit ingredient dialog, per the Framework canvas.

Header: thumbnail, name, "Used in N recipes · last price Oct 14".
Left: the facts — name, unit, weight, portion tool; the price section
(unit price, change since the previous price, step chart, history
table, + New price); nutrition per unit. Right: the associations —
category pills, allergens, photo, and the recipes that use it.
Footer: Delete (only when unused), Archive / Restore, Cancel, Save.

Saving is explicit: fields, category, allergens and photo apply on
Save; Cancel (or closing) with changes asks first. Prices are the
exception — each is its own history record and goes in as soon as
it's entered with + New price — and so are Archive / Restore and Delete.

Clicking a recipe under "Used in" closes the dialog (asking about
unsaved changes) and sets `open_recipe_id`, so the caller can open
that recipe in a tab.
'''
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.archive_confirm import confirm_archive_ingredient
from gui.dialogs.ingredient_price_edit import IngredientPriceEditDialog
from gui.images import choose_photo
from gui.models.ingredients_model import format_change, format_unit_price
from gui.widgets.ingredient_fields import UNIT_TIP, info_icon, AllergenChecks, CategoryPills, NutritionGrid, StatementBox
from gui.widgets.ingredient_thumb import IngredientThumb
from gui.widgets.portion_tool_field import attach_tool_picker
from gui.widgets.toolbar_controls import ToolbarCombo
from utilities import portions as portion_units
from gui.widgets.price_chart import PriceStepChart
from gui.widgets.usda_panel import UsdaLookupPanel
from gui.widgets.wedge_view import WedgeView
from utilities import portions


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_RULE = '#f3ece0'
_FIELD_BORDER = '#7d8771'
_BG = '#fffaf2'
_TOMATO = '#b80700'
_UP_FG, _UP_BG = '#8a4a00', '#fff0dc'
_DOWN_FG, _DOWN_BG = '#24502A', '#E6EFE3'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"
_USED_PREVIEW = 3
_PRICE_PREVIEW = 3   # latest prices shown until All prices is clicked

_FIELD = f'''
    QLineEdit {{ height: 32px; padding: 0 10px; border: 1px solid {_FIELD_BORDER};
        border-radius: 4px; background: #ffffff; color: {_KALE}; }}
    QLineEdit:focus {{ border: 2px solid {_ROMAINE}; padding: 0 9px; }}
'''
_SECONDARY = f'''
    QPushButton {{ min-height: 32px; padding: 0 12px; border: 1px solid {_FIELD_BORDER};
        border-radius: 8px; background: #ffffff; color: {_KALE}; }}
    QPushButton:hover {{ background: #f3ece0; }}
'''


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


BASIS_TIP = 'By weight: nutrition and prices scale with Weight. Each: eggs, avocados, lemon wedges, packaging.'


def _float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _unit_ratio(old, new):
    '''new / old when both units are volumes ("3 f.oz" -> "1 cup" is
    8/3) or amounts of the same measure (".5 ea" -> "1 ea" is 2), else
    None.'''
    a, b = portion_units.parse_unit(old), portion_units.parse_unit(new)
    if a is None or b is None:
        return None
    if a.floz and b.floz:
        ratio = b.floz / a.floz
    elif a.measure == b.measure:
        ratio = b.amount / a.amount
    else:
        return None
    return None if abs(ratio - 1) < 1e-9 else ratio


def _labelled(label, widget, width=None, tip=''):
    col = QVBoxLayout()
    col.setSpacing(4)
    eyebrow = _eyebrow(label)
    if tip:
        head = QHBoxLayout()
        head.setSpacing(5)
        head.addWidget(eyebrow)
        head.addWidget(info_icon(tip))
        head.addStretch()
        col.addLayout(head)
    else:
        col.addWidget(eyebrow)
    if width:
        widget.setFixedWidth(width)
    col.addWidget(widget)
    return col


def _section(title):
    frame = QFrame()
    frame.setObjectName('Section')
    frame.setStyleSheet(f'QFrame#Section {{ border: 1px solid {_BORDER}; border-radius: 8px;'
                        ' background: #ffffff; }')
    head = QHBoxLayout()
    head.setSpacing(12)
    label = QLabel(title)
    label.setStyleSheet(f'color: {_KALE}; font-size: 15px; font-weight: 600;')
    head.addWidget(label)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(12)
    layout.addLayout(head)
    return frame, head, layout, label


def _short_date(iso, year=False):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso or '')
    return (d.strftime('%b %d, %Y') if year else d.strftime('%b %d')).replace(' 0', ' ')


def _num_text(value):
    if value is None or value == '':
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return '{:.4f}'.format(n).rstrip('0').rstrip('.')


class IngredientEditDialog(QDialog):
    def __init__(self, ingredient_id, parent=None):
        super().__init__(parent)
        self.ingredient_id = ingredient_id
        self.modified = False      # parent should refresh if True after exec()
        self.status_message = ''
        self.open_recipe_id = None  # set when the user picks a recipe under Used in
        self._show_all_used = False

        row = db.get_ingredients(ingredient_id)
        self._row = row
        self.setWindowTitle(f"{config.APPNAME} | {row['Name']}")
        self.resize(1100, 840)
        self.setStyleSheet(f'QDialog {{ background: #ffffff; }} QLabel {{ color: {_KALE}; }}')

        self._usage = db.get_ingredient_usage(ingredient_id)
        self._tag_id = (db.get_ingredient_tag(ingredient_id) or {}).get('id')
        self._image = row.get('ImageFilename') or ''

        header = self._build_header(row)
        left = self._build_facts(row)
        right = self._build_associations()
        footer = self._build_footer()

        left_scroll = QScrollArea()
        left_scroll.setWidget(left)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.NoFrame)
        right_scroll.setFixedWidth(400)
        right_scroll.setStyleSheet(f'QScrollArea {{ border: 0; border-left: 1px solid {_BORDER};'
                                   f' background: {_BG}; }}')
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(left_scroll, stretch=1)
        body.addWidget(right_scroll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addLayout(body, stretch=1)
        layout.addWidget(footer)

        QShortcut(QKeySequence.Save, self, activated=self._on_save)
        self._refresh_prices()
        self._baseline = self._collect_state()

    # --- building ------------------------------------------------------

    def _build_header(self, row):
        bar = QFrame()
        bar.setObjectName('Header')
        bar.setStyleSheet(f'QFrame#Header {{ background: #ffffff; border-bottom: 1px solid {_BORDER}; }}')
        thumb = IngredientThumb(self.ingredient_id, 48, name=row.get('Name') or '',
                                image_filename=row.get('ImageFilename') or '',
                                tag_color=row.get('TagColor') or '', radius=8, tint=True)
        self.title = QLabel(row.get('Name') or '')
        self.title.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')
        self.subtitle = QLabel('')
        self.subtitle.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 14, 20, 14)
        hl.setSpacing(14)
        hl.addWidget(thumb)
        hl.addLayout(text, stretch=1)
        return bar

    def _build_facts(self, row):
        area = QWidget()
        area.setObjectName('Facts')
        area.setStyleSheet('QWidget#Facts { background: #ffffff; }' + _FIELD)
        layout = QVBoxLayout(area)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(12)

        self.name_edit = QLineEdit(row.get('Name') or '')
        self.name_edit.textChanged.connect(lambda t: self.title.setText(t or ' '))
        self.unit_edit = QLineEdit(row.get('Unit') or '')
        self.weight_edit = QLineEdit(_num_text(row.get('Weight')))
        self.weight_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.weight_edit.setAlignment(Qt.AlignRight)
        self.basis_combo = ToolbarCombo()
        self.basis_combo.addItem('By weight', 'g')
        self.basis_combo.addItem('Each', 'each')
        self.basis_combo.setCurrentIndex(0 if row.get('basis') == 'g' else 1)
        # How nutrition and costing follow the portion; tracks Portioned.
        self.basis_note = QLabel('')
        self.basis_note.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.basis_combo.currentIndexChanged.connect(lambda _i: self._sync_basis_note())
        self._sync_basis_note()
        self.portion_edit = QLineEdit(row.get('Portion') or '')
        attach_tool_picker(self.portion_edit)
        self.unit_edit.textChanged.connect(lambda _t: self._sync_unit_labels())
        fields = QHBoxLayout()
        fields.setSpacing(12)
        fields.addLayout(_labelled('Name', self.name_edit), stretch=1)
        fields.addLayout(_labelled('Unit', self.unit_edit, 90, UNIT_TIP))
        weight_col = _labelled('Weight (g)', self.weight_edit, 90)
        self.weight_label = weight_col.itemAt(0).widget()
        fields.addLayout(weight_col)
        # Weight and Unit ask about a portion change as soon as they're
        # edited; the form previews it, previous values in gray, and Save
        # applies it.
        self._saved_weight = _float(row.get('Weight'))
        self._form_weight = self._saved_weight
        self._form_unit = row.get('Unit') or ''
        self._portion_ratio = None   # scale the portion by this on Save
        self._asking = False
        self.weight_edit.editingFinished.connect(self._on_weight_edited)
        self.unit_edit.editingFinished.connect(self._on_unit_edited)
        fields.addLayout(_labelled('Portioned', self.basis_combo, 110, BASIS_TIP))
        fields.addLayout(_labelled('Portion tool', self.portion_edit, 160))
        # How portion rules read the unit; shown only for a category some
        # format sizes by rule (Greens, Grains…).
        self.portion_hint = QLabel('')
        self.portion_hint.setWordWrap(True)
        self.portion_hint.hide()
        facts_col = QVBoxLayout()
        facts_col.setSpacing(6)
        facts_col.addWidget(self.basis_note)
        facts_col.addLayout(fields)
        facts_col.addWidget(self.portion_hint)
        layout.addLayout(facts_col)

        # --- price ---
        price, head, pl, _t = _section('Price')
        self.price_chip = QLabel('')
        head.addWidget(self.price_chip)
        head.addStretch()
        self._show_all_prices = False
        self.all_prices = QLabel('')
        self.all_prices.setStyleSheet(f'color: {_ROMAINE};')
        self.all_prices.linkActivated.connect(self._toggle_prices)
        head.addWidget(self.all_prices)
        head.addSpacing(8)
        new_price = QPushButton('+ New price')
        new_price.setStyleSheet(_SECONDARY)
        new_price.setAutoDefault(False)
        new_price.clicked.connect(self._on_new_price)
        head.addWidget(new_price)
        self.per_unit_label = _eyebrow('Per unit')
        self.per_unit_value = QLabel('')
        self.per_unit_value.setStyleSheet(f'color: {_KALE}; font-size: 28px; font-weight: 650;')
        self.per_unit_prev = QLabel('')
        self.per_unit_prev.setStyleSheet(f'color: {_MUTED}; font-size: 14px;')
        self.per_unit_prev.hide()
        value_line = QHBoxLayout()
        value_line.setSpacing(8)
        value_line.addWidget(self.per_unit_value)
        value_line.addWidget(self.per_unit_prev, alignment=Qt.AlignBottom)
        value_line.addStretch()
        value_col = QVBoxLayout()
        value_col.setSpacing(2)
        value_col.addWidget(self.per_unit_label)
        value_col.addLayout(value_line)
        self.chart = PriceStepChart(height=64)
        self.chart.setMaximumWidth(380)
        value_row = QHBoxLayout()
        value_row.setSpacing(20)
        value_row.addLayout(value_col)
        value_row.addWidget(self.chart, stretch=1, alignment=Qt.AlignBottom)
        pl.addLayout(value_row)
        self.price_table = QTableWidget(0, 5)
        self.price_table.setHorizontalHeaderLabels(
            ['EFFECTIVE', 'SUPPLIER', 'CASE PRICE', 'CASE YIELDS', 'PER UNIT'])
        self.price_table.verticalHeader().setVisible(False)
        self.price_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.price_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.price_table.setFocusPolicy(Qt.NoFocus)
        self.price_table.setShowGrid(False)
        self.price_table.setFrameShape(QFrame.NoFrame)
        self.price_table.verticalHeader().setDefaultSectionSize(30)
        self.price_table.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; border: 0; color: {_KALE}; }}
            QTableWidget::item {{ border-top: 1px solid {_RULE}; padding: 0 6px; }}
            QHeaderView::section {{ background: #ffffff; color: {_MUTED}; border: 0;
                padding: 4px 6px; font-size: 11px; font-weight: 600; }}
        ''')
        hdr = self.price_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        pl.addWidget(self.price_table)
        self.no_price = QLabel('No price yet')
        self.no_price.setWordWrap(True)
        self.no_price.setStyleSheet(f'color: {_MUTED};')
        pl.addWidget(self.no_price)
        layout.addWidget(price)

        # --- nutrition ---
        nutrition, nhead, nl, self.nutrition_title = _section('Nutrition per unit')
        nhead.addStretch()
        lookup = QPushButton('Look up in USDA…')
        lookup.setFlat(True)
        lookup.setAutoDefault(False)
        lookup.setCursor(Qt.PointingHandCursor)
        lookup.setStyleSheet(f'QPushButton {{ color: {_ROMAINE}; border: 0; padding: 0 4px; }}'
                             ' QPushButton:hover { text-decoration: underline; }')
        lookup.clicked.connect(self._on_usda_lookup)
        nhead.addWidget(lookup)
        self.nutrition = NutritionGrid({key: row.get(key) for key in config.nutrition_fields})
        self.nutrition.changed.connect(self._show_previous)
        nl.addWidget(self.nutrition)
        self.usda_note = QLabel('')
        self.usda_note.setWordWrap(True)
        self.usda_note.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.usda_note.hide()
        nl.addWidget(self.usda_note)
        self.statement = StatementBox(row.get('statement') or '')
        nl.addWidget(self.statement)
        layout.addWidget(nutrition)
        layout.addStretch()
        self._sync_unit_labels()
        return area

    def _build_associations(self):
        area = QWidget()
        area.setObjectName('Assoc')
        area.setStyleSheet(f'QWidget#Assoc {{ background: {_BG}; }} QCheckBox {{ color: {_KALE}; }}')
        layout = QVBoxLayout(area)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        layout.addWidget(_eyebrow('Category'))
        self.category = CategoryPills(self._tag_id)
        self.category.changed.connect(lambda _id: self._sync_portion_hint())
        layout.addWidget(self.category)
        if hasattr(self, 'portion_hint'):
            self._sync_portion_hint()

        layout.addWidget(_eyebrow('Contains allergens'))
        self.allergens = AllergenChecks(self.ingredient_id)
        layout.addWidget(self.allergens)

        # Photo.
        layout.addWidget(_eyebrow('Photo'))
        photo_row = QHBoxLayout()
        photo_row.setSpacing(12)
        self.photo_host = QHBoxLayout()
        self.photo_host.setContentsMargins(0, 0, 0, 0)
        photo_row.addLayout(self.photo_host)
        side = QVBoxLayout()
        side.setSpacing(6)
        self.photo_name = QLabel('')
        self.photo_name.setStyleSheet(f'color: {_MUTED}; font-family: {_MONO}; font-size: 12px;')
        self.photo_name.setWordWrap(True)
        change = QPushButton('Change…')
        change.setStyleSheet(_SECONDARY)
        change.setAutoDefault(False)
        change.clicked.connect(self._on_change_photo)
        self.remove_photo = QPushButton('Remove')
        self.remove_photo.setFlat(True)
        self.remove_photo.setStyleSheet(f'color: {_MUTED}; border: 0; text-align: left;')
        self.remove_photo.clicked.connect(lambda: self._set_photo(''))
        side.addWidget(self.photo_name)
        btns = QHBoxLayout()
        btns.addWidget(change)
        btns.addWidget(self.remove_photo)
        btns.addStretch()
        side.addLayout(btns)
        side.addStretch()
        photo_row.addLayout(side, stretch=1)
        layout.addLayout(photo_row)
        self._set_photo(self._image)

        # Used in.
        n = len(self._usage)
        self.used_title = _eyebrow(f"Used in {n} recipe{'s' if n != 1 else ''}" if n else 'Not used in any recipe')
        layout.addWidget(self.used_title)
        self.used_list = QFrame()
        self.used_list.setObjectName('UsedList')
        self.used_list.setStyleSheet(f'QFrame#UsedList {{ background: #ffffff; border: 1px solid {_BORDER};'
                                     ' border-radius: 8px; }')
        self._used_layout = QVBoxLayout(self.used_list)
        self._used_layout.setContentsMargins(0, 0, 0, 0)
        self._used_layout.setSpacing(0)
        layout.addWidget(self.used_list)
        self.used_list.setVisible(bool(n))
        self._fill_used_in()
        layout.addStretch()
        return area

    def _build_footer(self):
        bar = QFrame()
        bar.setObjectName('Footer')
        bar.setStyleSheet(f'QFrame#Footer {{ background: {_BG}; border-top: 1px solid {_BORDER}; }}')
        self.delete_btn = QPushButton('Delete ingredient…')
        self.delete_btn.setAutoDefault(False)
        self.delete_btn.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 14px; border: 1px solid {_TOMATO};'
            f' border-radius: 8px; background: #ffffff; color: {_TOMATO}; }}'
            f' QPushButton:disabled {{ border-color: #d8ccb4; color: #a7ad9c; }}')
        self.delete_btn.clicked.connect(self._on_delete)
        n = len(self._usage)
        self.delete_btn.setEnabled(not n)
        if n:
            self.delete_btn.setToolTip(f"Used in {n} recipe{'s' if n != 1 else ''}")
        self.archive_btn = QPushButton('')
        self.archive_btn.setAutoDefault(False)
        self.archive_btn.setStyleSheet(_SECONDARY.replace('min-height: 32px', 'min-height: 34px'))
        self.archive_btn.clicked.connect(self.toggle_archived)
        self._archived = self._status() == 'archived'
        self._sync_archive_btn()
        cancel = QPushButton('Cancel')
        cancel.setAutoDefault(False)
        cancel.setStyleSheet(_SECONDARY.replace('min-height: 32px', 'min-height: 34px'))
        cancel.clicked.connect(self.reject)
        save = QPushButton('Save   Ctrl+S')
        save.setAutoDefault(False)
        save.setStyleSheet(
            f'QPushButton {{ min-height: 34px; padding: 0 16px; border: 0; border-radius: 8px;'
            f' background: {_ROMAINE}; color: #ffffff; font-weight: 600; }}'
            f' QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        save.clicked.connect(self._on_save)
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 12, 20, 12)
        hl.setSpacing(8)
        hl.addWidget(self.delete_btn)
        hl.addWidget(self.archive_btn)
        hl.addStretch()
        hl.addWidget(cancel)
        hl.addWidget(save)
        return bar

    # --- prices --------------------------------------------------------

    def _refresh_prices(self):
        prices = db.get_ingredient_prices(self.ingredient_id)
        today = date.today().isoformat()
        current = next((p for p in prices if str(p['effective_date']) <= today), None)
        has = bool(prices)
        self.price_table.setVisible(has)
        self.chart.setVisible(len(prices) > 1)
        self.no_price.setVisible(not has)
        # A pending portion change previews every price at the new size.
        k = self._price_scale()
        self.chart.set_prices([(p['effective_date'], (p['unit_price'] or 0) * k) for p in prices])
        cost = (db.get_ingredients(self.ingredient_id) or {}).get('Cost')
        self.per_unit_value.setText(format_unit_price(cost * k) if cost else '—')
        self.per_unit_prev.setText(f'({format_unit_price(cost)})' if cost and k != 1 else '')
        self.per_unit_prev.setVisible(bool(cost) and k != 1)

        older = [p for p in prices if current and p is not current
                 and str(p['effective_date']) <= today]
        if current and older:
            prev = older[0]
            pct = (current['unit_price'] / prev['unit_price'] - 1.0) if prev['unit_price'] else 0.0
            up, down = pct > 0.0005, pct < -0.0005
            fg, bg = (_UP_FG, _UP_BG) if up else (_DOWN_FG, _DOWN_BG) if down else (_MUTED, '#f3ece0')
            arrow = '▲ ' if up else '▼ ' if down else ''
            self.price_chip.setText(f'{arrow}{format_change(pct)} since {_short_date(prev["effective_date"])}')
            self.price_chip.setStyleSheet(f'color: {fg}; background: {bg}; border-radius: 9px;'
                                          ' padding: 1px 8px; font-size: 12px; font-weight: 600;')
            self.price_chip.show()
        else:
            self.price_chip.hide()

        unit = self.unit_edit.text() or 'unit'
        n_all = len(prices)
        more = n_all > _PRICE_PREVIEW
        self.all_prices.setText(f'<a href="toggle" style="color: {_ROMAINE}; text-decoration: none;">'
                                f"{'Latest only' if self._show_all_prices else f'All {n_all} prices'}</a>"
                                if more else '')
        self.all_prices.setVisible(more)
        if not self._show_all_prices:
            prices = prices[:_PRICE_PREVIEW]
        self.price_table.setRowCount(len(prices))
        for r, p in enumerate(prices):
            is_current = p is current
            cells = [
                _short_date(p['effective_date'], year=True) + (' · current' if is_current else ''),
                p.get('supplier') or '—',
                f'${float(p["case_price"] or 0):.2f}',
                f'{_num_text(round(float(p["units_per_case"] or 0) / k, 2))} {unit}'
                + (f' ({_num_text(round(float(p["units_per_case"] or 0), 2))})' if k != 1 else ''),
                format_unit_price((p['unit_price'] or 0) * k)
                + (f' ({format_unit_price(p["unit_price"])})' if k != 1 else ''),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c >= 2:
                    item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if is_current:
                    item.setBackground(QColor('#fff1da'))
                    if c == 4:
                        f = QFont()
                        f.setWeight(QFont.DemiBold)
                        item.setFont(f)
                if p['effective_date'] and str(p['effective_date']) > today:
                    item.setForeground(Qt.GlobalColor.darkGray)
                    item.setToolTip('Takes effect on this date')
                self.price_table.setItem(r, c, item)
        rows_h = self.price_table.verticalHeader().defaultSectionSize() * len(prices)
        self.price_table.setFixedHeight(self.price_table.horizontalHeader().height() + rows_h + 4)

        bits = [f"Used in {len(self._usage)} recipe{'s' if len(self._usage) != 1 else ''}"
                if self._usage else 'Not used in any recipe']
        if current:
            bits.append(f'last price {_short_date(current["effective_date"])}')
        self.subtitle.setText(' · '.join(bits))

    def _toggle_prices(self, _href):
        self._show_all_prices = not self._show_all_prices
        self._refresh_prices()

    def _on_new_price(self):
        if IngredientPriceEditDialog(self.ingredient_id, parent=self).exec() == QDialog.Accepted:
            self.modified = True
            self._refresh_prices()

    def _sync_unit_labels(self):
        unit = self.unit_edit.text().strip() or 'unit'
        self.per_unit_label.setText(f'PER {unit.upper()}')
        self.nutrition_title.setText(f'Nutrition per {unit}')
        self._sync_portion_hint()

    def _sync_portion_hint(self):
        category = getattr(self, 'category', None)
        tag_id = category.selected() if category is not None else self._tag_id
        formats = db.get_category_portion_formats(tag_id)
        if not formats:
            self.portion_hint.hide()
            return
        ok, _desc = portions.describe_unit(self.unit_edit.text())
        sized_by = ', '.join(formats)
        if ok:
            self.portion_hint.setText(f'Sized by rule in {sized_by}')
            self.portion_hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        else:
            self.portion_hint.setText('Portion rules need a volume unit, like “3 cups”')
            self.portion_hint.setStyleSheet(f'color: {_UP_FG}; font-size: 12px;')
        self.portion_hint.show()

    # --- associations --------------------------------------------------

    def _on_usda_lookup(self):
        '''Look the ingredient up in USDA, scaled to this unit and weight.
        Values land in the form, not the DB — Save keeps them.'''
        dlg = UsdaLookupDialog(self.name_edit.text(), self.unit_edit.text(), self.weight_edit.text(), parent=self)
        if dlg.exec() != QDialog.Accepted or dlg.chosen is None:
            return
        values, grams, note = dlg.chosen
        self.nutrition.set_values(values)
        try:
            current = float(self.weight_edit.text())
        except ValueError:
            current = 0.0
        if abs(current - grams) > 0.01:
            if current > 0:
                note += f' Weight per unit changed from {_num_text(current)} g to match.'
            self.weight_edit.setText(_num_text(round(grams, 2)))
            # USDA's weight for this unit: a correction, not a new portion.
            self._form_weight = _float(self.weight_edit.text())
            self._show_previous()
        self.usda_note.setText(note.strip())
        self.usda_note.show()

    def _set_photo(self, filename):
        self._image = filename or ''
        while self.photo_host.count():
            w = self.photo_host.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.photo_host.addWidget(IngredientThumb(
            self.ingredient_id, 72, name=self.name_edit.text() or '?',
            image_filename=self._image, tag_color=self._row.get('TagColor') or '',
            radius=8, tint=True))
        self.photo_name.setText(self._image or 'No photo')
        self.remove_photo.setVisible(bool(self._image))

    def _on_change_photo(self):
        name = choose_photo(self, config.INGREDIENTS_PATH)
        if name:
            self._set_photo(name)

    def _fill_used_in(self):
        while self._used_layout.count():
            w = self._used_layout.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        shown = self._usage if self._show_all_used else self._usage[:_USED_PREVIEW]
        for i, u in enumerate(shown):
            row = QFrame()
            row.setObjectName('UsedRow')
            row.setStyleSheet('QFrame#UsedRow { border: 0; %s }'
                              % ('' if i == 0 else f'border-top: 1px solid {_RULE};'))
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 6, 10, 6)
            hl.setSpacing(8)
            # Wedges render in the background — a dozen synchronous
            # renders would stall opening the dialog.
            wedge = WedgeView(u['Id'], size=24, defer=True)
            wedge.render_async()
            hl.addWidget(wedge)
            archived = u.get('Status') == 'archived'
            name = QLabel(f'<a href="{u["Id"]}" style="color: {_MUTED if archived else _KALE}">{u["Name"]}</a>'
                          + (f'<span style="color: {_MUTED}"> · archived</span>' if archived else ''))
            # Long recipe names wrap instead of widening the side panel.
            name.setWordWrap(True)
            name.setMinimumWidth(1)
            name.linkActivated.connect(lambda href: self._open_recipe(int(href)))
            hl.addWidget(name, stretch=1)
            # Previews a pending portion change, like the prices.
            unit = self.unit_edit.text().strip() if hasattr(self, 'unit_edit') else u['Unit']
            meta = QLabel(f'{_num_text(u["Quantity"])} {unit or ""}'
                          f' · ${float(u["LineCost"] or 0) * self._price_scale():.2f}')
            meta.setStyleSheet(f'color: {_MUTED};')
            hl.addWidget(meta)
            self._used_layout.addWidget(row)
        extra = len(self._usage) - _USED_PREVIEW
        if extra > 0:
            more = QLabel(f'<a href="more" style="color: {_ROMAINE}">'
                          f'{"Show fewer" if self._show_all_used else f"{extra} more"}</a>')
            more.setStyleSheet(f'padding: 6px 10px; border-top: 1px solid {_RULE};')
            more.linkActivated.connect(self._toggle_used)
            self._used_layout.addWidget(more)

    def _toggle_used(self, _href):
        self._show_all_used = not self._show_all_used
        self._fill_used_in()

    def _open_recipe(self, recipe_id):
        if not self._confirm_leave():
            return
        self.open_recipe_id = recipe_id
        super().reject()

    # --- state ---------------------------------------------------------

    def _collect_state(self):
        return (
            self.name_edit.text().strip(), self.unit_edit.text(), self.weight_edit.text(),
            self.basis_combo.currentData(), self.portion_edit.text(),
            tuple(sorted(self.nutrition.values().items())), self.statement.text(),
            self.category.selected(), self._image,
            tuple(self.allergens.checked_ids()), tuple(self.allergens.facility_ids()),
        )

    def _dirty(self):
        return self._collect_state() != self._baseline

    def _confirm_leave(self):
        '''True if it's fine to close: nothing to save, or the user chose
        Save (and it worked) or Discard.'''
        if not self._dirty():
            return True
        answer = QMessageBox.question(
            self, 'Unsaved changes', f"Save changes to '{self.name_edit.text() or self._row['Name']}'?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self._save()
        return True

    def reject(self):
        if self._confirm_leave():
            super().reject()

    # --- handlers ------------------------------------------------------

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, 'Name needed', 'An ingredient needs a name.')
            self.name_edit.setFocus()
            return False
        if self._on_weight_edited() is False:
            return False   # Cancel on the portion question
        self._on_unit_edited()
        values = self.nutrition.values()
        if self._portion_ratio is not None:
            # Prices and history scale from their per-gram values; the
            # form's nutrition (already scaled) is saved below.
            db.scale_portion(self.ingredient_id, self._portion_ratio)
        # Cost comes from the price history (a trigger keeps it current);
        # re-read it so Save never overwrites a price added just now.
        current_cost = (db.get_ingredients(self.ingredient_id) or {}).get('Cost') or 0
        values.update({
            'Name': name, 'Unit': self.unit_edit.text(), 'Portion': self.portion_edit.text(),
            'Weight': self.weight_edit.text(), 'Cost': str(current_cost),
            'ImageFilename': self._image or None,
        })
        db.update_ingredient(self.ingredient_id, values)
        if self.basis_combo.currentData() != self._row.get('basis'):
            db.set_ingredient_basis(self.ingredient_id, self.basis_combo.currentData())
        self._row = db.get_ingredients(self.ingredient_id) or self._row
        self._saved_weight = self._form_weight = _float(self._row.get('Weight'))
        self._form_unit = self._row.get('Unit') or ''
        self._portion_ratio = None
        self._usage = db.get_ingredient_usage(self.ingredient_id)
        self._show_previous()
        self._refresh_prices()
        self._fill_used_in()
        db.set_ingredient_statement(self.ingredient_id, self.statement.text())
        db.set_ingredient_tag(self.ingredient_id, self.category.selected())
        db.set_ingredient_allergens(self.ingredient_id, self.allergens.checked_ids(),
                                    self.allergens.facility_ids())
        self.modified = True
        self.status_message = f"Saved '{name}'"
        self._baseline = self._collect_state()
        return True

    def _sync_basis_note(self):
        if self.basis_combo.currentData() == 'g':
            self.basis_note.setText('Calculating portion by weight. Change the gram weight to update nutrition & costing.')
        else:
            self.basis_note.setText('Calculating portion per each. Change the unit amount to update nutrition & costing.')

    def _can_scale(self):
        # Not while Portioned is being switched: Save does that first.
        return self._row.get('basis') == self.basis_combo.currentData()

    def _price_scale(self):
        return self._portion_ratio or 1.0

    def _on_weight_edited(self):
        '''Weight was edited: for an ingredient portioned by weight, ask
        whether the portion changed (scale nutrition and prices) or a typo
        was fixed (keep them). False if the user cancelled.'''
        if self._asking:
            return
        old, new = self._form_weight, _float(self.weight_edit.text())
        if abs(new - old) < 0.005:
            return
        if not self._can_scale() or old <= 0 or new <= 0:
            self._form_weight = new
            self._show_previous()
            return
        n = len(self._usage)
        where = f" in {n} recipe{'s' if n != 1 else ''}" if n else ''
        box = QMessageBox(QMessageBox.Question, 'Portion size',
                          f'Weight changed from {_num_text(old)} g to {_num_text(new)} g.', parent=self)
        box.setInformativeText(
            f'Portion changed: nutrition and prices, history included, scale {new / old:.2f}×{where}.\n'
            'Fixing a typo: they stay as entered.')
        portion = box.addButton('Portion changed', QMessageBox.AcceptRole)
        box.addButton('Fixing a typo', QMessageBox.RejectRole)
        cancel = box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(portion)
        self._asking = True
        try:
            box.exec()
        finally:
            self._asking = False
        if box.clickedButton() is cancel:
            self.weight_edit.setText(_num_text(old))
            return False
        if box.clickedButton() is portion:
            self._scale_portion(new / old, new)
        else:
            self._form_weight = new
            self._show_previous()

    def _on_unit_edited(self):
        '''A new amount in Unit (3 f.oz -> 4 f.oz, .5 ea -> 1 ea) offers
        to scale the portion to match: nutrition, prices and, if the
        weight was left alone, the weight.'''
        if self._asking:
            return
        old_unit, new_unit = self._form_unit, self.unit_edit.text().strip()
        if new_unit == old_unit.strip():
            return
        self._form_unit = new_unit
        ratio = _unit_ratio(old_unit, new_unit)
        if ratio is None or not self._can_scale():
            return
        old = self._form_weight
        weight_kept = old > 0 and abs(_float(self.weight_edit.text()) - old) < 0.005
        by_weight = self._row.get('basis') == 'g'
        if by_weight and not weight_kept:
            return   # the weight already says how big the portion is
        new = round(old * ratio, 1) if weight_kept else None
        question = (f'Scale the weight to {_num_text(new)} g?' if by_weight
                    else f'Scale the portion {ratio:.2f}×?')
        box = QMessageBox(QMessageBox.Question, 'Portion size',
                          f'Unit changed from {old_unit} to {new_unit}. {question}', parent=self)
        what = 'Nutrition, weight and prices' if new is not None else 'Nutrition and prices'
        box.setInformativeText(f'{what}, history included, scale {ratio:.2f}×.')
        scale = box.addButton('Scale portion', QMessageBox.AcceptRole)
        box.addButton('Keep weight' if by_weight else 'Keep numbers', QMessageBox.RejectRole)
        box.setDefaultButton(scale)
        self._asking = True
        try:
            box.exec()
        finally:
            self._asking = False
        if box.clickedButton() is scale:
            if new is not None:
                self.weight_edit.setText(_num_text(new))
            self._scale_portion(ratio, new)

    def _scale_portion(self, ratio, new_weight=None):
        '''Preview a portion change in the form; Save applies it.'''
        self.nutrition.scale(ratio)
        if new_weight is not None:
            self._form_weight = new_weight
        # Scales compound: a later typo fix keeps what this change made.
        self._portion_ratio = self._price_scale() * ratio
        self._show_previous()
        self._refresh_prices()
        self._fill_used_in()

    def _show_previous(self):
        '''Saved values in gray beside anything changed since Save.'''
        changed = abs(_float(self.weight_edit.text()) - self._saved_weight) >= 0.005
        self.weight_label.setText(f'WEIGHT (G)  ({_num_text(self._saved_weight)})' if changed else 'WEIGHT (G)')
        saved = {key: self._row.get(key) for key in config.nutrition_fields}
        self.nutrition.set_previous(saved if self._portion_ratio is not None else None)

    def _on_save(self):
        if self._save():
            self.accept()

    # --- archive -------------------------------------------------------

    def _status(self):
        row = db.query('SELECT status FROM Ingredients WHERE Id = ?;', (self.ingredient_id,), one=True)
        return (row or {}).get('status') or 'active'

    def _sync_archive_btn(self):
        self.archive_btn.setText('Restore' if self._archived else 'Archive')
        self.archive_btn.setToolTip('Back in the library and pickers' if self._archived
                                    else 'Hide from the library and pickers; recipes keep it')

    def toggle_archived(self):
        '''Archive (asking first when active recipes use it) or restore,
        right away, like a price. The dialog stays open.'''
        name = self.name_edit.text() or self._row['Name']
        archive = not self._archived
        if archive and not confirm_archive_ingredient(self, self.ingredient_id, name):
            return False
        db.set_ingredient_status(self.ingredient_id, 'archived' if archive else 'active')
        self._archived = archive
        self.modified = True
        self.status_message = f"{'Archived' if archive else 'Restored'} '{name}'"
        self._sync_archive_btn()
        return True

    def _on_delete(self):
        name = self.name_edit.text() or self._row['Name']
        if QMessageBox.question(
            self, 'Delete', f'Delete {name}? This can\'t be undone.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_ingredient(self.ingredient_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Ingredient In Use', str(exc))
            return
        self.modified = True
        self.status_message = f"Deleted '{name}'"
        self._baseline = self._collect_state()   # nothing left to save
        self.accept()


class UsdaLookupDialog(QDialog):
    '''The USDA lookup panel on its own, for checking or filling an
    existing ingredient. `chosen` is (values per unit, grams, note)
    after "Use these values", else None.'''

    def __init__(self, name, unit, weight, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | USDA lookup — {name}')
        self.resize(460, 760)
        self.chosen = None
        self.panel = UsdaLookupPanel()
        self.panel.set_target(unit, weight)
        self.panel.set_query(name)
        self.panel.valuesChosen.connect(self._on_chosen)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel)
        if name.strip():
            self.panel.search()

    def _on_chosen(self, values, grams, note):
        self.chosen = (values, grams, note)
        self.accept()
