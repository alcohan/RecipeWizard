'''Recipe editor — widget + thin modal-dialog wrapper.

RecipeEditWidget is an embeddable QWidget laid out per the Framework
canvas's editor artboard: an action bar (breadcrumb, unsaved count,
Nutrition label, Price history, Add to compare, Save), a build area
(name, format, yield, menu price, a row of status chips and the
components grid) and a live results column (wedge, cost and food cost,
nutrition, allergens). It's hosted inside the Recipes place as a
document tab.

RecipeEditDialog is a thin QDialog that wraps the widget for callers
that still want modal behavior (currently the Ingredient editor's
"Used in recipes" link, which opens a recipe from inside its own
modal context — tabs wouldn't help).

All mutations push through self.undo_stack so Ctrl+Z reverses them.
QUndoStack.indexChanged drives the refresh that re-reads
RecipesWithNutrition, redraws the wedge, and re-syncs the editable
fields.

Explicit save: each command still writes to the DB as it's pushed
(cost, nutrition and the wedge are computed by SQL views, so live
results need the rows in place), but the undo stack's clean index is
the saved state. Save (Ctrl+S) marks the stack clean; closing with
unsaved edits asks Save / Discard / Cancel, and Discard rewinds the
stack to the clean index, undoing every command since the last save.
The baseline — totals and component quantities at the last save — is
what the "vs saved" figures and "was 3.5" annotations compare against.

UX notes:
- Name / Yield / Unit / Menu price apply on focus-out or Enter, like
  every other edit, and count toward unsaved changes.
- Component quantities are edited inline (double-click or Enter).
  Right-click a component for Edit quantity / Remove. Rows are
  drag-reorderable; template-added rows are locked.
'''
from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtGui import QDoubleValidator, QFont, QKeySequence, QShortcut, QUndoStack
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QTableView, QToolTip, QVBoxLayout, QWidget,
)

import config
import db
from gui.dialogs.archive_confirm import confirm_archive
from gui.dialogs.nutrition_label import NutritionLabelDialog
from gui.dialogs.price_history import PriceHistoryDialog
from gui.dialogs.recipe_component_add import RecipeComponentAddDialog
from gui.models.components_model import RecipeComponentsModel
from gui.undo.recipe_commands import (
    AddComponentCommand, PortionCommand, RemoveComponentCommand, ReorderComponentsCommand,
    SetComponentQtyCommand, SetRecipeImageCommand, SetRecipeStatusCommand, SetRecipeTagCommand,
    SetRecipeTagsCommand, UpdateRecipeInfoCommand,
)
from gui.widgets.component_delegates import (
    ChangedRowDelegate, NameDelegate, QuantityDelegate, ShareDelegate,
)
from gui.widgets.editor_results import EditorResults
from gui.widgets.undo_keys import pass_undo_keys
from gui.widgets.format_segments import FormatSegments
from gui.widgets.template_summary import TemplateSummaryLine
from gui.widgets.wedge_view import WedgeView, recipe_photo
from gui.images import bring_in_photo, choose_photo, is_image_file


WEDGE_SIZE = 200

# Evergreens tokens.
_KALE = '#082c00'
_ROMAINE = '#347200'
_ROMAINE_HOVER = '#285900'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_BG = '#fffaf2'
_MONO = "ui-monospace, 'Cascadia Mono', Consolas, monospace"

_SECONDARY_BTN = f'''
    QPushButton {{
        height: 32px; padding: 0 12px; border: 1px solid {_FIELD_BORDER};
        border-radius: 8px; background: #ffffff; color: {_KALE};
    }}
    QPushButton:hover {{ background: #f3ece0; }}
'''
_PRIMARY_BTN = f'''
    QPushButton {{
        height: 32px; padding: 0 16px; border: 0; border-radius: 8px;
        background: {_ROMAINE}; color: #ffffff; font-weight: 600;
    }}
    QPushButton:hover {{ background: {_ROMAINE_HOVER}; }}
    QPushButton:disabled {{ background: #c9d1bf; color: #f4f1ea; }}
'''
_FIELD = f'''
    QLineEdit {{
        height: 32px; padding: 0 10px; border: 1px solid {_FIELD_BORDER};
        border-radius: 8px; background: #ffffff; color: {_KALE};
    }}
    QLineEdit:focus {{ border: 2px solid {_ROMAINE}; padding: 0 9px; }}
'''


def _eyebrow(text):
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
    return lbl


def _labelled(label, widget):
    col = QVBoxLayout()
    col.setSpacing(4)
    col.addWidget(_eyebrow(label))
    col.addWidget(widget)
    return col


