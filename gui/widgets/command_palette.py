'''⌘K "go to anything" palette.

Modal popover with a single search field, then a ranked list of
recipes, ingredients, and commands that match the user's query. Arrow
keys move the selection; Enter activates; Escape dismisses.

Lightweight: substring/prefix match (no full fuzzy), top-N per section.
Index is built from whatever the caller hands in — the palette itself
doesn't query the DB, so test setup and future "add another kind of
thing to search" stay simple.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout,
)


# How many items per section. Keep each section short so the whole
# list is one eye-span.
_PER_SECTION_LIMIT = 6


class CommandPalette(QDialog):
    '''Caller passes three iterables:
      recipes:    [(id, name), ...]
      ingredients: [(id, name), ...]
      commands:   [(key, label), ...]

    Fires one of three signals on activation:
      recipeChosen(int)      # recipe id
      ingredientChosen(int)  # ingredient id
      commandChosen(str)     # command key
    '''

    recipeChosen = Signal(int)
    ingredientChosen = Signal(int)
    commandChosen = Signal(str)

    def __init__(self, recipes, ingredients, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Go to anything')
        # Dialog chrome: borderless popover with a modest shadow. Qt
        # doesn't do blur on its own; a plain border + background works.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Popup)
        self.setMinimumWidth(520)
        self.setMaximumWidth(640)

        self._recipes = list(recipes)
        self._ingredients = list(ingredients)
        self._commands = list(commands)

        self.search = QLineEdit()
        self.search.setPlaceholderText('Go to a recipe, ingredient, or command…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refresh_results)
        self.search.returnPressed.connect(self._activate_current)

        self.results = QListWidget()
        self.results.setSelectionMode(QListWidget.SingleSelection)
        self.results.itemActivated.connect(self._on_item_activated)

        # Up/Down should move selection in the list while the user's
        # typing in the search box — intercept those on the search box.
        self.search.installEventFilter(self)

        hint = QLabel('↑↓ navigate · ↩ open · Esc close')
        hint.setStyleSheet('color: #55624c; font-size: 11px; padding: 4px 0 0;')
        hint.setAlignment(Qt.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(self.search)
        layout.addWidget(self.results, stretch=1)
        layout.addWidget(hint)

        self.setStyleSheet('''
            CommandPalette {
                background: #ffffff;
                border: 1px solid #ebe1cd;
                border-radius: 10px;
            }
            QLineEdit {
                border: 1px solid #7d8771;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
            }
            QListWidget {
                border: 0;
                background: transparent;
                font-size: 13px;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: #e9f1d9;
                color: #082c00;
            }
        ''')

        self.resize(540, 360)
        self._refresh_results('')

    # --- event filter --------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == event.Type.KeyPress:
            k = event.key()
            if k == Qt.Key_Down:
                self._move_selection(1)
                return True
            if k == Qt.Key_Up:
                self._move_selection(-1)
                return True
        return super().eventFilter(obj, event)

    # --- search --------------------------------------------------------

    def _refresh_results(self, _text=None):
        needle = self.search.text().strip().lower()
        self.results.clear()

        sections = [
            ('Recipes', self._match(self._recipes, needle), 'recipe'),
            ('Ingredients', self._match(self._ingredients, needle), 'ingredient'),
            ('Commands', self._match(self._commands, needle), 'command'),
        ]
        first_selectable = None
        for section_title, hits, kind in sections:
            if not hits:
                continue
            # Section header is non-selectable, muted.
            header = QListWidgetItem(section_title.upper())
            header.setFlags(Qt.NoItemFlags)
            header.setData(Qt.ForegroundRole, Qt.gray)
            self.results.addItem(header)
            for item_id_or_key, label in hits[:_PER_SECTION_LIMIT]:
                row = QListWidgetItem(label)
                row.setData(Qt.UserRole, (kind, item_id_or_key))
                self.results.addItem(row)
                if first_selectable is None:
                    first_selectable = row
        if first_selectable is not None:
            self.results.setCurrentItem(first_selectable)

    @staticmethod
    def _match(items, needle):
        '''Rank by (match-position, length-of-label) so prefix matches
        rank before mid-string matches and shorter labels win ties.
        An empty needle returns everything.'''
        if not needle:
            return list(items)
        scored = []
        for item_id_or_key, label in items:
            lab = (label or '').lower()
            pos = lab.find(needle)
            if pos < 0:
                continue
            scored.append(((pos, len(lab)), item_id_or_key, label))
        scored.sort(key=lambda t: t[0])
        return [(t[1], t[2]) for t in scored]

    # --- selection / activation ----------------------------------------

    def _move_selection(self, delta):
        n = self.results.count()
        if n == 0:
            return
        cur = self.results.currentRow()
        if cur < 0:
            cur = 0
        nxt = cur
        for _ in range(n):
            nxt = (nxt + delta) % n
            item = self.results.item(nxt)
            # Skip non-selectable section headers.
            if item.flags() & Qt.ItemIsSelectable:
                self.results.setCurrentRow(nxt)
                return

    def _activate_current(self):
        item = self.results.currentItem()
        if item is None:
            return
        self._on_item_activated(item)

    def _on_item_activated(self, item):
        if not (item.flags() & Qt.ItemIsSelectable):
            return
        kind, key = item.data(Qt.UserRole)
        if kind == 'recipe':
            self.recipeChosen.emit(int(key))
        elif kind == 'ingredient':
            self.ingredientChosen.emit(int(key))
        elif kind == 'command':
            self.commandChosen.emit(str(key))
        self.accept()
