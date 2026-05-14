'''QUndoCommand subclasses for the recipe edit dialog.

Each command captures the inverse data on construction (or trusts what was
just-before state), so undo() and redo() can each mutate the DB without
having to re-query for prior values. The dialog connects QUndoStack's
indexChanged signal to a refresh slot, so every push/undo/redo triggers
a UI re-read.'''
from PySide6.QtGui import QUndoCommand

import db


class UpdateRecipeInfoCommand(QUndoCommand):
    '''Capture changes to Name / Unit / OutputQty as a single undoable action.
    `before` and `after` are (name, unit, outputqty) tuples.'''

    def __init__(self, recipe_id, before, after):
        super().__init__('Edit recipe info')
        self.recipe_id = recipe_id
        self.before = before
        self.after = after

    def redo(self):
        db.update_recipe_info(self.recipe_id, *self.after)

    def undo(self):
        db.update_recipe_info(self.recipe_id, *self.before)


class AddComponentCommand(QUndoCommand):
    def __init__(self, parent_id, mode, child_id, qty, child_name):
        super().__init__(f'Add {child_name}')
        self.parent_id = parent_id
        self.mode = mode
        self.child_id = child_id
        self.qty = qty

    def redo(self):
        db.add_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.qty)

    def undo(self):
        db.delete_recipe_ingredient(self.parent_id, self.mode, self.child_id)


class RemoveComponentCommand(QUndoCommand):
    def __init__(self, parent_id, mode, child_id, qty, child_name, sort_order=None):
        super().__init__(f'Remove {child_name}')
        self.parent_id = parent_id
        self.mode = mode
        self.child_id = child_id
        self.qty = qty
        # Capture the row's SortOrder so undo puts it back in its original
        # slot instead of always appending to the end.
        self.sort_order = sort_order

    def redo(self):
        db.delete_recipe_ingredient(self.parent_id, self.mode, self.child_id)

    def undo(self):
        db.add_recipe_ingredient(
            self.parent_id, self.mode, self.child_id, self.qty, self.sort_order,
        )


class SetComponentQtyCommand(QUndoCommand):
    def __init__(self, parent_id, mode, child_id, before, after, child_name):
        super().__init__(f'Change {child_name} qty')
        self.parent_id = parent_id
        self.mode = mode
        self.child_id = child_id
        self.before = before
        self.after = after

    def redo(self):
        db.update_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.after)

    def undo(self):
        db.update_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.before)


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
