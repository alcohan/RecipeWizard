'''Compact two-row summary of the recipe's current template, with a
click-to-expand flyout for the full item list and any portion overrides.

Row 1: colored swatch + template name + Details button.
Row 2: "N items · $X.XX · M overrides" stats.

Updated by the recipe edit dialog's _refresh() — whenever the recipe's
format changes (via the selector or via undo/redo), refresh() re-reads
the current template, recomputes the stats, and closes any open flyout
so its content can't drift behind the displayed summary.'''
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout,
    QWidget,
)

import db


class TemplateSummaryWidget(QGroupBox):
    '''Group box containing:
      - a colored swatch + template name
      - "N items · $X.XX" stats
      - a "Details" button that opens a flyout popup with the full list

    refresh() is called by the recipe edit dialog whenever the format
    changes (selection or undo/redo). The summary stats update; the
    popup, if open, is closed first so it can't go stale.'''

    def __init__(self, recipe_id, parent=None):
        super().__init__('Template', parent)
        self.recipe_id = recipe_id
        self._popup = None
        # Cache the items/multipliers from the last refresh so opening the
        # popup doesn't have to round-trip to the DB.
        self._cached_tag = None
        self._cached_items = []
        self._cached_mults = []

        # Two rows so the stats (item count + cost) never get clipped by
        # the Details button competing for horizontal space — which used
        # to happen when the panel was narrow. The name row carries just
        # the swatch + template name + button; the stats row gets the
        # full width below.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8)
        outer.setSpacing(4)

        self._swatch = QLabel()
        self._swatch.setFixedSize(12, 12)
        self._name_label = QLabel('')
        self._name_label.setTextFormat(Qt.RichText)
        # Name is short ("Salad" / "Wrap" / etc.) — letting it grow normally
        # is fine. The horizontal layout has the button on the right with
        # no stretch, so width is dominated by the (stable) button width.
        self._name_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._details_btn = QPushButton('Details ▾')
        self._details_btn.setFlat(False)
        self._details_btn.clicked.connect(self._on_details)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(self._swatch, alignment=Qt.AlignVCenter)
        name_row.addWidget(self._name_label, stretch=1)
        name_row.addWidget(self._details_btn)

        self._stats_label = QLabel('')
        # Indent to roughly line up under the name (past the swatch).
        self._stats_label.setStyleSheet('color: #475569; padding-left: 18px;')
        self._stats_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        outer.addLayout(name_row)
        outer.addWidget(self._stats_label)
        outer.addStretch()

        self.refresh()

    def refresh(self):
        '''Re-read the current format + its items. Close any open popup
        first so its data can't drift behind the displayed summary.'''
        self._close_popup()

        tag = db.get_recipe_tag(self.recipe_id)
        self._cached_tag = tag
        if not tag:
            self._cached_items = []
            self._cached_mults = []
            self._swatch.setStyleSheet('background: transparent;')
            self._name_label.setText(
                '<i style="color:#64748b;">No format applied</i>'
            )
            self._stats_label.setText('')
            self._details_btn.setEnabled(False)
            return

        items = db.get_tag_components(tag['id'])
        mults = [
            m for m in db.get_tag_category_multipliers(tag['id'])
            if abs(m['multiplier'] - 1.0) > 1e-9
        ]
        self._cached_items = items
        self._cached_mults = mults

        color = QColor(tag.get('color') or '#64748b')
        if not color.isValid():
            color = QColor('#64748b')
        self._swatch.setStyleSheet(
            f'background: {color.name()}; border-radius: 3px;'
        )

        total_cost = sum(
            float(it.get('UnitCost') or 0) * float(it.get('quantity') or 0)
            for it in items
        )
        self._name_label.setText(f"<b>{tag['name']}</b>")
        # Stats live on their own row so they're always fully visible,
        # regardless of how cramped the Details button makes row 1.
        mult_suffix = (
            f'  ·  {len(mults)} override{"" if len(mults)==1 else "s"}'
            if mults else ''
        )
        self._stats_label.setText(
            f"{len(items)} item{'' if len(items)==1 else 's'}"
            f"  ·  ${total_cost:.2f}{mult_suffix}"
        )
        self._details_btn.setEnabled(bool(items or mults))

    def _on_details(self):
        # Toggle: if a popup is already showing, close it. _close_popup
        # tolerates a stale C++ object from WA_DeleteOnClose so a second
        # button click after a click-outside doesn't blow up.
        if self._popup_is_visible():
            self._close_popup()
            return
        # Stale ref (popup was deleted by Qt.Popup auto-close earlier) —
        # drop it before creating a fresh popup.
        self._popup = None

        popup = _TemplateDetailsPopup(
            self._cached_tag, self._cached_items, self._cached_mults, self,
        )
        # Clear our reference once the C++ object goes away so the next
        # click sees `self._popup is None` and creates a fresh popup.
        popup.destroyed.connect(self._on_popup_destroyed)
        self._popup = popup
        # Position just under the Details button. Qt.Popup auto-dismisses
        # on click-outside.
        anchor = self._details_btn.mapToGlobal(QPoint(0, self._details_btn.height() + 2))
        popup.move(anchor)
        popup.show()

    def _popup_is_visible(self):
        '''True iff self._popup is alive and currently shown. Catches the
        RuntimeError raised when the C++ object behind the Python ref has
        already been deleted (e.g. by Qt.Popup + WA_DeleteOnClose).'''
        if self._popup is None:
            return False
        try:
            return self._popup.isVisible()
        except RuntimeError:
            self._popup = None
            return False

    def _close_popup(self):
        if self._popup is None:
            return
        try:
            self._popup.close()
        except RuntimeError:
            pass
        self._popup = None

    def _on_popup_destroyed(self, *_):
        self._popup = None


