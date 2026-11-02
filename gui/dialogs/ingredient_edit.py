'''Edit ingredient dialog, per the Framework canvas.

Header: thumbnail, name, "Used in N recipes · last price Oct 14".
Left: the facts — name, unit, weight, portion tool; the price section
(unit price, change since the previous price, step chart, history
table, + New price); nutrition per unit. Right: the associations —
category pills, allergens, photo, and the recipes that use it.
Footer: Delete (only when unused), Cancel, Save.

Saving is explicit: fields, category, allergens and photo apply on
Save; Cancel (or closing) with changes asks first. Prices are the
exception — each is its own history record and goes in as soon as
it's entered with + New price.

Clicking a recipe under "Used in" closes the dialog (asking about
unsaved changes) and sets `open_recipe_id`, so the caller can open
that recipe in a tab.
'''
import os
import shutil
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QDoubleValidator, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.ingredient_price_edit import IngredientPriceEditDialog
from gui.images import IMAGE_EXTENSIONS
from gui.models.ingredients_model import format_change, format_unit_price
from gui.widgets.ingredient_fields import AllergenChecks, CategoryPills, NutritionGrid
from gui.widgets.ingredient_thumb import IngredientThumb
from gui.widgets.price_chart import PriceStepChart
from gui.widgets.usda_panel import UsdaLookupPanel
from gui.widgets.wedge_view import WedgeView


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


