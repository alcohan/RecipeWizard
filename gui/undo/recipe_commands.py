'''QUndoCommand subclasses for the recipe edit dialog.

Each command captures the inverse data on construction (or trusts what was
just-before state), so undo() and redo() can each mutate the DB without
having to re-query for prior values. The dialog connects QUndoStack's
indexChanged signal to a refresh slot, so every push/undo/redo triggers
a UI re-read.'''
from PySide6.QtGui import QUndoCommand

import db


class UpdateRecipeInfoCommand(QUndoCommand):
    '''Capture changes to Name / Unit / OutputQty / menu_price as a single
    undoable action. `before` and `after` are
    (name, unit, outputqty, menu_price) tuples; menu_price may be None.'''

    def __init__(self, recipe_id, before, after):
        super().__init__('Edit recipe info')
        self.recipe_id = recipe_id
        self.before = before
        self.after = after

    def redo(self):
        db.update_recipe_info(self.recipe_id, *self.after)

    def undo(self):
        db.update_recipe_info(self.recipe_id, *self.before)


class SetRecipeImageCommand(QUndoCommand):
    '''Set or clear a recipe's photo (a filename in the recipe photos
    folder; '' for none). The file itself is never deleted.'''

    def __init__(self, recipe_id, before, after):
        super().__init__('Remove photo' if not after else 'Set photo')
        self.recipe_id = recipe_id
        self.before = before or ''
        self.after = after or ''

    def redo(self):
        db.set_recipe_image(self.recipe_id, self.after)

    def undo(self):
        db.set_recipe_image(self.recipe_id, self.before)


class _SnapshotCommand(QUndoCommand):
    '''A component edit can resize other rows too (portion rules re-split
    a base when a green is added or removed, and typing a quantity pins
    its category). So these commands run the edit once, then undo/redo
    by restoring the recipe's whole Connections snapshot.'''

    def __init__(self, label, parent_id):
        super().__init__(label)
        self.parent_id = parent_id
        self._before_snapshot = None
        self._after_snapshot = None

    def apply(self):
        raise NotImplementedError

    def redo(self):
        if self._before_snapshot is None:
            self._before_snapshot = db.snapshot_recipe_connections(self.parent_id)
            self.apply()
            self._after_snapshot = db.snapshot_recipe_connections(self.parent_id)
        else:
            db.restore_recipe_connections(self.parent_id, self._after_snapshot)

    def undo(self):
        db.restore_recipe_connections(self.parent_id, self._before_snapshot)


class AddComponentCommand(_SnapshotCommand):
    def __init__(self, parent_id, mode, child_id, qty, child_name):
        super().__init__(f'Add {child_name}', parent_id)
        self.mode = mode
        self.child_id = child_id
        self.qty = qty

    def apply(self):
        db.add_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.qty)


class RemoveComponentCommand(_SnapshotCommand):
    def __init__(self, parent_id, mode, child_id, qty, child_name, sort_order=None):
        super().__init__(f'Remove {child_name}', parent_id)
        self.mode = mode
        self.child_id = child_id
        self.qty = qty
        self.sort_order = sort_order   # kept for callers; the snapshot restores order

    def apply(self):
        db.delete_recipe_ingredient(self.parent_id, self.mode, self.child_id)


class SetComponentQtyCommand(_SnapshotCommand):
    def __init__(self, parent_id, mode, child_id, before, after, child_name):
        super().__init__(f'Change {child_name} qty', parent_id)
        self.mode = mode
        self.child_id = child_id
        self.before = before
        self.after = after

    def apply(self):
        db.update_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.after)


class PortionCommand(_SnapshotCommand):
    '''Any portion-rules edit on one recipe (follow / pin / re-split a
    base): `edit` is a callable that does it; undo restores the snapshot.'''

    def __init__(self, parent_id, label, edit):
        super().__init__(label, parent_id)
        self._edit = edit

    def apply(self):
        self._edit()


class ReorderComponentsCommand(QUndoCommand):
    '''Captures a full reordering of a recipe's components. `before` and
    `after` are lists of (mode, child_id) tuples in their respective
    orders.'''

    def __init__(self, recipe_id, before, after):
        super().__init__('Reorder components')
        self.recipe_id = recipe_id
        self.before = list(before)
        self.after = list(after)

    def redo(self):
        db.reorder_recipe_components(self.recipe_id, self.after)

    def undo(self):
        db.reorder_recipe_components(self.recipe_id, self.before)


class SetRecipeTagCommand(QUndoCommand):
    '''Change a recipe's format. The first redo actually runs the
    template transition (add items, scale categories, etc.) and captures
    the resulting Connections snapshot; subsequent redos and the undo
    both replay snapshots so we never have to invert the transition
    logic at runtime.

    `before` and `after` are tag ids (or None for "no tag").'''

    def __init__(self, recipe_id, before, after, label):
        super().__init__(label)
        self.recipe_id = recipe_id
        self.before = before
        self.after = after
        # Snapshots captured the first time redo() runs. None until then.
        self._before_snapshot = None
        self._after_snapshot = None

    def redo(self):
        if self._before_snapshot is None:
            # First-time apply: actually run the transition, then snapshot.
            self._before_snapshot = db.snapshot_recipe_connections(self.recipe_id)
            db.transition_recipe_format(self.recipe_id, self.before, self.after)
            self._after_snapshot = db.snapshot_recipe_connections(self.recipe_id)
        else:
            # Redo after a prior undo — replay the snapshot we already have.
            db.restore_recipe_connections(self.recipe_id, self._after_snapshot)
        db.set_recipe_tag(self.recipe_id, self.after)

    def undo(self):
        db.restore_recipe_connections(self.recipe_id, self._before_snapshot)
        db.set_recipe_tag(self.recipe_id, self.before)


class SetRecipeStatusCommand(QUndoCommand):
    '''Archive or restore a recipe. `before` / `after` are 'active' or
    'archived'.'''

    def __init__(self, recipe_id, before, after, name):
        super().__init__(f"{'Archive' if after == 'archived' else 'Restore'} {name}")
        self.recipe_id = recipe_id
        self.before = before
        self.after = after

    def redo(self):
        db.set_recipe_status(self.recipe_id, self.after)

    def undo(self):
        db.set_recipe_status(self.recipe_id, self.before)


class SetRecipeTagsCommand(QUndoCommand):
    '''Replace a recipe's recipe tags (Core, Seasonal… — not its
    format). `before` / `after` are sets of tag ids.'''

    def __init__(self, recipe_id, before, after, label='Change tags'):
        super().__init__(label)
        self.recipe_id = recipe_id
        self.before = set(before)
        self.after = set(after)

    def redo(self):
        db.set_recipe_tags(self.recipe_id, self.after)

    def undo(self):
        db.set_recipe_tags(self.recipe_id, self.before)