class _TemplateDetailsPopup(QWidget):
    '''Flyout shown when the user clicks Details on the summary. Qt.Popup
    window flag makes it dismiss on click-outside, Escape, or focus loss;
    WA_DeleteOnClose drops the C++ object on dismiss so the parent's
    `self._popup` ref goes stale and gets cleared via the destroyed
    signal (see TemplateSummaryWidget._on_popup_destroyed).

    Content: header (swatch + template name) → bulleted item list with
    quantities → optional "── Portion overrides ──" section with any
    non-1.0 category multipliers.'''

    POPUP_WIDTH = 320

    def __init__(self, tag, items, multipliers, parent=None):
        super().__init__(parent)
        # Qt.Popup is the magic flag — without it the widget acts like a
        # normal floating window and doesn't auto-close.
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_DeleteOnClose)

        frame = QFrame(self)
        frame.setObjectName('PopupFrame')
        frame.setStyleSheet(
            '#PopupFrame { background: white; border: 1px solid #cbd5e1;'
            ' border-radius: 4px; }'
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        color = QColor(tag.get('color') or '#64748b')
        if not color.isValid():
            color = QColor('#64748b')
        header = QLabel(
            f'<span style="color:{color.name()};">■</span>  '
            f"<b>{tag['name']}</b> adds:"
        )
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

        items_list = QListWidget()
        items_list.setSelectionMode(QAbstractItemView.NoSelection)
        items_list.setFocusPolicy(Qt.NoFocus)
        items_list.setFrameShape(QFrame.NoFrame)
        items_list.setUniformItemSizes(True)
        if not items:
            empty = QListWidgetItem('  (no items)')
            empty.setFlags(empty.flags() & ~Qt.ItemIsSelectable)
            items_list.addItem(empty)
        else:
            for it in items:
                qty = _fmt_qty(it['quantity'])
                items_list.addItem(f"• {it['Name']} × {qty}")
        layout.addWidget(items_list)

        if multipliers:
            divider = QLabel('── Portion overrides ──')
            divider.setStyleSheet('color:#64748b; font-style: italic;')
            layout.addWidget(divider)
            for m in multipliers:
                layout.addWidget(
                    QLabel(f"  {m['category_name']} × {_fmt_qty(m['multiplier'])}"),
                )

        # Size the flyout enough to comfortably show ~6 list rows plus the
        # header (and any multipliers). Width is a fixed compact value.
        items_list.setMinimumHeight(min(len(items) * 22 + 8, 160))
        self.setFixedWidth(self.POPUP_WIDTH)
        self.adjustSize()


def _fmt_qty(value):
    if value is None:
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{n:.4f}'.rstrip('0').rstrip('.')