def _labelled(label, widget, width=None):
    col = QVBoxLayout()
    col.setSpacing(4)
    col.addWidget(_eyebrow(label))
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        self.name_edit = QLineEdit(row.get('Name') or '')
        self.name_edit.textChanged.connect(lambda t: self.title.setText(t or ' '))
        self.unit_edit = QLineEdit(row.get('Unit') or '')
        self.weight_edit = QLineEdit(_num_text(row.get('Weight')))
        self.weight_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.weight_edit.setAlignment(Qt.AlignRight)
        self.portion_edit = QLineEdit(row.get('Portion') or '')
        self.unit_edit.textChanged.connect(lambda _t: self._sync_unit_labels())
        fields = QHBoxLayout()
        fields.setSpacing(12)
        fields.addLayout(_labelled('Name', self.name_edit), stretch=1)
        fields.addLayout(_labelled('Unit', self.unit_edit, 90))
        fields.addLayout(_labelled('Weight (g)', self.weight_edit, 90))
        fields.addLayout(_labelled('Portion tool', self.portion_edit, 140))
        layout.addLayout(fields)

        # --- price ---
        price, head, pl, _t = _section('Price')
        self.price_chip = QLabel('')
        head.addWidget(self.price_chip)
        head.addStretch()
        new_price = QPushButton('+ New price')
        new_price.setStyleSheet(_SECONDARY)
        new_price.setAutoDefault(False)
        new_price.clicked.connect(self._on_new_price)
        head.addWidget(new_price)
        self.per_unit_label = _eyebrow('Per unit')
        self.per_unit_value = QLabel('')
        self.per_unit_value.setStyleSheet(f'color: {_KALE}; font-size: 28px; font-weight: 650;')
        value_col = QVBoxLayout()
        value_col.setSpacing(2)
        value_col.addWidget(self.per_unit_label)
        value_col.addWidget(self.per_unit_value)
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
        self.no_price = QLabel('No price yet. It shows up in Library health under "No price" until you add one.')
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
        lookup.setToolTip('Find this ingredient in USDA FoodData Central and fill in its nutrition, '
                          'scaled to this unit')
        lookup.clicked.connect(self._on_usda_lookup)
        nhead.addWidget(lookup)
        self.nutrition = NutritionGrid({key: row.get(key) for key in config.nutrition_fields})
        nl.addWidget(self.nutrition)
        self.usda_note = QLabel('')
        self.usda_note.setWordWrap(True)
        self.usda_note.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.usda_note.hide()
        nl.addWidget(self.usda_note)
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
        layout.addWidget(self.category)

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
        hint = QLabel(f"Used in {n} recipe{'s' if n != 1 else ''} — remove it from "
                      f"{'them' if n != 1 else 'it'} to delete" if n else '')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.delete_btn.setEnabled(not n)
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
        hl.addWidget(hint)
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
        self.chart.set_prices([(p['effective_date'], p['unit_price']) for p in prices])
        cost = (db.get_ingredients(self.ingredient_id) or {}).get('Cost')
        self.per_unit_value.setText(format_unit_price(cost) if cost else '—')

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
        self.price_table.setRowCount(len(prices))
        for r, p in enumerate(prices):
            is_current = p is current
            cells = [
                _short_date(p['effective_date'], year=True) + (' · current' if is_current else ''),
                p.get('supplier') or '—',
                f'${float(p["case_price"] or 0):.2f}',
                f'{_num_text(p["units_per_case"])} {unit}',
                format_unit_price(p['unit_price']),
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
        rows_h = self.price_table.verticalHeader().defaultSectionSize() * min(len(prices), 6)
        self.price_table.setFixedHeight(self.price_table.horizontalHeader().height() + rows_h + 4)

        bits = [f"Used in {len(self._usage)} recipe{'s' if len(self._usage) != 1 else ''}"
                if self._usage else 'Not used in any recipe']
        if current:
            bits.append(f'last price {_short_date(current["effective_date"])}')
        self.subtitle.setText(' · '.join(bits))

    def _on_new_price(self):
        if IngredientPriceEditDialog(self.ingredient_id, parent=self).exec() == QDialog.Accepted:
            self.modified = True
            self._refresh_prices()

    def _sync_unit_labels(self):
        unit = self.unit_edit.text().strip() or 'unit'
        self.per_unit_label.setText(f'PER {unit.upper()}')
        self.nutrition_title.setText(f'Nutrition per {unit}')

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
        self.usda_note.setText(note + ' Save to keep these values.')
        self.usda_note.show()

    def _set_photo(self, filename):
        self._image = filename or ''
        while self.photo_host.count():
            w = self.photo_host.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.photo_host.addWidget(IngredientThumb(
            self.ingredient_id, 96, name=self.name_edit.text() or '?',
            image_filename=self._image, tag_color=self._row.get('TagColor') or '',
            radius=8, tint=True))
        self.photo_name.setText(self._image or 'No photo')
        self.remove_photo.setVisible(bool(self._image))

    def _on_change_photo(self):
        exts = ' '.join(f'*{e}' for e in IMAGE_EXTENSIONS)
        path, _ = QFileDialog.getOpenFileName(
            self, 'Choose a photo', config.INGREDIENTS_PATH, f'Images ({exts})')
        if not path:
            return
        folder = os.path.normcase(os.path.abspath(config.INGREDIENTS_PATH))
        if os.path.normcase(os.path.dirname(os.path.abspath(path))) != folder:
            # Photos live in the data folder; bring outside ones in.
            target = os.path.join(config.INGREDIENTS_PATH, os.path.basename(path))
            if os.path.exists(target) and QMessageBox.question(
                self, 'Replace photo?',
                f'"{os.path.basename(path)}" is already in the photos folder. Replace it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            ) != QMessageBox.Yes:
                return
            try:
                shutil.copy(path, target)
            except OSError as exc:
                QMessageBox.warning(self, 'Photo not copied', str(exc))
                return
        self._set_photo(os.path.basename(path))

    def _fill_used_in(self):
        while self._used_layout.count():
            w = self._used_layout.takeAt(0).widget()
            if w is not None:
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
            name = QLabel(f'<a href="{u["Id"]}" style="color: {_KALE}">{u["Name"]}</a>')
            name.setToolTip('Close and open this recipe in a tab')
            name.linkActivated.connect(lambda href: self._open_recipe(int(href)))
            hl.addWidget(name, stretch=1)
            meta = QLabel(f'{_num_text(u["Quantity"])} {u["Unit"] or ""} · ${float(u["LineCost"] or 0):.2f}')
            meta.setStyleSheet(f'color: {_MUTED};')
            hl.addWidget(meta)
            self._used_layout.addWidget(row)
        extra = len(self._usage) - _USED_PREVIEW
        if extra > 0:
            more = QLabel(f'<a href="more" style="color: {_ROMAINE}">'
                          f'{"Show fewer" if self._show_all_used else f"{extra} more"}</a>'
                          f'<span style="color: {_MUTED}"> · links open the recipe in a tab</span>')
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
            self.portion_edit.text(),
            tuple(sorted(self.nutrition.values().items())),
            self.category.selected(), self._image,
            tuple(self.allergens.checked_ids()),
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
        values = self.nutrition.values()
        # Cost comes from the price history (a trigger keeps it current);
        # re-read it so Save never overwrites a price added just now.
        current_cost = (db.get_ingredients(self.ingredient_id) or {}).get('Cost') or 0
        values.update({
            'Name': name, 'Unit': self.unit_edit.text(), 'Portion': self.portion_edit.text(),
            'Weight': self.weight_edit.text(), 'Cost': str(current_cost),
            'ImageFilename': self._image or None,
        })
        db.update_ingredient(self.ingredient_id, values)
        db.set_ingredient_tag(self.ingredient_id, self.category.selected())
        db.set_ingredient_allergens(self.ingredient_id, self.allergens.checked_ids())
        self.modified = True
        self.status_message = f"Saved '{name}'"
        self._baseline = self._collect_state()
        return True

    def _on_save(self):
        if self._save():
            self.accept()

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
