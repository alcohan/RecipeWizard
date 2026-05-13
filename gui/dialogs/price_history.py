'''Price history viewer. Phase 2 supports ingredient mode (line chart only).
Phase 3 extends this with recipe mode (pie chart + limiting-dates callout).'''
from datetime import datetime

import matplotlib.dates as mdates
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

import config
import db


class PriceHistoryDialog(QDialog):
    def __init__(self, ingredient_id, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Price History | {name}')
        self.resize(1100, 520)

        self.name = name
        self.history = db.get_price_history(ingredient_id)

        self.table = QTableWidget(len(self.history), 3)
        self.table.setHorizontalHeaderLabels(['Date', 'Unit Price', 'Supplier'])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, row in enumerate(self.history):
            self.table.setItem(r, 0, QTableWidgetItem(row['date']))
            self.table.setItem(r, 1, QTableWidgetItem('$ {:.4f}'.format(row['price'])))
            self.table.setItem(r, 2, QTableWidgetItem(row.get('supplier') or ''))
        self.table.resizeColumnsToContents()
        self.table.cellClicked.connect(self._on_row_clicked)

        self.figure = Figure(figsize=(6, 4.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.ax = self.figure.add_subplot(111)

        right_layout = QVBoxLayout()
        if self.history:
            right_layout.addWidget(self.canvas, stretch=1)
            self._plot()
        else:
            placeholder = QLabel('No price history yet.')
            placeholder.setEnabled(False)
            right_layout.addWidget(placeholder)
            right_layout.addStretch()

        main = QHBoxLayout()
        main.addWidget(self.table, stretch=2)
        main.addLayout(right_layout, stretch=3)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(main, stretch=1)
        layout.addWidget(buttons)

    def _plot(self, highlight_index=None):
        self.ax.clear()
        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in self.history]
        prices = [d['price'] for d in self.history]
        self.ax.plot_date(dates, prices, linestyle='solid')
        self.ax.set_title(self.name)
        self.ax.set_xlabel('Date')
        self.ax.set_ylabel('Price')
        self.ax.set_ylim(0, max(prices) * 1.1 if prices else 1)
        self.ax.yaxis.set_major_formatter('${x:1.4f}')

        locator = mdates.AutoDateLocator()
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        for tick in self.ax.get_xticklabels():
            tick.set_rotation(45)
            tick.set_ha('right')
        self.figure.subplots_adjust(bottom=0.2)

        for i, (d, p) in enumerate(zip(dates, prices)):
            weight = 'bold' if i == highlight_index else 'normal'
            self.ax.text(d, p, '${:.4f}'.format(p), ha='center', va='bottom', fontweight=weight)
        self.canvas.draw()

    def _on_row_clicked(self, row, _col):
        if not self.history:
            return
        self._plot(highlight_index=row)
