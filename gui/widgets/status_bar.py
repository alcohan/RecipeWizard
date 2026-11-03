'''RecipeWizard's custom status bar.

Replaces Qt's default status bar with a fixed-content strip at the
bottom of the main window: library counts, latest supplier-price
date, last backup, and a compare-tray link on the right.

Each section is a QLabel so the main window can bump its text without
rebuilding anything. refresh() recomputes all three from the DB.
'''

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

import db
from utilities.backup import list_backups


class RecipeWizardStatusBar(QFrame):
    '''Thin band pinned at the bottom of the main window. Content is
    read-only; the right-side "Compare tray" entry is a signal-emitting
    link so the main window can route the click to its place switcher.'''

    compareTrayClicked = Signal()
    updateClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('RecipeWizardStatusBar')
        self.setStyleSheet('''
            QFrame#RecipeWizardStatusBar {
                background: #fffaf2;
                border-top: 1px solid #ebe1cd;
            }
            QFrame#RecipeWizardStatusBar QLabel {
                color: #55624c;
                font-size: 12px;
            }
            QFrame#RecipeWizardStatusBar QLabel[role="link"] {
                color: #ffffff;
                background: #347200;
                padding: 2px 10px;
                border-radius: 4px;
                font-weight: 600;
            }
        ''')
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self._counts_label = QLabel('')
        self._prices_label = QLabel('')
        self._backup_label = QLabel('')
        self._unsaved_label = QLabel('')
        self._unsaved_label.setStyleSheet('color: #8a4a00; font-weight: 600;')
        self._unsaved_label.hide()
        # Tray chip: always visible so the collapsed tray has a home.
        # Click (or Ctrl+Shift+C) flips collapsed ↔ docked.
        self._tray_count = 0
        self._tray_docked = False
        self._tray_label = _TrayChip()
        self._tray_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        self._tray_label.setProperty('role', 'link')
        self._tray_label.setCursor(Qt.PointingHandCursor)
        self._tray_label.setToolTip('Show / hide the compare tray (Ctrl+Shift+C)')
        self._tray_label.mousePressEvent = self._on_tray_click
        # Fixed width (see _TrayChip), centred text: the count and the
        # ▴/▾ change, but the chip never shifts, so collapsing is a click
        # in the same spot that opened the tray.
        self._tray_label.setAlignment(Qt.AlignCenter)
        self._update_tray_chip()
        # Update chip: hidden until a check finds a newer release.
        self._update_label = QLabel('')
        self._update_label.setProperty('role', 'link')
        self._update_label.setCursor(Qt.PointingHandCursor)
        self._update_label.mousePressEvent = lambda _e: self.updateClicked.emit()
        self._update_label.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(18)
        layout.addWidget(self._counts_label)
        layout.addWidget(self._prices_label)
        layout.addWidget(self._backup_label)
        layout.addWidget(self._unsaved_label)
        layout.addStretch()
        layout.addWidget(self._update_label)
        layout.addWidget(self._tray_label)

    def refresh(self):
        '''Rebuild all three left-side sections. Called by the main
        window after any model reset.'''
        try:
            ing_n = db.query('SELECT COUNT(*) AS n FROM Ingredients', one=True)['n']
            rec_n = db.query('SELECT COUNT(*) AS n FROM Recipes', one=True)['n']
        except Exception:
            ing_n = rec_n = 0
        self._counts_label.setText(f'{rec_n} recipes · {ing_n} ingredients')

        prices_as_of = _latest_price_date()
        if prices_as_of:
            # Green dot (●) when the data looks fresh (<30 days old) and
            # amber otherwise. For now treat anything we have as fresh
            # — a staleness threshold can come later.
            dot = '●'
            self._prices_label.setText(
                f'<span style="color: #3E7D3A">{dot}</span> '
                f'Supplier prices as of {prices_as_of}'
            )
            self._prices_label.setTextFormat(Qt.RichText)
        else:
            self._prices_label.setText('No supplier prices yet')

        last_backup = _last_backup_label()
        self._backup_label.setText(last_backup)

    def set_compare_tray_count(self, n):
        '''Called by the compare-tray service when membership changes.'''
        self._tray_count = max(0, n)
        self._update_tray_chip()

    def set_compare_tray_docked(self, docked):
        '''▾ when the docked strip is showing (click collapses it),
        ▴ when collapsed (click docks it).'''
        self._tray_docked = bool(docked)
        self._update_tray_chip()

    def set_unsaved_count(self, n):
        '''Unsaved edits in the current recipe tab; zero hides it.'''
        if n:
            self._unsaved_label.setText(
                f"Unsaved changes · {n} edit{'s' if n != 1 else ''}"
            )
        self._unsaved_label.setVisible(bool(n))

    def set_update(self, release):
        '''Show the "Update available" chip for a utilities.updates.Release;
        None hides it.'''
        if release is not None:
            self._update_label.setText(f'Update available · {release.tag}')
            self._update_label.setToolTip('See what’s new and download it')
        self._update_label.setVisible(release is not None)

    def _update_tray_chip(self):
        arrow = '▾' if self._tray_docked else '▴'
        self._tray_label.setText(f'Compare tray · {self._tray_count} {arrow}')

    def _on_tray_click(self, _event):
        self.compareTrayClicked.emit()


class _TrayChip(QLabel):
    '''Status-bar chip whose width is always that of its widest text,
    measured at layout time with the font and padding it actually has
    (measuring at construction ran before the stylesheet applied).'''

    _WIDEST = 'Compare tray · 999 ▾'
    _PADDING = 2 * 10 + 8   # stylesheet's left+right padding, plus slack

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(self.fontMetrics().horizontalAdvance(self._WIDEST) + self._PADDING)
        return hint

    def minimumSizeHint(self):
        return self.sizeHint()


def _latest_price_date():
    '''Return a human-readable date string ("Oct 14") for the most
    recent ingredient_prices.effective_date, or None when there are
    no prices stored.'''
    try:
        row = db.query(
            'SELECT MAX(effective_date) AS d FROM ingredient_prices',
            one=True,
        )
    except Exception:
        return None
    d = (row or {}).get('d')
    if not d:
        return None
    # effective_date is a sqlite DATE: 'YYYY-MM-DD'. Format compactly.
    from datetime import datetime
    try:
        return datetime.strptime(d, '%Y-%m-%d').strftime('%b %d')
    except ValueError:
        return str(d)


def _last_backup_label():
    '''Pull the most recent backup file timestamp from the user's data
    directory (utilities.backup.list_backups). If none, say so plainly rather than hiding the row.'''
    backups = list_backups()
    newest_mtime = backups[0][1] if backups else 0
    if newest_mtime == 0:
        return 'No backup yet'
    from datetime import datetime, date
    when = datetime.fromtimestamp(newest_mtime)
    if when.date() == date.today():
        return f'Last backup today, {when.strftime("%I:%M %p").lstrip("0")}'
    return f'Last backup {when.strftime("%b %d, %I:%M %p").replace(" 0", " ")}'
