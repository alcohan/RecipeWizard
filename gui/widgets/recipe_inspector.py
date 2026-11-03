'''Right-hand inspector for the Recipes Library, per the Framework
canvas: a quick look at the selected recipe without opening it.

Wedge, name, format · yield · when it was last edited, Cost / Food
cost / Calories, components counted by category, its tags and the
diets it fits,
allergens with their sources (which also say why it misses a diet),
and Open in tab / Duplicate.

Only the selected recipe's components and allergen sources are
queried, when the selection changes.
'''
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import db
from gui.widgets.elided_label import ElidedLabel
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.recipe_gallery import FOOD_COST_TARGET, diet_chip, tag_chip
from gui.widgets.wedge_view import WedgeView
from utilities.diets import DIET_NAMES


_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_WARN = '#8a4a00'
_WEDGE = 184


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def edited_ago(stamp, now=None):
    '''"edited today" / "edited yesterday" / "edited 3 days ago" /
    "edited Oct 14", from an SQLite UTC timestamp.'''
    try:
        when = datetime.fromisoformat(str(stamp)[:19])
    except (TypeError, ValueError):
        return ''
    days = ((now or datetime.utcnow()).date() - when.date()).days
    if days <= 0:
        return 'edited today'
    if days == 1:
        return 'edited yesterday'
    if days < 14:
        return f'edited {days} days ago'
    return 'edited ' + when.strftime('%b %d').replace(' 0', ' ')


def _fmt(value):
    try:
        return '{:.2f}'.format(float(value)).rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(value or '')


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()


