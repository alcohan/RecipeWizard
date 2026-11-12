'''Analytics › Scenarios: every active recipe against the baseline and
the chosen scenarios — cost, food cost % and its change.

Scenario chips pick the columns (Baseline always shows); the rows are
the compare tray's recipes after its filters (set_recipe_ids), under
their format's heading when grouped (set_group), and "Changed only"
keeps recipes a scenario moves.
Hovering a cost lists the rules behind it; its Cost change lists the
ingredients behind it; a price says where it came from. The footer averages food cost over the priced recipes shown.
Numbers come from utilities.scenarios, which never writes.
'''
from html import escape

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

import db
from gui.services import food_cost
from gui.widgets import config_kit as kit
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.text_fit import literal
from gui.widgets.recipe_gallery import group_title
from utilities import compare, scenarios


_ROW_LINE = '#f3ece0'
_WARN_BG = '#fff0dc'
_ID_ROLE = Qt.UserRole


def _money(v, signed=False):
    if v is None:
        return '—'
    if signed:
        return f'{"+" if v >= 0 else "−"}${abs(v):,.2f}'
    return f'${v:,.2f}'


def _cost_delta(v):
    '''Signed dollars, or $0.00 when it doesn't move.'''
    return '$0.00' if abs(v) < 0.005 else _money(v, signed=True)


def _pct(v):
    return '—' if v is None else f'{v:.1f}%'


_PER = 4    # columns per scenario: Cost, Cost change, Food cost, Change


def _pts(v):
    if v is None:
        return ''
    if abs(v) < 0.05:
        return '0.0'
    return f'{"▲" if v > 0 else "▼"} {abs(v):.1f}'


