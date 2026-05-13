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
    def __init__(self, parent_id, mode, child_id, qty, child_name):
        super().__init__(f'Remove {child_name}')
        self.parent_id = parent_id
        self.mode = mode
        self.child_id = child_id
        self.qty = qty

    def redo(self):
        db.delete_recipe_ingredient(self.parent_id, self.mode, self.child_id)

    def undo(self):
        db.add_recipe_ingredient(self.parent_id, self.mode, self.child_id, self.qty)


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


class ToggleTagCommand(QUndoCommand):
    def __init__(self, recipe_id, tag_id, state, tag_name):
        verb = 'Set' if state else 'Unset'
        super().__init__(f'{verb} tag {tag_name}')
        self.recipe_id = recipe_id
        self.tag_id = tag_id
        self.state = state

    def redo(self):
        db.modify_recipe_tag(self.recipe_id, self.tag_id, self.state)

    def undo(self):
        db.modify_recipe_tag(self.recipe_id, self.tag_id, not self.state)
