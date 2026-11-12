'''Analytics › Pricing and Nutrition: recipes as rows, per serving.

Pricing: ingredients (hover the ⓘ for the list), cost by ingredient
category (collapsed by default), cost, menu price and food cost %.
Nutrition: weight and the Nutrition Facts values, then allergens the
recipe contains and facility-only ones. Click a header to sort; the
Average row stays last. Fed by utilities.compare.build().
'''
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QSizePolicy, QTableWidget, QTableWidgetItem, QToolButton,
    QVBoxLayout, QWidget,
)

from gui.services import food_cost
from gui.widgets import config_kit as kit
from utilities import compare


_ROW_LINE = '#f3ece0'
_WARN_BG = '#fff0dc'
_LEFT = Qt.AlignLeft | Qt.AlignVCenter
_RIGHT = Qt.AlignRight | Qt.AlignVCenter


def _money(v):
    return compare.fmt(v, '$')


def _pct(v):
    return compare.fmt(v, '%')


def _amount(v):
    '''A nutrient with its unit in the header: "640", "3.5"; None is "—".'''
    if v is None:
        return '—'
    return f'{v:.1f}' if 0 < abs(v) < 10 else f'{v:,.0f}'


def _swatch(color):
    pix = QPixmap(4, 16)
    pix.fill(QColor(color))
    return QIcon(pix)


def _info_icon():
    '''A small circled "i": this cell has more on hover.'''
    pix = QPixmap(28, 28)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(kit.MUTED))
    pen.setWidthF(2.2)
    p.setPen(pen)
    p.drawEllipse(3, 3, 22, 22)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(kit.MUTED))
    p.drawEllipse(12, 7, 4, 4)
    p.drawRoundedRect(12, 12, 4, 10, 1.5, 1.5)
    p.end()
    pix.setDevicePixelRatio(2)
    return QIcon(pix)


def _low(v):
    '''Sort key for a value that may be blank ("—"): blank sorts lowest.'''
    return float('-inf') if v is None else v


