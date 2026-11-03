'''Session-scoped compare tray.

A list of recipe ids the user has staged for side-by-side comparison.
Lives for the life of the window (not persisted to disk) and emits
`changed` whenever membership shifts, so the status bar's count, the
Compare place's filtered view, and card checkbox states all stay in
lockstep.

The tray is injected into widgets that need it rather than being a
module-level singleton — keeps testing simple and lets multiple
windows (if we ever get there) have independent trays.
'''
from PySide6.QtCore import QObject, Signal


class CompareTray(QObject):
    '''Ordered set of recipe ids staged for comparison.

    Order matters for the Compare place's row order; de-dupe is on
    add so adding an already-present id is a no-op. Removing a
    missing id is also a no-op — the signal fires only when the set
    actually changes.'''

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = []

    def add(self, recipe_id):
        '''Append `recipe_id` if not already present. Emits changed.'''
        if recipe_id in self._ids:
            return False
        self._ids.append(recipe_id)
        self.changed.emit()
        return True

    def remove(self, recipe_id):
        if recipe_id not in self._ids:
            return False
        self._ids.remove(recipe_id)
        self.changed.emit()
        return True

    def toggle(self, recipe_id):
        '''Convenience for Space-to-add/remove. Returns the new
        membership state (True if the id is now in the tray).'''
        if recipe_id in self._ids:
            self._ids.remove(recipe_id)
            self.changed.emit()
            return False
        self._ids.append(recipe_id)
        self.changed.emit()
        return True

    def clear(self):
        if not self._ids:
            return False
        self._ids = []
        self.changed.emit()
        return True

    def set_ids(self, recipe_ids):
        '''Replace the tray with `recipe_ids` (a saved comparison).'''
        ids = list(dict.fromkeys(recipe_ids))
        if ids == self._ids:
            return False
        self._ids = ids
        self.changed.emit()
        return True

    def move(self, recipe_id, index):
        '''Move an id to position `index` (drag to reorder).'''
        if recipe_id not in self._ids:
            return False
        ids = [i for i in self._ids if i != recipe_id]
        ids.insert(max(0, min(index, len(ids))), recipe_id)
        return self.set_ids(ids)

    def contains(self, recipe_id):
        return recipe_id in self._ids

    def count(self):
        return len(self._ids)

    def ids(self):
        '''Snapshot copy — callers mutate at their own peril.'''
        return list(self._ids)