class RecipeInspector(QScrollArea):
    openRequested = Signal(int)
    duplicateRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet(f'QScrollArea {{ border: 0; border-left: 1px solid {_BORDER};'
                           ' background: #ffffff; }')
        self._id = None

        host = QWidget()
        host.setObjectName('InspectorHost')
        host.setStyleSheet(f'QWidget#InspectorHost {{ background: #ffffff; }}'
                           f' QLabel {{ color: {_KALE}; }}')
        self.setWidget(host)

        self._wedge_slot = QHBoxLayout()
        self._wedge_slot.setContentsMargins(0, 0, 0, 0)
        self.wedge = None

        self.name = QLabel('')
        name_font = QFont()
        name_font.setFamilies(['Gooper Semicondensed', 'Fraunces', 'Georgia', 'serif'])
        name_font.setPixelSize(24)
        name_font.setBold(True)
        self.name.setFont(name_font)
        self.name.setWordWrap(True)
        self.name.setMinimumWidth(1)
        self.meta = QLabel('')
        self.meta.setWordWrap(True)
        self.meta.setStyleSheet(f'color: {_MUTED};')

        stats = QFrame()
        stats.setObjectName('Stats')
        stats.setStyleSheet(f'QFrame#Stats {{ border: 1px solid {_BORDER}; border-radius: 8px; }}')
        sl = QHBoxLayout(stats)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(8)
        self._stats = {}
        for key, label in (('cost', 'Cost'), ('food', 'Food cost'), ('kcal', 'Calories')):
            col = QVBoxLayout()
            col.setSpacing(2)
            title = QLabel(label)
            title.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
            value = QLabel('')
            value.setStyleSheet(f'color: {_KALE}; font-size: 20px; font-weight: 650;')
            for lbl in (title, value):
                lbl.setMinimumWidth(1)   # three columns share the card's width
            col.addWidget(title)
            col.addWidget(value)
            sl.addLayout(col, stretch=1)
            self._stats[key] = value

        self.components_title = _eyebrow('Components')
        self._component_rows = QVBoxLayout()
        self._component_rows.setSpacing(4)

        self._diet_chips = FlowLayout()
        diet_wrap = QWidget()
        diet_wrap.setLayout(self._diet_chips)

        self.allergens = QLabel('')
        self.allergens.setWordWrap(True)
        self.allergens.setTextFormat(Qt.RichText)

        self.open_btn = QPushButton('Open in tab   Enter')
        self.open_btn.setStyleSheet(
            f'QPushButton {{ height: 36px; border: 0; border-radius: 8px; background: {_ROMAINE};'
            f' color: #ffffff; font-weight: 600; }} QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}')
        self.open_btn.clicked.connect(lambda: self._id is not None and self.openRequested.emit(self._id))
        self.dup_btn = QPushButton('Duplicate   Ctrl+D')
        self.dup_btn.setStyleSheet(
            f'QPushButton {{ height: 36px; border: 1px solid #7d8771; border-radius: 8px;'
            f' background: #ffffff; color: {_KALE}; }} QPushButton:hover {{ background: #f3ece0; }}')
        self.dup_btn.clicked.connect(lambda: self._id is not None and self.duplicateRequested.emit(self._id))
        for btn in (self.open_btn, self.dup_btn):
            # Share the panel's width instead of setting its minimum.
            btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.open_btn)
        buttons.addWidget(self.dup_btn)

        self.empty = QLabel('Select a recipe to see its cost, components, diets and allergens.')
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f'color: {_MUTED};')

        self._body = QWidget()
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(16)
        bl.addLayout(self._wedge_slot)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(self.name)
        name_col.addWidget(self.meta)
        bl.addLayout(name_col)
        bl.addWidget(stats)
        comp_col = QVBoxLayout()
        comp_col.setSpacing(6)
        comp_col.addWidget(self.components_title)
        comp_col.addLayout(self._component_rows)
        bl.addLayout(comp_col)
        diet_col = QVBoxLayout()
        diet_col.setSpacing(6)
        diet_col.addWidget(_eyebrow('Tags & diets'))
        diet_col.addWidget(diet_wrap)
        bl.addLayout(diet_col)
        allergen_col = QVBoxLayout()
        allergen_col.setSpacing(4)
        allergen_col.addWidget(_eyebrow('Allergens'))
        allergen_col.addWidget(self.allergens)
        bl.addLayout(allergen_col)
        bl.addStretch()
        bl.addLayout(buttons)

        layout = QVBoxLayout(host)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self.empty)
        layout.addWidget(self._body, stretch=1)
        self.show_recipe(None)

    def current_id(self):
        return self._id

    def show_recipe(self, row):
        '''`row` is a RecipesModel row dict, or None to clear.'''
        if row is None:
            self._id = None
            self._body.hide()
            self.empty.show()
            return
        rid = row['Id']
        self._id = rid
        self.empty.hide()
        self._body.show()

        # A fresh wedge each time: WedgeView is bound to one recipe.
        if self.wedge is not None:
            self.wedge.setParent(None)
            self.wedge.deleteLater()
        self.wedge = WedgeView(rid, size=_WEDGE, defer=True)
        self._wedge_slot.addWidget(self.wedge, alignment=Qt.AlignHCenter)
        self.wedge.render_async()

        self.name.setText(row.get('Name') or '')
        unit = row.get('Unit') or ''
        bits = [row.get('TagName') or 'Sub-recipe',
                f'yields {_fmt(row.get("OutputQty") or 1)} {unit}'.strip(),
                edited_ago(row.get('UpdatedAt'))]
        self.meta.setText(' · '.join(b for b in bits if b))

        self._stats['cost'].setText(f'${float(row.get("CostRaw") or 0):.2f}')
        pct = row.get('FoodCostPct')
        food = self._stats['food']
        if pct is None:
            food.setText('—')
            food.setToolTip('No menu price set')
            food.setStyleSheet(f'color: {_MUTED}; font-size: 20px; font-weight: 650;')
        else:
            food.setText(f'{pct:.1f}%')
            food.setToolTip(f'of ${float(row["MenuPrice"]):.2f} · target {FOOD_COST_TARGET:.0f}%')
            color = _WARN if pct > FOOD_COST_TARGET else _KALE
            food.setStyleSheet(f'color: {color}; font-size: 20px; font-weight: 650;')
        self._stats['kcal'].setText(f'{row.get("CaloriesPerServing", 0):.0f}')

        self._fill_components(rid)
        sources = db.get_recipe_allergen_sources(rid)
        self._fill_diets(row)
        if sources:
            self.allergens.setText('<br>'.join(
                f'{a} <span style="color: {_MUTED}">— {", ".join(src)}</span>' for a, src in sources))
        else:
            self.allergens.setText(f'<span style="color: {_MUTED}">None</span>')

    def _fill_components(self, rid):
        _clear(self._component_rows)
        counts = {}
        comps = db.recipe_components(rid)
        for c in comps:
            if c.get('Type') == 'recipe':
                name, color = 'Sub-recipes', '#a7ad9c'
            else:
                name, color = c.get('TagName') or 'Uncategorized', c.get('TagColor') or '#a7ad9c'
            entry = counts.setdefault(name, [color, 0])
            entry[1] += 1
        n = len(comps)
        self.components_title.setText(f"{n} COMPONENT{'S' if n != 1 else ''}" if n else 'NO COMPONENTS YET')
        for name, (color, count) in counts.items():
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(8)
            dot = QLabel()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f'background: {color}; border-radius: 5px;')
            hl.addWidget(dot)
            hl.addWidget(ElidedLabel(name), stretch=1)
            num = QLabel(str(count))
            num.setStyleSheet(f'color: {_MUTED};')
            hl.addWidget(num)
            self._component_rows.addWidget(row)

    def _fill_diets(self, row):
        _clear(self._diet_chips)
        diets = row.get('Diets') or []
        tags = row.get('TagNames') or []
        for name in tags:
            self._diet_chips.addWidget(tag_chip(name))
        for key in diets:
            self._diet_chips.addWidget(diet_chip(DIET_NAMES[key]))
        if not diets and not tags:
            none = QLabel('No tags, and none of the built-in diets')
            none.setStyleSheet(f'color: {_MUTED};')
            self._diet_chips.addWidget(none)