class ScenarioMatrix(QWidget):
    recipeActivated = Signal(int)
    setupRequested = Signal()
    refreshed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stale = True
        self.result = None
        self._shown = []
        self._table_rows = []       # the recipe on each table row; None for a group heading
        self._group = 'none'          # the Analytics tab sets Format (its default)
        self._format_order = []
        settings = QSettings()
        self._chosen = {int(x) for x in (settings.value('analytics/scenarioIds', '', type=str) or '').split(',')
                        if x.strip().isdigit()}
        self._all_chosen = settings.value('analytics/scenarioAll', True, type=bool)

        # Controls.
        self.chips_host = QWidget()
        self.chips = FlowLayout(self.chips_host, spacing=8)
        self._recipe_ids = None
        self.changed_only = QCheckBox('Changed only')
        self.changed_only.setStyleSheet(f'QCheckBox {{ color: {kit.KALE}; spacing: 8px; }}')
        self.changed_only.setChecked(settings.value('analytics/scenarioChanged', False, type=bool))
        self.changed_only.toggled.connect(lambda _on: self._on_filter())
        edit = kit.button('Edit scenarios')
        edit.clicked.connect(self.setupRequested.emit)
        filters = QHBoxLayout()
        filters.setSpacing(12)
        filters.addWidget(self.changed_only)
        filters.addStretch()
        filters.addWidget(edit)

        # Table.
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setWordWrap(False)
        self.table.setMouseTracking(True)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.cellDoubleClicked.connect(self._on_double_click)
        self.table.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; color: {kit.KALE}; border: 0; }}
            QTableWidget::item {{ padding: 0 12px; border-top: 1px solid {_ROW_LINE}; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.KALE}; font-weight: 600; border: 0;
                border-bottom: 1px solid {kit.BORDER}; padding: 8px 12px; }}
        ''')
        self.table_card, tcl = kit.card()
        tcl.setContentsMargins(0, 0, 0, 0)
        tcl.addWidget(self.table)
        self.summary = QLabel('')
        self.summary.setStyleSheet(f'color: {kit.MUTED};')

        # Empty state.
        self.empty_card, ecl = kit.card()
        ecl.setContentsMargins(24, 20, 24, 24)
        ecl.addWidget(kit.subheading('No scenarios yet'))
        ecl.addWidget(kit.note('Set up packaging and menu price changes for a kind of store or order, '
                               'then compare them here.'))
        setup = kit.button('Set up scenarios', primary=True)
        setup.clicked.connect(self.setupRequested.emit)
        ecl.addWidget(setup, alignment=Qt.AlignLeft)

        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(14)
        bl.addWidget(self.chips_host)
        bl.addLayout(filters)
        bl.addWidget(self.summary)
        bl.addWidget(self.table_card)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addWidget(self.empty_card)
        layout.addWidget(self.body)
        layout.addStretch()

    # --- lifecycle -----------------------------------------------------

    def mark_stale(self):
        self._stale = True
        if self.isVisible():
            self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()

    def refresh(self):
        self._stale = False
        self._recipe_tags = db.get_tags(kind='recipe_tag')
        self._format_names = {f['id']: f['name'] for f in db.get_tags(kind='recipe')}
        self._ingredient_names = {i['Id']: i['Name'] for i in db.get_ingredients()}
        self._rules = {r['id']: r for s in scenarios.get_scenarios() for r in s['rules']}
        self.result = scenarios.matrix()
        ids = [s['id'] for s in self.result['scenarios']]
        if self._all_chosen:
            self._chosen = set(ids)
        self._chosen &= set(ids)
        has = bool(ids)
        self.empty_card.setVisible(not has)
        self.body.setVisible(has)
        self._rebuild_chips()
        self._rebuild_table()
        self.refreshed.emit()

    def has_scenarios(self):
        return bool(self.result and self.result['scenarios'])

    def set_group(self, group, format_order=()):
        '''"format": rows under their format's heading, in `format_order`;
        "none": one list.'''
        group = group if group in ('format', 'none') else 'format'
        if (group, list(format_order)) == (self._group, self._format_order):
            return
        self._group, self._format_order = group, list(format_order)
        self._rebuild_table()

    def set_recipe_ids(self, recipe_ids):
        '''The rows to show, in order (None: every active recipe).'''
        ids = None if recipe_ids is None else list(recipe_ids)
        if ids == self._recipe_ids:
            return
        self._recipe_ids = ids
        self._rebuild_table()

    # --- controls ------------------------------------------------------

    def scenario_ids(self):
        '''The chosen scenarios, in their order.'''
        if not self.result:
            return []
        return [s['id'] for s in self.result['scenarios'] if s['id'] in self._chosen]

    def _rebuild_chips(self):
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        base = QLabel('Baseline')
        base.setStyleSheet(f'QLabel {{ border: 1px solid {kit.BORDER}; border-radius: 10px; padding: 3px 12px;'
                           f' background: {kit.SELECTED}; color: {kit.KALE}; font-weight: 600; }}')
        self.chips.addWidget(base)
        for s in self.result['scenarios']:
            chip = QPushButton(literal(s['name']))
            chip.setCheckable(True)
            chip.setChecked(s['id'] in self._chosen)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setFocusPolicy(Qt.NoFocus)
            chip.setStyleSheet(f'QPushButton {{ border: 1px solid {kit.FIELD_BORDER}; border-radius: 10px;'
                               f' padding: 3px 12px; background: #ffffff; color: {kit.KALE}; }}'
                               ' QPushButton:hover:!checked { background: #f3ece0; }'
                               f' QPushButton:checked {{ border-color: {kit.ROMAINE}; background: {kit.ROMAINE};'
                               ' color: #ffffff; font-weight: 600; }')
            chip.toggled.connect(lambda on, sid=s['id']: self.set_chosen(sid, on))
            self.chips.addWidget(chip)

    def set_chosen(self, scenario_id, on):
        if on:
            self._chosen.add(scenario_id)
        else:
            self._chosen.discard(scenario_id)
        all_ids = {s['id'] for s in self.result['scenarios']}
        self._all_chosen = self._chosen >= all_ids
        settings = QSettings()
        settings.setValue('analytics/scenarioIds', ','.join(str(i) for i in sorted(self._chosen)))
        settings.setValue('analytics/scenarioAll', self._all_chosen)
        self._rebuild_table()

    def _on_filter(self):
        QSettings().setValue('analytics/scenarioChanged', self.changed_only.isChecked())
        self._rebuild_table()

    def visible_recipes(self):
        '''The rows shown, after the filters.'''
        if not self.result:
            return []
        sids = self.scenario_ids()
        recipes = self.result['recipes']
        if self._recipe_ids is not None:
            by_id = {r['id']: r for r in recipes}
            recipes = [by_id[i] for i in self._recipe_ids if i in by_id]
        out = []
        for r in recipes:
            if self.changed_only.isChecked() and not any(self._changed(r, sid) for sid in sids):
                continue
            out.append(r)
        return out

    @staticmethod
    def _changed(r, sid):
        c, b = r['cells'][sid], r['base']
        return c['excluded'] or bool(c['applied']) or c['price'] != b['price']

    # --- table -----------------------------------------------------------

    def _rebuild_table(self):
        if not self.result:
            return
        rows = self.visible_recipes()
        layout = list(rows)
        if self._group == 'format' and rows:
            groups = compare.format_groups(rows, self._format_order,
                                           lambda r: self._format_names.get(r['format_id']))
            rows = [r for _name, members in groups for r in members]
            layout = []
            for name, members in groups:
                layout.append((name, len(members)))
                layout.extend(members)
        self._shown = rows
        self._table_rows = [r if isinstance(r, dict) else None for r in layout]
        sids = self.scenario_ids()
        names = {s['id']: s['name'] for s in self.result['scenarios']}
        t = self.table
        t.clearSpans()
        t.clear()
        heads = ['Recipe', 'Baseline\nCost', 'Baseline\nFood cost']
        for sid in sids:
            heads += [f'{names[sid]}\nCost', f'{names[sid]}\nCost change', f'{names[sid]}\nFood cost',
                      f'{names[sid]}\nChange']
        t.setColumnCount(len(heads))
        t.setRowCount(len(layout) + 1)
        for c, text in enumerate(heads):
            item = QTableWidgetItem(text)
            item.setTextAlignment((Qt.AlignLeft if c == 0 else Qt.AlignRight) | Qt.AlignVCenter)
            t.setHorizontalHeaderItem(c, item)
        bold = t.font()
        bold.setBold(True)
        muted = QColor(kit.MUTED)
        for i, r in enumerate(layout):
            if not isinstance(r, dict):
                self._group_row(i, *r)
                continue
            fmt = self._format_names.get(r['format_id'])
            label = QTableWidgetItem(r['name'])
            label.setData(_ID_ROLE, r['id'])
            label.setToolTip(f'{r["name"]}{" · " + fmt if fmt else ""} · double-click to open')
            t.setItem(i, 0, label)
            base = r['base']
            t.setItem(i, 1, self._num(_money(base['cost'])))
            t.setItem(i, 2, self._pct_item(base['pct'], base['price'], None))
            for k, sid in enumerate(sids):
                col = 3 + k * _PER
                cell = r['cells'][sid]
                if cell['excluded']:
                    item = QTableWidgetItem('Left out')
                    item.setForeground(muted)
                    item.setTextAlignment(Qt.AlignCenter)
                    t.setItem(i, col, item)
                    t.setSpan(i, col, 1, _PER)
                    continue
                cost = self._num(_money(cell['cost']))
                cost.setToolTip(self._cost_tip(r, cell))
                if cell['applied'] and any(a['action'] != 'price_adjust' for a in cell['applied']):
                    cost.setFont(bold)
                t.setItem(i, col, cost)
                t.setItem(i, col + 1, self._cost_change_item(r, cell))
                t.setItem(i, col + 2, self._pct_item(cell['pct'], cell['price'], self._price_tip(r, sid, cell)))
                dpct = None if cell['pct'] is None or base['pct'] is None else cell['pct'] - base['pct']
                change = self._num(_pts(dpct))
                change.setToolTip('' if dpct is None else 'Food cost points vs baseline')
                self._tint(change, dpct, 0.05)
                t.setItem(i, col + 3, change)
            t.setRowHeight(i, 30)
        self._footer(len(layout), sids)
        hh = t.horizontalHeader()
        hh.setMinimumSectionSize(70)
        hh.setSectionResizeMode(QHeaderView.Interactive)
        t.resizeColumnsToContents()
        t.setColumnWidth(0, t.columnWidth(0) + 24)
        self._fit()
        n = len(rows)
        self.summary.setText(f"{n} recipe{'s' if n != 1 else ''}")

    def _group_row(self, i, name, n):
        '''A format heading ("Salads 6") across the whole row.'''
        t = self.table
        item = QTableWidgetItem(f'{group_title(name)}   {n}')
        bold = t.font()
        bold.setBold(True)
        item.setFont(bold)
        item.setBackground(QColor(kit.BG))
        item.setFlags(Qt.ItemIsEnabled)
        t.setItem(i, 0, item)
        for c in range(1, t.columnCount()):
            filler = QTableWidgetItem('')
            filler.setBackground(QColor(kit.BG))
            t.setItem(i, c, filler)
        t.setSpan(i, 0, 1, t.columnCount())
        t.setRowHeight(i, 32)

    def _fit(self):
        '''The card hugs the columns so the numbers sit next to the names;
        when they don't fit, the table scrolls sideways.'''
        t = self.table
        natural = sum(t.columnWidth(c) for c in range(t.columnCount())) + 2 * t.frameWidth() + 2
        self.table_card.setMaximumWidth(natural)
        hh = t.horizontalHeader()
        height = hh.sizeHint().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 4
        if natural > self.width():
            height += t.horizontalScrollBar().sizeHint().height()
        t.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.table.columnCount():
            self._fit()

    def _footer(self, row, sids):
        t = self.table
        avg = scenarios.averages(self.result, [r['id'] for r in self._shown])
        label = QTableWidgetItem('Average food cost')
        f = t.font()
        f.setBold(True)
        label.setFont(f)
        cells = {0: label, 2: self._num(_pct(avg['base']))}
        for k, sid in enumerate(sids):
            col = 3 + k * _PER
            moves = [r['cells'][sid]['cost'] - r['base']['cost'] for r in self._shown
                     if not r['cells'][sid]['excluded']]
            if moves:
                cells[col + 1] = self._num(_cost_delta(sum(moves) / len(moves)))
                cells[col + 1].setToolTip('Average cost change')
            cells[col + 2] = self._num(_pct(avg[sid]))
            if avg[sid] is not None and avg['base'] is not None:
                cells[col + 3] = self._num(_pts(avg[sid] - avg['base']))
        for c in range(t.columnCount()):
            item = cells.get(c) or QTableWidgetItem('')
            item.setBackground(QColor(kit.BG))
            if c:
                item.setFont(f)
            t.setItem(row, c, item)
        t.setRowHeight(row, 34)

    def _num(self, text):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if text in ('—', ''):
            item.setForeground(QColor(kit.MUTED))
        return item

    def _tint(self, item, value, step):
        '''Up is warn, down is green, about zero is muted.'''
        if value is not None and value >= step:
            item.setForeground(QColor(kit.WARN))
        elif value is not None and value <= -step:
            item.setForeground(QColor(kit.ROMAINE))
        else:
            item.setForeground(QColor(kit.MUTED))

    def _cost_change_item(self, r, cell):
        '''Cost vs baseline in dollars; hover for the ingredients behind it.'''
        delta = cell['cost'] - r['base']['cost']
        item = self._num(_cost_delta(delta))
        self._tint(item, delta, 0.005)
        lines = scenarios.ingredient_changes(cell)
        if lines:
            rows = ''.join(
                f'<tr><td>{escape(self._ingredient_names.get(ing, "Ingredient"))}</td>'
                f'<td align="right" style="padding-left:16px">{_money(v, signed=True)}</td></tr>'
                for ing, v in lines)
            rows += ('<tr><td style="padding-top:4px"><b>Net</b></td><td align="right" '
                     f'style="padding-left:16px; padding-top:4px"><b>{_money(delta, signed=True)}</b></td></tr>')
            item.setToolTip(f'<table cellspacing="0">{rows}</table>')
        elif abs(delta) >= 0.005:
            item.setToolTip(f'Net {_money(delta, signed=True)}')
        return item

    def _pct_item(self, pct, price, tip):
        item = self._num(_pct(pct))
        lines = [f'Menu price {_money(price)}' if price is not None else 'No menu price']
        if tip:
            lines.append(tip)
        if food_cost.over_percent(pct):
            item.setText('▲ ' + item.text())
            item.setForeground(QColor(kit.WARN))
            item.setBackground(QColor(_WARN_BG))
            lines.append(f'Over the {food_cost.target_percent():.0f}% target')
        item.setToolTip('\n'.join(lines))
        return item

    def _cost_tip(self, r, cell):
        lines = [f'Baseline {_money(r["base"]["cost"])}']
        tags = {t['id']: t['name'] for t in self._recipe_tags}
        for a in cell['applied']:
            rule = self._rules.get(a['rule_id'])
            if rule is None or a['action'] == 'price_adjust':
                continue
            lines.append(f'{scenarios.describe_rule(rule, self._ingredient_names, tags)}  '
                         f'{_money(a["delta"], signed=True)}')
        if len(lines) == 1:
            lines.append('No changes')
        return '\n'.join(lines)

    def _price_tip(self, r, sid, cell):
        if cell['price'] == r['base']['price']:
            return ''
        adjust = [a for a in cell['applied'] if a['action'] == 'price_adjust']
        if adjust:
            return 'Price rule ' + ', '.join(_money(a['delta'], signed=True) for a in adjust)
        return 'Set for this scenario'

    def _on_double_click(self, row, _col):
        if 0 <= row < len(self._table_rows) and self._table_rows[row] is not None:
            self.recipeActivated.emit(self._table_rows[row]['id'])

    # --- export ------------------------------------------------------------

    def csv_rows(self):
        if not self.has_scenarios():
            return []
        keep = {r['id'] for r in self.visible_recipes()}
        sids = self.scenario_ids()
        result = {'scenarios': [s for s in self.result['scenarios'] if s['id'] in sids],
                  'recipes': [r for r in self.result['recipes'] if r['id'] in keep]}
        return scenarios.csv_rows(result, self._format_names)