class RecipeMatrix(QWidget):
    recipeActivated = Signal(int)

    def __init__(self, mode, parent=None):
        '''mode: "pricing" or "nutrition".'''
        super().__init__(parent)
        self.mode = mode
        self.data = None
        self._colors = {}
        self._rows = []
        self._columns = []
        self._sort = None           # (column key, descending)
        self._name_width = 0
        self._info = _info_icon()
        self._open = QSettings().value('analytics/categoriesOpen', False, type=bool)

        self.toggle = QToolButton()
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setStyleSheet(f'QToolButton {{ border: 0; color: {kit.KALE}; font-weight: 600; padding: 2px 0; }}'
                                  f' QToolButton:hover {{ color: {kit.ROMAINE_HOVER}; }}')
        self.toggle.clicked.connect(lambda: self.set_categories_open(not self._open))
        self.toggle.setVisible(mode == 'pricing')
        self.summary = QLabel('')
        self.summary.setStyleSheet(f'color: {kit.MUTED};')
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(self.summary)
        head.addWidget(self.toggle)
        head.addStretch()

        t = self.table = QTableWidget()
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.NoSelection)
        t.setFocusPolicy(Qt.NoFocus)
        t.setShowGrid(False)
        t.verticalHeader().setVisible(False)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        t.setFrameShape(QFrame.NoFrame)
        t.setWordWrap(False)
        t.setMouseTracking(True)
        t.cellEntered.connect(self._on_cell_entered)
        t.cellDoubleClicked.connect(self._on_double_click)
        hh = t.horizontalHeader()
        hh.setHighlightSections(False)
        hh.setSectionsClickable(True)
        hh.sectionClicked.connect(self._on_header_clicked)
        t.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; color: {kit.KALE}; border: 0; }}
            QTableWidget::item {{ padding: 0 12px; border-top: 1px solid {_ROW_LINE}; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.KALE}; font-weight: 600; border: 0;
                border-bottom: 1px solid {kit.BORDER}; padding: 8px 12px; }}
        ''')
        self.card, cl = kit.card()
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(t)
        self.card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)   # exactly the table's height

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(self.card)
        layout.addStretch()     # spare height goes below the card, not into it
        self._sync_toggle()

    # --- data ----------------------------------------------------------

    def set_data(self, data, colors=None):
        self.data = data
        self._colors = dict(colors or {})
        self._rebuild()

    def categories_open(self):
        return self._open

    def set_categories_open(self, on):
        self._open = bool(on)
        QSettings().setValue('analytics/categoriesOpen', self._open)
        self._sync_toggle()
        self._rebuild()

    def _sync_toggle(self):
        self.toggle.setText(('▾  ' if self._open else '▸  ') + 'Cost by category')
        self.toggle.setToolTip('Hide the category columns' if self._open else 'Show cost for each ingredient category')

    def sort_by(self, key, descending=False):
        self._sort = (key, descending) if key else None
        self._rebuild()

    def rows(self):
        '''The recipes in display order.'''
        return list(self._rows)

    def csv_rows(self):
        if not self.data:
            return []
        data = dict(self.data, recipes=self.rows())
        return compare.pricing_csv(data) if self.mode == 'pricing' else compare.nutrition_csv(data)

    # --- columns -------------------------------------------------------

    def _make_columns(self):
        '''[(key, header, align, sort key(recipe), cell(recipe) -> item)].'''
        cols = [('name', 'Recipe', _LEFT, lambda r: r['name'].lower(), self._name_item)]
        if self.mode == 'pricing':
            cols.append(('ingredients', 'Ingredients', Qt.AlignCenter, None, self._ingredients_item))
            if self._open:
                for cat in self.data['categories']:
                    cols.append((('cat', cat), cat, _RIGHT, lambda r, c=cat: _low(r['categories'].get(c)),
                                 lambda r, c=cat: self._num(_money(r['categories'].get(c)), self._cat_tip(r, c))))
            cols += [
                ('cost', 'Cost', _RIGHT, lambda r: r['cost'], lambda r: self._num(_money(r['cost']))),
                ('price', 'Menu price', _RIGHT, lambda r: _low(r['menu_price']),
                 lambda r: self._num(_money(r['menu_price']))),
                ('pct', 'Food cost', _RIGHT, lambda r: _low(r['pct']), lambda r: self._pct_item(r['pct'])),
            ]
        else:
            for key, label, unit in compare.NUTRIENTS:
                cols.append((key, compare.nutrient_header(label, unit), _RIGHT, lambda r, k=key: r['totals'][k],
                             lambda r, k=key: self._num(_amount(r['totals'][k]))))
            cols += [
                ('contains', 'Contains', _LEFT, lambda r: ', '.join(r['allergens']).lower(),
                 lambda r: self._text(', '.join(r['allergens']))),
                ('facility', 'Facility', _LEFT, lambda r: ', '.join(r['facility']).lower(),
                 lambda r: self._text(', '.join(r['facility']))),
            ]
        return cols

    # --- table ---------------------------------------------------------

    def _rebuild(self):
        if self.data is None:
            return
        cols = self._columns = self._make_columns()
        rows = list(self.data['recipes'])
        keys = [c[0] for c in cols]
        if self._sort and self._sort[0] in keys:
            fn = cols[keys.index(self._sort[0])][3]
            rows.sort(key=fn, reverse=self._sort[1])
        self._rows = rows

        t = self.table
        t.clearSpans()
        t.clear()
        t.setColumnCount(len(cols))
        t.setRowCount(len(rows) + (1 if rows else 0))
        for c, (key, header, align, _s, _cell) in enumerate(cols):
            item = QTableWidgetItem(header)
            item.setTextAlignment(align)
            if isinstance(key, tuple):
                item.setIcon(_swatch(self._colors.get(key[1], '#888888')))
            elif key == 'facility':
                item.setToolTip('Made in a facility that also handles these')
            t.setHorizontalHeaderItem(c, item)
        for i, r in enumerate(rows):
            for c, col in enumerate(cols):
                t.setItem(i, c, col[4](r))
            t.setRowHeight(i, 30)
        if rows:
            self._footer(len(rows))
        hh = t.horizontalHeader()
        hh.setMinimumSectionSize(64)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        # Measure with the sort arrow hidden: Qt would widen the sorted
        # column for it (the arrow draws above the text, not beside it),
        # and the table would jump on every sort.
        hh.setSortIndicatorShown(False)
        t.resizeColumnsToContents()
        if self._sort and self._sort[0] in keys:
            hh.setSortIndicator(keys.index(self._sort[0]),
                                Qt.DescendingOrder if self._sort[1] else Qt.AscendingOrder)
            hh.setSortIndicatorShown(True)
        self._name_width = t.columnWidth(0)
        self._fit()
        self.summary.setText('Per serving')

    def _fit(self):
        '''Every column keeps its content width and the card hugs them, so
        the numbers sit next to the names; when they don't fit, the table
        scrolls sideways.'''
        t = self.table
        if not t.columnCount():
            return
        t.setColumnWidth(0, self._name_width + 24)
        natural = sum(t.columnWidth(c) for c in range(t.columnCount())) + 2 * t.frameWidth() + 2
        self.card.setMaximumWidth(natural)
        hh = t.horizontalHeader()
        height = hh.sizeHint().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 4
        if natural > self.width():
            height += t.horizontalScrollBar().sizeHint().height()
        t.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.table.columnCount():
            self._fit()

    def _footer(self, row):
        t = self.table
        avg = compare.averages(dict(self.data, recipes=self._rows))
        bold = t.font()
        bold.setBold(True)
        cells = {}
        for c, (key, _h, _a, _s, _cell) in enumerate(self._columns):
            if key == 'name':
                cells[c] = QTableWidgetItem('Average')
            elif isinstance(key, tuple):
                cells[c] = self._num(_money(avg['categories'].get(key[1])))
            elif key == 'cost':
                cells[c] = self._num(_money(avg['cost']))
            elif key == 'price':
                cells[c] = self._num(_money(avg['menu_price']))
            elif key == 'pct':
                cells[c] = self._num(_pct(avg['pct']))
                cells[c].setToolTip('Average over the recipes with a menu price')
            elif key in avg:
                cells[c] = self._num(_amount(avg[key]))
        for c in range(t.columnCount()):
            item = cells.get(c) or QTableWidgetItem('')
            item.setBackground(QColor(kit.BG))
            item.setFont(bold)
            t.setItem(row, c, item)
        t.setRowHeight(row, 34)

    def _name_item(self, r):
        item = QTableWidgetItem(r['name'] + (' · archived' if r['archived'] else ''))
        item.setTextAlignment(_LEFT)
        bits = [r['name']] + ([r['format']] if r['format'] else []) + ['double-click to open']
        item.setToolTip(' · '.join(bits))
        if r['archived']:
            item.setForeground(QColor(kit.MUTED))
        return item

    def _ingredients_item(self, r):
        item = QTableWidgetItem('')
        item.setTextAlignment(Qt.AlignCenter)
        if r['ingredients']:
            item.setIcon(self._info)
            lines = [f'{cat}: {", ".join(names)}' for cat, names in r['items'].items()]
            item.setToolTip('\n'.join(lines))
        return item

    def _num(self, text, tip=''):
        item = QTableWidgetItem(text)
        item.setTextAlignment(_RIGHT)
        if text == '—':
            item.setForeground(QColor(kit.MUTED))
        if tip:
            item.setToolTip(tip)
        return item

    def _text(self, text):
        item = QTableWidgetItem(text or '—')
        item.setTextAlignment(_LEFT)
        if not text:
            item.setForeground(QColor(kit.MUTED))
        return item

    def _pct_item(self, pct):
        item = self._num(_pct(pct))
        if pct is None:
            item.setToolTip('No menu price')
        elif food_cost.over_percent(pct):
            item.setText('▲ ' + item.text())
            item.setForeground(QColor(kit.WARN))
            item.setBackground(QColor(_WARN_BG))
            item.setToolTip(f'Over the {food_cost.target_percent():.0f}% target')
        return item

    def _cat_tip(self, r, cat):
        names = r['items'].get(cat)
        return ', '.join(names) if names else ''

    # --- interaction ---------------------------------------------------

    def _on_header_clicked(self, section):
        if not (0 <= section < len(self._columns)):
            return
        key, sort_key = self._columns[section][0], self._columns[section][3]
        if sort_key is None:
            return      # the Ingredients column is a hover list, not a value
        if self._sort and self._sort[0] == key:
            # Name: A→Z, Z→A, off. Numbers: high→low, low→high, off.
            first_desc = key != 'name' and key not in ('contains', 'facility')
            if self._sort[1] == first_desc:
                self._sort = (key, not first_desc)
            else:
                self._sort = None
        else:
            self._sort = (key, key not in ('name', 'contains', 'facility'))
        self._rebuild()

    def _on_cell_entered(self, row, col):
        hover = (0 <= col < len(self._columns) and self._columns[col][0] == 'ingredients'
                 and row < len(self._rows))
        self.table.viewport().setCursor(Qt.WhatsThisCursor if hover else Qt.ArrowCursor)

    def _on_double_click(self, row, _col):
        if 0 <= row < len(self._rows):
            self.recipeActivated.emit(self._rows[row]['id'])
