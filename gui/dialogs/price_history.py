'''Price history viewer for both ingredients and recipes.

Ingredient mode shows a line chart of the unit-price history with one row
per (date, supplier). Recipe mode adds a pie chart of cost-by-ingredient
for the date highlighted in the table, plus a callout listing the
ingredients whose missing earlier history caps the recipe's earliest
chartable date.'''
from datetime import datetime

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

import config
import db


class PriceHistoryDialog(QDialog):
    def __init__(self, target_id, name, recipe_mode=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Price History | {name}')
        self.resize(1200, 600)

        self.name = name
        self.recipe_mode = recipe_mode
        self.target_id = target_id

        if recipe_mode:
            self.history = db.get_recipe_price_history(target_id)
            self._price_fmt = '${:.2f}'
            table_headers = ('Date', 'Unit Price')
        else:
            self.history = db.get_price_history(target_id)
            self._price_fmt = '${:.4f}'
            table_headers = ('Date', 'Unit Price', 'Supplier')

        self.table = self._build_table(table_headers)
        tabs, self.line_figure, self.line_canvas, self.pie_figure, self.pie_canvas = self._build_tabs()

        if self.history:
            self.line_ax = self.line_figure.add_subplot(111)
            self._plot_line()
            if recipe_mode and self.pie_figure is not None:
                self.pie_ax = self.pie_figure.add_subplot(111)
                self._plot_pie(self.history[-1]['date'])

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.table)
        if recipe_mode:
            limiting_widget = self._build_limiting_dates()
            if limiting_widget is not None:
                left_layout.addWidget(limiting_widget)

        main_row = QHBoxLayout()
        main_row.addLayout(left_layout, stretch=2)
        main_row.addWidget(tabs, stretch=3)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(main_row, stretch=1)
        layout.addWidget(buttons)

    # --- builders ---

    def _build_table(self, headers):
        table = QTableWidget(len(self.history), len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, row in enumerate(self.history):
            table.setItem(r, 0, QTableWidgetItem(row['date']))
            table.setItem(r, 1, QTableWidgetItem(self._price_fmt.format(row['price'])))
            if not self.recipe_mode:
                table.setItem(r, 2, QTableWidgetItem(row.get('supplier') or ''))
        table.resizeColumnsToContents()
        table.cellClicked.connect(self._on_row_clicked)
        return table

    def _build_tabs(self):
        tabs = QTabWidget()
        if not self.history:
            placeholder = QLabel('No price history yet.')
            placeholder.setEnabled(False)
            tabs.addTab(placeholder, 'History')
            return tabs, None, None, None, None

        line_fig = Figure(figsize=(6, 4.5))
        line_canvas = FigureCanvasQTAgg(line_fig)
        tabs.addTab(line_canvas, 'History Over Time')

        pie_fig = pie_canvas = None
        if self.recipe_mode:
            pie_fig = Figure(figsize=(6, 4.5))
            pie_canvas = FigureCanvasQTAgg(pie_fig)
            tabs.addTab(pie_canvas, 'Ingredient Breakdown')

        return tabs, line_fig, line_canvas, pie_fig, pie_canvas

    def _build_limiting_dates(self):
        '''Recipe mode only: show which ingredients are capping the chart's
        earliest date. Clicking row in main table won't change this — it's
        a property of the recipe, not of the selected date.'''
        rows = db.get_recipe_price_history_dates(self.target_id)
        if not rows:
            return None
        max_date = max(r['earliest_date'] for r in rows)
        limiting_names = [r['Name'] for r in rows if r['earliest_date'] == max_date]
        if not limiting_names:
            return None

        wrap = QWidget()
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        callout = QLabel(
            f'Price data starts {max_date} due to history available on ingredients.\n'
            f'To extend, add older entries for:'
        )
        callout.setWordWrap(True)
        listw = QListWidget()
        for nm in limiting_names:
            listw.addItem(QListWidgetItem(nm))
        listw.setMaximumHeight(min(180, 24 * len(limiting_names) + 8))
        layout.addWidget(callout)
        layout.addWidget(listw)
        return wrap

    # --- plotting ---

    def _plot_line(self, highlight_index=None):
        if not self.history or self.line_canvas is None:
            return
        self.line_ax.clear()
        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in self.history]
        prices = [d['price'] for d in self.history]
        self.line_ax.plot_date(dates, prices, linestyle='solid')
        self.line_ax.set_title(self.name)
        self.line_ax.set_xlabel('Date')
        self.line_ax.set_ylabel('Price')
        self.line_ax.set_ylim(0, max(prices) * 1.1 if prices else 1)
        fmt = '${x:1.2f}' if self.recipe_mode else '${x:1.4f}'
        self.line_ax.yaxis.set_major_formatter(fmt)
        locator = mdates.AutoDateLocator()
        self.line_ax.xaxis.set_major_locator(locator)
        self.line_ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        for tick in self.line_ax.get_xticklabels():
            tick.set_rotation(45)
            tick.set_ha('right')
        self.line_figure.subplots_adjust(bottom=0.2)
        for i, (d, p) in enumerate(zip(dates, prices)):
            weight = 'bold' if i == highlight_index else 'normal'
            self.line_ax.text(d, p, self._price_fmt.format(p), ha='center', va='bottom', fontweight=weight)
        self.line_canvas.draw()

    def _plot_pie(self, date):
        if not self.recipe_mode or self.pie_canvas is None:
            return
        data = db.get_recipe_price_history_details(self.target_id, date)
        if not data:
            return
        self.pie_ax.clear()
        labels = [f"{item['Name']} ${item['price']:.2f}" for item in data]
        values = [item['price'] for item in data]
        self.pie_ax.set_title(f'{self.name} {date}')
        self.pie_ax.pie(values, labels=labels, autopct='%1.1f%%')
        self.pie_ax.axis('equal')
        self.pie_canvas.draw()

    def _on_row_clicked(self, row, _col):
        if not self.history:
            return
        self._plot_line(highlight_index=row)
        if self.recipe_mode:
            self._plot_pie(self.history[row]['date'])