class _Chip(QLabel):
    '''Rounded status pill under the recipe fields. `tone` is
    'positive' (romaine on green), 'warn' (amber) or 'neutral'
    (outlined).'''

    clicked = Signal()

    _TONES = {
        'positive': f'background: #e9f1d9; color: {_ROMAINE}; font-weight: 600; border: 0;',
        'warn': 'background: #fff0dc; color: #8a4a00; font-weight: 600; border: 0;',
        'neutral': f'background: #ffffff; color: {_MUTED}; border: 1px solid {_FIELD_BORDER};',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._clickable = False

    def configure(self, text, tone='neutral', tooltip='', clickable=False):
        self.setText(text)
        self.setToolTip(tooltip)
        self._clickable = clickable
        self.setCursor(Qt.PointingHandCursor if clickable else Qt.ArrowCursor)
        # Radius at most half the height, or Qt draws square corners.
        self.setStyleSheet(f'QLabel {{ {self._TONES[tone]} border-radius: 9px;'
                           ' padding: 2px 10px; font-size: 12px; }')

    def mousePressEvent(self, event):
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(event)


class RecipeEditWidget(QWidget):
    '''Embeddable recipe editor. The container (EditorTabs or
    RecipeEditDialog) owns window chrome and the close flow; this
    widget emits signals for the title / modified state / delete and
    exposes close_requested() so the container can flush pending edits
    and stamp the cost snapshot before tearing down.'''

    titleChanged = Signal(str)       # recipe's current name — tab/window title
    recipeDeleted = Signal(int)      # recipe_id, fired after confirm + DB delete
    modifiedChanged = Signal(bool)   # true while there are unsaved edits
    dirtyCountChanged = Signal(int)  # number of edits since the last save
    saved = Signal(int)              # recipe_id, after Save
    libraryRequested = Signal()      # breadcrumb "Library" clicked
    openRecipeRequested = Signal(int)  # "Used in …" chip picked a parent recipe

    def __init__(self, recipe_id, compare_tray=None, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self.modified = False
        self.status_message = ''
        self._being_deleted = False
        self._compare_tray = compare_tray

        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._refresh)
        # Dirty-flag tracking lives on the undo stack rather than inside
        # _refresh — _refresh also runs on construction, when the widget
        # isn't modified yet. cleanChanged(False) fires on the first
        # push; cleanChanged(True) fires again if an undo returns to
        # the saved baseline.
        self.undo_stack.cleanChanged.connect(self._on_clean_changed)
        self.undo_stack.indexChanged.connect(self._on_index_changed)

        # Bring the recipe in line with its current format's template
        # before reading anything else — fixes sample-seeded recipes
        # that were tagged but missed some template items, and recipes
        # whose template was edited after they were tagged. Silent /
        # not on the undo stack: this reconciles latent data drift,
        # not a user action.
        db.reconcile_recipe_template(recipe_id)

        recipe = db.recipe_info(recipe_id)
        self._title = recipe['Name']
        self._recipe_snapshot = self._snapshot(recipe)

        self.components_model = RecipeComponentsModel(recipe_id)
        self.components_model.qtyEdited.connect(self._on_qty_edited)
        self.components_model.rowsReordered.connect(self._on_components_reordered)
        self._capture_baseline(recipe)

        action_bar = self._build_action_bar()
        build = self._build_build_area(recipe)
        self.wedge = WedgeView(self.recipe_id, size=WEDGE_SIZE)
        self.results = EditorResults(self._build_photo_box())
        self.results.fullLabelRequested.connect(self._on_nutrition_label)

        build_scroll = QScrollArea()
        build_scroll.setWidget(build)
        build_scroll.setWidgetResizable(True)
        build_scroll.setFrameShape(QFrame.NoFrame)
        results_scroll = QScrollArea()
        results_scroll.setWidget(self.results)
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.NoFrame)
        results_scroll.setMinimumWidth(320)
        results_scroll.setStyleSheet(f'QScrollArea {{ border-left: 1px solid {_BORDER};'
                                     ' background: #ffffff; }')

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(build_scroll)
        self.splitter.addWidget(results_scroll)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([900, 380])

        # Undo/Redo actions — keyboard shortcuts only, no toolbar buttons.
        # Window-wide, so they work wherever focus is (the header, the tab
        # bar); Qt skips shortcuts on hidden widgets, so with several
        # recipe tabs open only the visible one's stack answers. The text
        # fields pass the keys on unless an edit is being typed there.
        undo_action = self.undo_stack.createUndoAction(self, 'Undo')
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setShortcutContext(Qt.WindowShortcut)
        redo_action = self.undo_stack.createRedoAction(self, 'Redo')
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.setShortcutContext(Qt.WindowShortcut)
        self.addAction(undo_action)
        self.addAction(redo_action)

        self.setObjectName('RecipeEditWidget')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f'QWidget#RecipeEditWidget {{ background: {_BG}; }}')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(action_bar)
        layout.addWidget(self.splitter, stretch=1)

        # Restore splitter ratios from the previous session if we have
        # them. Written back from close_requested() below. New key: the
        # layout changed, so the old two-column ratios don't apply.
        state = QSettings().value('recipeEditor/splitter2')
        if state is not None:
            self.splitter.restoreState(state)

        if self._compare_tray is not None:
            self._compare_tray.changed.connect(self._sync_compare_button)
        self._sync_compare_button()
        self._refresh()

    # --- container-facing API ------------------------------------------

    def title(self):
        return self._title

    def dirty_count(self):
        '''Edits since the last save (or since opening). An undo past
        the saved point counts too — it's still a change to save.'''
        clean = self.undo_stack.cleanIndex()
        index = self.undo_stack.index()
        return index if clean < 0 else abs(index - clean)

    def save(self):
        '''Make the current state the saved state: flush any in-flight
        field edit, stamp the cost snapshot, mark the stack clean and
        move the "vs saved" baseline here.'''
        if self._being_deleted:
            return
        self._maybe_commit_info()
        try:
            db.update_recipe_cost_snapshot(self.recipe_id)
        except Exception:
            pass
        self.undo_stack.setClean()
        self._capture_baseline(db.recipe_info(self.recipe_id))
        self.status_message = f"Saved '{self._title}'"
        self.saved.emit(self.recipe_id)
        self._refresh()

    def discard(self):
        '''Rewind every edit since the last save.'''
        clean = self.undo_stack.cleanIndex()
        if clean >= 0:
            self.undo_stack.setIndex(clean)

    def close_requested(self):
        '''Called by the container (tab bar or modal wrapper) when this
        widget is about to go away. Flushes any pending field edit and,
        if there are unsaved edits, asks Save / Discard / Cancel. Then
        stamps the cost snapshot and saves the splitter state. Returns
        False if the user cancelled.'''
        if self._being_deleted:
            # Row's gone — skip _maybe_commit_info (it would push a
            # bogus UpdateRecipeInfoCommand against the vanished id)
            # and skip the snapshot stamp.
            QSettings().setValue('recipeEditor/splitter2', self.splitter.saveState())
            return True
        self._maybe_commit_info()
        if self.modified:
            n = self.dirty_count()
            answer = QMessageBox.question(
                self, 'Unsaved changes',
                f"Save {n} change{'s' if n != 1 else ''} to '{self._title}'?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if answer == QMessageBox.Cancel:
                return False
            if answer == QMessageBox.Save:
                self.save()
            else:
                self.discard()
        try:
            db.update_recipe_cost_snapshot(self.recipe_id)
        except Exception:
            # A failure here is a UX nicety, not correctness —
            # swallow so a flaky DB doesn't block closing.
            pass
        QSettings().setValue('recipeEditor/splitter2', self.splitter.saveState())
        return True

    def mark_deleted(self):
        '''Called by the container when the recipe was deleted from
        outside this widget (e.g. the library's row context menu).
        Suppresses further DB reads from _refresh and the stale-id
        UPDATE paths in close_requested, so the container can safely
        tear the tab down.'''
        self._being_deleted = True
        # Any undo-stack entries now point at a gone row; drop them so
        # a stray Ctrl+Z before deleteLater() doesn't UPDATE nothing.
        self.undo_stack.clear()

    # Public entry points for the main window's Recipe menu.
    def add_component(self):
        self._on_add_component()

    def show_nutrition_label(self):
        self._on_nutrition_label()

    def show_price_history(self):
        self._on_price_history()

    def delete_recipe(self):
        self._on_delete()

    # --- layout builders -----------------------------------------------

    def _build_action_bar(self):
        bar = QFrame()
        bar.setObjectName('EditorActionBar')
        bar.setStyleSheet(f'QFrame#EditorActionBar {{ background: #ffffff;'
                          f' border-bottom: 1px solid {_BORDER}; }}')

        self.breadcrumb = QLabel('')
        self.breadcrumb.setTextFormat(Qt.RichText)
        self.breadcrumb.setStyleSheet(f'color: {_MUTED}; font-size: 13px;')
        self.breadcrumb.linkActivated.connect(lambda _h: self.libraryRequested.emit())
        self.unsaved_label = QLabel('')
        self.unsaved_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')

        self.archive_btn = QPushButton('Archive')
        self.archive_btn.clicked.connect(self.toggle_archived)
        label_btn = QPushButton('Nutrition label')
        label_btn.clicked.connect(self._on_nutrition_label)
        history_btn = QPushButton('Price history')
        history_btn.clicked.connect(self._on_price_history)
        print_btn = QPushButton('Print')
        print_btn.setToolTip('Print this recipe’s page (Ctrl+P)')
        print_btn.clicked.connect(self.print_recipe)
        self.compare_btn = QPushButton('')
        self.compare_btn.clicked.connect(self._toggle_compare)
        self.compare_btn.setVisible(self._compare_tray is not None)
        for btn in (self.archive_btn, label_btn, history_btn, print_btn, self.compare_btn):
            btn.setStyleSheet(_SECONDARY_BTN)
            btn.setAutoDefault(False)
        self.save_btn = QPushButton('Save   Ctrl+S')
        self.save_btn.setStyleSheet(_PRIMARY_BTN)
        self.save_btn.setEnabled(False)
        self.save_btn.setAutoDefault(False)
        self.save_btn.clicked.connect(self.save)

        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 8, 20, 8)
        row.setSpacing(8)
        row.addWidget(self.breadcrumb)
        row.addWidget(self.unsaved_label)
        row.addStretch()
        row.addWidget(self.archive_btn)
        row.addWidget(label_btn)
        row.addWidget(history_btn)
        row.addWidget(print_btn)
        row.addWidget(self.compare_btn)
        row.addWidget(self.save_btn)
        return bar

    def _build_build_area(self, recipe):
        area = QWidget()
        area.setObjectName('EditorBuild')
        area.setAttribute(Qt.WA_StyledBackground, True)
        area.setStyleSheet(f'QWidget#EditorBuild {{ background: {_BG}; }}' + _FIELD)

        # Name — the one display-face moment on the screen.
        self.name_edit = QLineEdit(recipe['Name'])
        name_font = QFont()
        name_font.setFamilies(['Gooper Semicondensed', 'Fraunces', 'Georgia', 'serif'])
        name_font.setPixelSize(30)
        name_font.setBold(True)
        self.name_edit.setFont(name_font)
        self.name_edit.setStyleSheet(
            f'QLineEdit {{ border: 0; border-bottom: 1px dashed {_FIELD_BORDER};'
            f' background: transparent; color: {_KALE}; padding: 0 0 2px; height: auto; }}'
            f' QLineEdit:focus {{ border-bottom: 2px solid {_ROMAINE}; }}'
        )
        self.name_edit.editingFinished.connect(self._maybe_commit_info)

        self.format_segments = FormatSegments()
        self.format_segments.selectionChanged.connect(self._on_tag_changed)

        self.yield_edit = QLineEdit(_format_qty(recipe['OutputQty']))
        self.yield_edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
        self.yield_edit.setFixedWidth(64)
        self.yield_edit.setAlignment(Qt.AlignRight)
        self.yield_edit.editingFinished.connect(self._maybe_commit_info)
        self.unit_edit = QLineEdit(recipe['Unit'])
        self.unit_edit.setFixedWidth(96)
        self.unit_edit.setPlaceholderText('unit')
        self.unit_edit.editingFinished.connect(self._maybe_commit_info)
        yield_row = QHBoxLayout()
        yield_row.setSpacing(6)
        yield_row.addWidget(self.yield_edit)
        yield_row.addWidget(self.unit_edit)
        yield_box = QWidget()
        yield_box.setLayout(yield_row)
        yield_row.setContentsMargins(0, 0, 0, 0)

        # Blank is meaningful: "not on the menu / no food-cost %". We parse
        # that in _maybe_commit_info rather than relying on a validator that
        # would reject empty.
        self.menu_price_edit = QLineEdit(_format_menu_price(recipe.get('MenuPrice')))
        self.menu_price_edit.setPlaceholderText('Not on menu')
        self.menu_price_edit.setFixedWidth(110)
        self.menu_price_edit.editingFinished.connect(self._maybe_commit_info)

        # Each field's last committed text: Ctrl+Z goes to the recipe's
        # undo stack unless the field holds an uncommitted edit.
        self._committed_text = {e: e.text() for e in (self.name_edit, self.yield_edit, self.unit_edit,
                                                       self.menu_price_edit)}
        for edit in self._committed_text:
            pass_undo_keys(edit, self._field_has_pending_edit)

        name_col = _labelled('Recipe', self.name_edit)
        fields = QHBoxLayout()
        fields.setSpacing(28)
        fields.addLayout(name_col, stretch=1)
        fields.addLayout(_labelled('Format', self.format_segments))
        fields.addLayout(_labelled('Yield', yield_box))
        fields.addLayout(_labelled('Menu price', self.menu_price_edit))
        for col in (fields.itemAt(i).layout() for i in range(1, 4)):
            col.setAlignment(Qt.AlignBottom)

        # Recipe tags (Core, Seasonal…): toggle pills, then the status
        # chips: on the menu, used in N recipes, prices changed.
        self._tag_pills = {}
        self._tag_row = QHBoxLayout()
        self._tag_row.setSpacing(6)
        self.menu_chip = _Chip()
        self.menu_chip.clicked.connect(self.toggle_archived)
        self.used_in_chip = _Chip()
        self.used_in_chip.clicked.connect(self._show_used_in_menu)
        self.prices_chip = _Chip()
        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addLayout(self._tag_row)
        self._tag_divider = QFrame()
        self._tag_divider.setFixedSize(1, 18)
        self._tag_divider.setStyleSheet(f'background: {_BORDER};')
        chips.addWidget(self._tag_divider)
        chips.addWidget(self.menu_chip)
        chips.addWidget(self.used_in_chip)
        chips.addWidget(self.prices_chip)
        chips.addStretch()

        layout = QVBoxLayout(area)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addLayout(fields)
        layout.addLayout(chips)
        # The card sizes to its rows (the table shows them all); spare
        # height goes below it, and the area scrolls when it runs out.
        layout.addWidget(self._build_components_card())
        layout.addStretch(1)
        return area

    def _build_photo_box(self):
        '''The wedge (or the recipe's photo) with "Add photo" /
        "Change · Remove" under it. An image file dropped on it sets the
        photo too. Photo changes go on the undo stack like any edit.'''
        box = _PhotoDropBox(self._on_photo_dropped)
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        col.addWidget(self.wedge, alignment=Qt.AlignHCenter)
        self.photo_links = QLabel('')
        self.photo_links.setTextFormat(Qt.RichText)
        self.photo_links.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.photo_links.linkActivated.connect(self._on_photo_link)
        col.addWidget(self.photo_links, alignment=Qt.AlignHCenter)
        self._sync_photo_links()
        return box

    def _sync_photo_links(self):
        link = f'color: {_ROMAINE}; text-decoration: none'
        if recipe_photo(self.recipe_id):
            self.photo_links.setText(f'<a href="change" style="{link}">Change photo</a>'
                                     f' &nbsp;·&nbsp; <a href="remove" style="{link}">Remove</a>')
            self.photo_links.setToolTip('The photo shows in place of the wedge everywhere.')
        else:
            self.photo_links.setText(f'<a href="change" style="{link}">Add photo</a>')
            self.photo_links.setToolTip('A photo shows in place of the wedge everywhere,'
                                        ' printed pages included. You can also drop an image here.')

    def _on_photo_link(self, href):
        if href == 'remove':
            self._set_recipe_photo('')
            return
        name = choose_photo(self, config.RECIPE_IMAGES_PATH, 'Choose a recipe photo')
        if name:
            self._set_recipe_photo(name)

    def _on_photo_dropped(self, path):
        name = bring_in_photo(self, path, config.RECIPE_IMAGES_PATH)
        if name:
            self._set_recipe_photo(name)

    def _set_recipe_photo(self, name):
        before = db.get_recipe_image(self.recipe_id)
        if (before or '') == (name or ''):
            # Same filename, maybe a replaced file: just redraw.
            self.wedge.refresh()
            return
        self.undo_stack.push(SetRecipeImageCommand(self.recipe_id, before, name))

    def _build_components_card(self):
        card = QFrame()
        card.setObjectName('ComponentsCard')
        card.setStyleSheet(f'QFrame#ComponentsCard {{ background: #ffffff;'
                           f' border: 1px solid {_BORDER}; border-radius: 8px; }}')

        title = QLabel('Components')
        title.setStyleSheet(f'color: {_KALE}; font-size: 16px; font-weight: 600;')
        self.components_summary = QLabel('')
        self.components_summary.setStyleSheet(f'color: {_MUTED};')
        order_hint = QLabel('Drag to reorder')
        order_hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        head = QHBoxLayout()
        head.setContentsMargins(16, 12, 16, 12)
        head.setSpacing(12)
        head.addWidget(title)
        head.addWidget(self.components_summary)
        head.addStretch()
        head.addWidget(order_hint)

        table = QTableView()
        self.components_table = table
        table.setModel(self.components_model)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        # Drag-reorder rows. The model returns False from dropMimeData
        # for no-op moves and the actual SortOrder update goes through
        # the undo stack (see _on_components_reordered).
        table.setDragEnabled(True)
        table.setAcceptDrops(True)
        table.setDropIndicatorShown(True)
        table.setDragDropMode(QAbstractItemView.InternalMove)
        table.setDefaultDropAction(Qt.MoveAction)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.NoFrame)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.setSizeAdjustPolicy(QAbstractItemView.AdjustToContents)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        table.setStyleSheet(f'''
            QTableView {{
                background: #ffffff; border: 0; color: {_KALE};
                selection-background-color: #e9f1d9; selection-color: {_KALE};
            }}
            QTableView::item {{ border-top: 1px solid #f3ece0; padding: 0 8px; }}
            QHeaderView::section {{
                background: #ffffff; color: {_MUTED}; border: 0;
                border-top: 1px solid {_BORDER};
                padding: 6px 8px; font-size: 11px; font-weight: 600;
            }}
        ''')

        cols = self.components_model.COLUMNS
        changed = ChangedRowDelegate(table)
        for name in cols:
            table.setItemDelegateForColumn(cols.index(name), changed)
        table.setItemDelegateForColumn(cols.index('Name'), NameDelegate(table))
        table.setItemDelegateForColumn(cols.index('Quantity'), QuantityDelegate(table))
        table.setItemDelegateForColumn(cols.index('Share'), ShareDelegate(table))
        header = table.horizontalHeader()
        header.setSectionResizeMode(cols.index('Name'), QHeaderView.Stretch)
        for name, width in (('Quantity', 72), ('Unit', 90), ('Cost', 76),
                            ('Share', 120), ('Calories', 64), ('Allergens', 140)):
            header.setSectionResizeMode(cols.index(name), QHeaderView.Interactive)
            table.setColumnWidth(cols.index(name), width)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        table.activated.connect(self._on_component_activated)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_components_context_menu)
        self.components_model.modelReset.connect(self._fit_table_height)

        # The format's template: its auto-add items (packaging among
        # them — hidden from the grid and wedge but still in the cost),
        # portion overrides, and a Details flyout listing both.
        self.template_line = TemplateSummaryLine(self.recipe_id)

        add_row = QPushButton()
        add_row.setCursor(Qt.PointingHandCursor)
        add_row.setStyleSheet(f'''
            QPushButton {{
                text-align: left; padding: 10px 16px; border: 0;
                border-top: 1px solid {_BORDER}; background: {_BG};
                border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;
            }}
            QPushButton:hover {{ background: #fff1da; }}
        ''')
        add_label = QLabel(f'<span style="color: {_ROMAINE}; font-size: 16px">+</span>&nbsp;&nbsp;'
                           f'<b style="color: {_ROMAINE}">Add component</b>'
                           f'<span style="color: {_MUTED}"> — ingredient or sub-recipe</span>')
        add_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        add_kbd = QLabel('Ctrl+Enter')
        add_kbd.setStyleSheet(f'color: {_MUTED}; font-family: {_MONO}; font-size: 12px;')
        add_kbd.setAttribute(Qt.WA_TransparentForMouseEvents)
        add_inner = QHBoxLayout(add_row)
        add_inner.setContentsMargins(16, 8, 16, 8)
        add_inner.addWidget(add_label)
        add_inner.addStretch()
        add_inner.addWidget(add_kbd)
        add_row.setMinimumHeight(40)
        add_row.clicked.connect(self._on_add_component)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(table)
        layout.addWidget(self.template_line)
        layout.addWidget(add_row)
        return card

    def _fit_table_height(self):
        '''The grid shows every row; the build area scrolls instead.'''
        t = self.components_table
        rows = self.components_model.rowCount()
        h = t.horizontalHeader().height() + rows * t.verticalHeader().defaultSectionSize() + 2
        t.setFixedHeight(h)

    # --- helpers -------------------------------------------------------

    def _snapshot(self, recipe):
        return (
            recipe['Name'], recipe['Unit'], float(recipe['OutputQty']),
            _coerce_menu_price(recipe.get('MenuPrice')),
        )

    def _capture_baseline(self, recipe):
        '''Totals and component quantities as of the last save (or
        opening) — what "vs saved" and "was" compare against.'''
        self._baseline = dict(recipe)
        self.components_model.set_baseline(self.components_model.quantities())

    def _refresh(self):
        '''Re-read recipe state from DB and update every dependent view.
        Fires on every QUndoStack.indexChanged plus on widget construction.
        Dirty-flag tracking is NOT done here (see _on_clean_changed);
        construction fires _refresh too, and the widget isn't modified then.'''
        if self._being_deleted:
            # The recipe row is gone; don't re-read it. Any undo-stack
            # tick that lands here after mark_deleted() is a no-op.
            return
        recipe = db.recipe_info(self.recipe_id)
        self._recipe_snapshot = self._snapshot(recipe)

        self.components_model.refresh()
        try:
            total = float(recipe.get('CostRaw') or 0) * float(recipe.get('OutputQty') or 0)
        except (TypeError, ValueError):
            total = 0.0
        self.components_model.set_total_cost(total)
        self._fit_table_height()

        rows = [self.components_model.row_dict(i) for i in range(self.components_model.rowCount())]
        n_sub = sum(1 for r in rows if r['Type'] == 'recipe')
        n_ing = len(rows) - n_sub
        summary = f"{n_ing} ingredient{'s' if n_ing != 1 else ''}"
        if n_sub:
            summary += f" · {n_sub} sub-recipe{'s' if n_sub != 1 else ''}"
        self.components_summary.setText(summary)
        self.template_line.refresh(unlisted_cost=total - self.components_model.visible_cost())

        current_tag = db.get_recipe_tag(self.recipe_id)
        self.format_segments.set_selected(current_tag['id'] if current_tag else None)
        crumb_mid = f" › {current_tag['name']}" if current_tag else ''
        self.breadcrumb.setText(
            f'<a href="library" style="color: {_ROMAINE}; text-decoration: none">Library</a>'
            f'{crumb_mid} › <b style="color: {_KALE}">{_html_escape(recipe["Name"])}</b>'
        )

        self._refresh_tag_pills()
        self._refresh_chips(recipe)
        self.results.update_results(
            recipe, self._baseline, db.get_recipe_allergen_sources(self.recipe_id),
            db.get_recipe_allergen_sources(self.recipe_id, facility=True))
        self.wedge.refresh()
        if hasattr(self, 'photo_links'):
            self._sync_photo_links()

        # Sync editable fields. A field holding an edit the user hasn't
        # committed yet is left alone — otherwise typing in one field while
        # another commits would clobber it. A focused field with nothing
        # pending does update, so an undo shows in the field you're in.
        for edit, value in (
            (self.name_edit, recipe['Name']),
            (self.unit_edit, recipe['Unit']),
            (self.yield_edit, _format_qty(recipe['OutputQty'])),
            (self.menu_price_edit, _format_menu_price(recipe.get('MenuPrice'))),
        ):
            if edit.text() == value:
                self._committed_text[edit] = value   # e.g. the edit just committed
                continue
            if edit.hasFocus() and self._field_has_pending_edit(edit):
                continue
            edit.blockSignals(True)
            edit.setText(value)
            edit.blockSignals(False)
            self._committed_text[edit] = value

        if recipe['Name'] != self._title:
            self._title = recipe['Name']
            self.titleChanged.emit(self._title)

    def showEvent(self, event):
        '''Coming back to this tab (from Configure, say): pick up recipe
        tags and formats added or renamed while it was hidden.'''
        super().showEvent(event)
        if not self._being_deleted and hasattr(self, '_tag_row'):
            self.format_segments.reload()
            self._refresh_tag_pills()

    def _refresh_tag_pills(self):
        '''One toggle pill per recipe tag, checked when this recipe has
        it. Rebuilt only when the set of tags changes (Configure).'''
        tags = db.get_tags('recipe_tag')
        key = [(t['id'], t['name'], t.get('color')) for t in tags]
        if key != getattr(self, '_tag_key', None):
            self._tag_key = key
            while self._tag_row.count():
                item = self._tag_row.takeAt(0)
                if item.widget() is not None:
                    item.widget().deleteLater()
            self._tag_pills = {}
            for tid, name, color in key:
                pill = QPushButton(name)
                pill.setCheckable(True)
                pill.setCursor(Qt.PointingHandCursor)
                pill.setToolTip(f'Tag this recipe {name}. Manage tags in Configure › Recipe tags.')
                dot = color or _MUTED
                pill.setStyleSheet(
                    f'QPushButton {{ border: 1px dashed {_FIELD_BORDER}; border-radius: 10px; padding: 1px 10px;'
                    f' background: transparent; color: {_MUTED}; font-size: 12px; }}'
                    f' QPushButton:hover {{ border-style: solid; }}'
                    f' QPushButton:checked {{ border: 1px solid {dot}; background: #ffffff; color: {_KALE};'
                    ' font-weight: 600; }')
                pill.toggled.connect(lambda on, t=tid, n=name: self._on_recipe_tag_toggled(t, n, on))
                self._tag_row.addWidget(pill)
                self._tag_pills[tid] = pill
            self._tag_divider.setVisible(bool(key))
        have = db.get_recipe_tags(self.recipe_id)
        for tid, pill in self._tag_pills.items():
            pill.blockSignals(True)
            pill.setChecked(tid in have)
            pill.blockSignals(False)

    def _on_recipe_tag_toggled(self, tag_id, name, on):
        before = db.get_recipe_tags(self.recipe_id)
        after = before | {tag_id} if on else before - {tag_id}
        if after != before:
            self.undo_stack.push(SetRecipeTagsCommand(
                self.recipe_id, before, after, f"{'Tag' if on else 'Untag'} {name}"))

    def _refresh_chips(self, recipe):
        self._archived = recipe.get('Status') == 'archived'
        self.archive_btn.setText('Restore to menu' if self._archived else 'Archive')
        self.archive_btn.setToolTip('Put it back on the menu' if self._archived else
                                    'Take it off the menu: hidden from the Library and analytics, kept for later')
        if self._archived:
            self.menu_chip.configure('Archived · off the menu', 'neutral',
                                     'Hidden from the Library and analytics. Click to restore it.',
                                     clickable=True)
        elif _coerce_menu_price(recipe.get('MenuPrice')):
            self.menu_chip.configure('On the menu', 'positive',
                                     'Click to archive it (take it off the menu).', clickable=True)
        else:
            self.menu_chip.configure('On the menu · no price', 'neutral',
                                     'Set a menu price to see its food cost. Click to archive it'
                                     ' (take it off the menu).', clickable=True)

        self._parents = db.get_parent_recipes(self.recipe_id)
        n = len(self._parents)
        if n:
            names = ', '.join(p['Name'] + (' (archived)' if p.get('Status') == 'archived' else '')
                              for p in self._parents)
            self.used_in_chip.configure(
                f"Used in {n} recipe{'s' if n != 1 else ''}", 'neutral',
                f'Used as a sub-recipe in {names}. Click to open one.', clickable=True)
        self.used_in_chip.setVisible(bool(n))

        # Prices moved since the last save (not caused by this session's
        # edits — the snapshot is stamped at save).
        try:
            snap = recipe.get('CostSnapshot')
            drift = float(self._baseline.get('CostRaw') or 0) - float(snap) if snap is not None else 0
        except (TypeError, ValueError):
            drift = 0
        if abs(drift) >= 0.01:
            sign = '+' if drift > 0 else '−'
            self.prices_chip.configure(
                f'Prices changed {sign}${abs(drift):.2f} since last save', 'warn',
                'Supplier prices moved since this recipe was last saved. Save to confirm the new cost.')
        self.prices_chip.setVisible(abs(drift) >= 0.01)

    def toggle_archived(self):
        '''Archive or restore this recipe — an edit in this tab, so it
        counts as unsaved and Discard puts it back.'''
        if self._being_deleted:
            return
        before = 'archived' if self._archived else 'active'
        after = 'active' if self._archived else 'archived'
        if after == 'archived' and not confirm_archive(self, self.recipe_id, self._title):
            return
        self.undo_stack.push(SetRecipeStatusCommand(self.recipe_id, before, after, self._title))

    def refresh_status(self):
        '''The Library archived or restored this recipe.'''
        if not self._being_deleted:
            self._refresh_chips(db.recipe_info(self.recipe_id))

    def _sync_compare_button(self):
        if self._compare_tray is None:
            return
        inside = self._compare_tray.contains(self.recipe_id)
        self.compare_btn.setText('In compare ✓   Space' if inside else 'Add to compare   Space')
        self.compare_btn.setToolTip('Remove from the compare tray' if inside
                                    else 'Add to the compare tray')

    # --- handlers ------------------------------------------------------

    def _on_clean_changed(self, is_clean):
        '''undo_stack.cleanChanged — flips when the stack is either
        pushed-off or undone-back-to the clean baseline. Mirror to
        self.modified so the container can wire a dirty-dot off this
        signal without seeing a false positive on construction.'''
        was_modified = self.modified
        self.modified = not is_clean
        if self.modified != was_modified:
            self.modifiedChanged.emit(self.modified)
        self.save_btn.setEnabled(self.modified)
        # Save marks the stack clean without moving its index, so
        # indexChanged doesn't fire: refresh "N unsaved changes" here.
        self._on_index_changed(self.undo_stack.index())

    def _on_index_changed(self, _index):
        n = self.dirty_count()
        self.unsaved_label.setText(
            f"· {n} unsaved change{'s' if n != 1 else ''}" if n else ''
        )
        self.dirtyCountChanged.emit(n)

    def _toggle_compare(self):
        if self._compare_tray is not None:
            self._compare_tray.toggle(self.recipe_id)

    def _show_used_in_menu(self):
        if not self._parents:
            return
        menu = QMenu(self)
        for p in self._parents:
            action = menu.addAction(p['Name'] + ('  · archived' if p.get('Status') == 'archived' else ''))
            action.triggered.connect(lambda _c=False, rid=p['Id']: self.openRecipeRequested.emit(rid))
        menu.exec(self.used_in_chip.mapToGlobal(self.used_in_chip.rect().bottomLeft()))

    def _field_has_pending_edit(self, edit):
        committed = getattr(self, '_committed_text', {})
        return edit in committed and edit.text() != committed[edit]

    def _maybe_commit_info(self):
        '''Apply the recipe fields. Wired to each input's editingFinished
        signal and called explicitly from save() / close_requested() so
        an in-flight edit isn't lost.'''
        name = self.name_edit.text().strip()
        if not name:
            # Refuse the empty-name commit; restore the previous value.
            self.name_edit.blockSignals(True)
            self.name_edit.setText(self._recipe_snapshot[0])
            self.name_edit.blockSignals(False)
            return
        unit = self.unit_edit.text()
        try:
            yield_qty = float(self.yield_edit.text() or 0)
        except ValueError:
            self.yield_edit.blockSignals(True)
            self.yield_edit.setText(_format_qty(self._recipe_snapshot[2]))
            self.yield_edit.blockSignals(False)
            return
        try:
            menu_price = _parse_menu_price(self.menu_price_edit.text())
        except ValueError:
            # Restore last-committed value so a bogus edit doesn't commit.
            self.menu_price_edit.blockSignals(True)
            self.menu_price_edit.setText(_format_menu_price(self._recipe_snapshot[3]))
            self.menu_price_edit.blockSignals(False)
            return
        after = (name, unit, yield_qty, menu_price)
        if after == self._recipe_snapshot:
            # Same values, maybe typed differently ("1.0" for "1"): the
            # field's text is what's committed now.
            for edit in self._committed_text:
                self._committed_text[edit] = edit.text()
            return
        self.undo_stack.push(UpdateRecipeInfoCommand(self.recipe_id, self._recipe_snapshot, after))

    def _on_tag_changed(self, new_tag_id, prev_tag_id):
        if new_tag_id == prev_tag_id:
            return
        label = 'Clear format' if new_tag_id is None else 'Set format'
        self.undo_stack.push(SetRecipeTagCommand(
            self.recipe_id, prev_tag_id, new_tag_id, label,
        ))

    def _on_add_component(self):
        '''Opens the picker; each Add pushes its own undoable command,
        so "keep open to add another" adds several in one visit.'''
        def push(child_id, mode, qty, name):
            self.undo_stack.push(AddComponentCommand(self.recipe_id, mode, child_id, qty, name))

        RecipeComponentAddDialog(
            self.recipe_id, self.name_edit.text(), parent=self, on_add=push,
        ).exec()

    def _on_component_activated(self, view_index):
        '''Double-click or Enter on a row — open the inline Quantity editor.'''
        if not view_index.isValid():
            return
        qty_col = self.components_model.COLUMNS.index('Quantity')
        qty_index = self.components_model.index(view_index.row(), qty_col)
        self.components_table.setCurrentIndex(qty_index)
        row_dict = self.components_model.row_dict(view_index.row())
        if row_dict.get('FromTemplateTagId') is None and not self.components_model.qty_editable(view_index.row()):
            # The format's rule sets this quantity; say how to change it.
            rect = self.components_table.visualRect(qty_index)
            QToolTip.showText(self.components_table.viewport().mapToGlobal(rect.bottomLeft()),
                              self.components_model.portion_tooltip(row_dict), self.components_table)
            return
        self.components_table.edit(qty_index)

    def _on_qty_edited(self, row, new_qty):
        '''The components model emitted qtyEdited because the user finished
        an inline edit. Push a SetComponentQtyCommand so the change is
        undoable.'''
        row_dict = self.components_model.row_dict(row)
        try:
            old_qty = float(row_dict.get('QuantityRaw', 0) or 0)
        except (TypeError, ValueError):
            old_qty = 0.0
        if new_qty == old_qty:
            return
        portion = row_dict.get('Portion')
        if portion and portion['state'] == 'base' and portion['siblings'] >= 2:
            # A shared base keeps its total: the typed amount becomes this
            # row's share and the others split the rest.
            problem = db.base_quantity_problem(self.recipe_id, row_dict['Id'], new_qty)
            if problem:
                QMessageBox.information(self, 'Shared base', f'{problem} Use Size by hand to set it freely.')
                self.components_model.refresh()
                return
            self.undo_stack.push(PortionCommand(
                self.recipe_id, f"Change {row_dict['Name']} share",
                lambda rid=self.recipe_id, iid=row_dict['Id'], q=new_qty: db.set_base_quantity(rid, iid, q)))
            return
        self.undo_stack.push(SetComponentQtyCommand(
            self.recipe_id, row_dict['Type'], row_dict['Id'],
            old_qty, new_qty, row_dict['Name'],
        ))

    def _show_components_context_menu(self, point):
        index = self.components_table.indexAt(point)
        if not index.isValid():
            return
        row_dict = self.components_model.row_dict(index.row())
        is_template = row_dict.get('FromTemplateTagId') is not None
        menu = QMenu(self.components_table)
        edit_action = menu.addAction('Edit Quantity')
        remove_action = menu.addAction('Remove')
        portion = None if is_template else row_dict.get('Portion')
        follow_action = pin_action = even_action = None
        if portion:
            menu.addSeparator()
            if portion['state'] == 'hand':
                follow_action = menu.addAction('Follow format rule')
                follow_action.setEnabled(portion['sizable'])
                if not portion['sizable']:
                    follow_action.setToolTip('Its unit isn’t a volume, so the rule can’t size it.')
            else:
                pin_action = menu.addAction('Size by hand')
                if portion['state'] == 'base' and portion['siblings'] >= 2:
                    even_action = menu.addAction('Split base evenly')
            edit_action.setEnabled(self.components_model.qty_editable(index.row()))
        open_action = edit_ing_action = None
        if row_dict['Type'] == 'recipe':
            menu.addSeparator()
            open_action = menu.addAction(f"Open {row_dict['Name']}")
        else:
            menu.addSeparator()
            edit_ing_action = menu.addAction('Edit ingredient…')
        if is_template:
            # Template-added rows are managed by the template, not the
            # recipe. Disable mutating actions; the user edits the
            # template in Configure › Formats & templates.
            edit_action.setEnabled(False)
            remove_action.setEnabled(False)
        chosen = menu.exec(self.components_table.viewport().mapToGlobal(point))
        if chosen is edit_action:
            self._on_component_activated(index)
        elif chosen is remove_action:
            self._remove_component(index.row())
        elif open_action is not None and chosen is open_action:
            self.openRecipeRequested.emit(row_dict['Id'])
        elif edit_ing_action is not None and chosen is edit_ing_action:
            self._edit_ingredient(row_dict['Id'])
        elif chosen is not None and chosen in (follow_action, pin_action, even_action):
            self._portion_action(chosen, follow_action, pin_action, row_dict)

    def _edit_ingredient(self, ingredient_id):
        '''Open the ingredient's editor (the main window's, so the library
        refreshes too), then re-read this recipe: its cost, nutrition and
        allergens may have changed.'''
        win = self.window()
        if hasattr(win, '_on_ingredient_edit_by_id'):
            dlg = win._on_ingredient_edit_by_id(ingredient_id)
        else:
            from gui.dialogs.ingredient_edit import IngredientEditDialog
            dlg = IngredientEditDialog(ingredient_id, parent=self)
            dlg.exec()
            if dlg.open_recipe_id is not None:
                self.openRecipeRequested.emit(dlg.open_recipe_id)
        if dlg.modified and not self._being_deleted:
            self._refresh()

    def _portion_action(self, chosen, follow_action, pin_action, row_dict):
        rid, iid, name = self.recipe_id, row_dict['Id'], row_dict['Name']
        if chosen is follow_action:
            self.undo_stack.push(PortionCommand(rid, f'{name}: follow format rule',
                                                lambda: db.follow_portion(rid, iid)))
        elif chosen is pin_action:
            self.undo_stack.push(PortionCommand(rid, f'{name}: size by hand', lambda: db.pin_portion(rid, iid)))
        else:
            self.undo_stack.push(PortionCommand(rid, 'Split base evenly', lambda: db.split_base_evenly(rid, iid)))

    def _remove_component(self, row):
        row_dict = self.components_model.row_dict(row)
        name = row_dict['Name']
        if QMessageBox.question(
            self, 'Remove', f"Remove '{name}' from this recipe?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            old_qty = float(row_dict.get('QuantityRaw', 0) or 0)
        except (TypeError, ValueError):
            old_qty = 0.0
        sort_order = row_dict.get('SortOrder')
        self.undo_stack.push(RemoveComponentCommand(
            self.recipe_id, row_dict['Type'], row_dict['Id'], old_qty, name,
            sort_order=sort_order,
        ))

    def _on_components_reordered(self, before, after):
        '''Model fired this when the user dropped a row at a new position.
        Push it through the undo stack so the DB rewrite is reversible.'''
        if before == after:
            return
        self.undo_stack.push(ReorderComponentsCommand(self.recipe_id, before, after))

    def print_recipe(self):
        from gui.printing.print_dialog import print_recipes
        print_recipes(self, [self.recipe_id])

    def _on_nutrition_label(self):
        NutritionLabelDialog(self.recipe_id, parent=self).exec()

    def _on_price_history(self):
        dlg = PriceHistoryDialog(self.recipe_id, self.name_edit.text(), recipe_mode=True, parent=self)
        dlg.exec()

    def _on_delete(self):
        name = self.name_edit.text()
        if QMessageBox.question(
            self, 'Delete', f'Delete {name}?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            db.delete_recipe(self.recipe_id)
        except Exception as exc:
            QMessageBox.warning(self, 'Recipe In Use', str(exc))
            return
        self.modified = True
        self.status_message = f"Deleted '{name}'"
        # Flag so close_requested() skips the cost-snapshot stamp
        # (the recipe row is already gone from the DB).
        self._being_deleted = True
        self.recipeDeleted.emit(self.recipe_id)


class RecipeEditDialog(QDialog):
    '''Thin modal wrapper around RecipeEditWidget. Kept for callers
    already in a modal context (the Ingredient editor's "Used in
    recipes" link opens a recipe from inside its own dialog, where a
    tabbed editor on the Recipes place can't be reached without
    closing the ingredient dialog first).'''

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.widget = RecipeEditWidget(recipe_id, parent=self)
        self.setWindowTitle(f"{config.APPNAME} | {self.widget.title()}")
        self.resize(1280, 820)
        self.widget.titleChanged.connect(
            lambda name: self.setWindowTitle(f"{config.APPNAME} | {name}")
        )
        self.widget.recipeDeleted.connect(lambda _id: self.accept())
        # No Library to go back to from a modal; the crumb closes it.
        self.widget.libraryRequested.connect(self.reject)

        close_btn = QPushButton('Close')
        close_btn.setAutoDefault(False)
        close_btn.setDefault(False)
        close_btn.clicked.connect(self.reject)
        save_sc = QShortcut(QKeySequence.Save, self)
        save_sc.activated.connect(self.widget.save)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(12, 8, 12, 12)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget, stretch=1)
        layout.addLayout(btn_row)

    # Property passthroughs for callers (main_window) that read these
    # after exec() to decide whether to refresh or flash a status toast.
    @property
    def recipe_id(self):
        return self.widget.recipe_id

    @property
    def modified(self):
        return self.widget.modified

    @property
    def status_message(self):
        return self.widget.status_message

    def done(self, result):
        if not self.widget.close_requested():
            return
        super().done(result)


class _PhotoDropBox(QWidget):
    '''Holds the wedge; accepts an image file dropped on it.'''

    def __init__(self, on_drop, parent=None):
        super().__init__(parent)
        self._on_drop = on_drop
        self.setAcceptDrops(True)

    def _image_path(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        path = urls[0].toLocalFile() if urls else ''
        return path if is_image_file(path) else ''

    def dragEnterEvent(self, event):
        if self._image_path(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        path = self._image_path(event)
        if path:
            event.acceptProposedAction()
            self._on_drop(path)


def _html_escape(text):
    return (str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _format_qty(value):
    try:
        return '{:.4f}'.format(float(value)).rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(value)


def _parse_menu_price(text):
    '''Accept blank / '-' / '$3.42' / '13.95' etc. Returns float or None;
    raises ValueError on anything else so the caller can refuse the edit.'''
    s = (text or '').strip().lstrip('$').strip()
    if not s or s == '-' or s == '—':
        return None
    return float(s)


def _format_menu_price(value):
    '''Inverse of _parse_menu_price for display.'''
    if value is None or value == '':
        return ''
    try:
        return '${:.2f}'.format(float(value))
    except (TypeError, ValueError):
        return str(value)


def _coerce_menu_price(value):
    '''DB → in-memory. None stays None; everything else becomes a float.'''
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
