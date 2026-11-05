'''Let Ctrl+Z / Ctrl+Y reach an undo stack from inside a text field.

A focused QLineEdit claims the Undo and Redo keys for its own typing
history (it accepts the ShortcutOverride), even when there's nothing of
the user's left to undo there, so a window's Undo action never fires.
Installed on a field, UndoKeysToStack passes those keys on whenever the
field has no edit in progress — `has_pending(field)` says whether it
does — and leaves them to the field while one is being typed.'''
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence


class UndoKeysToStack(QObject):
    def __init__(self, has_pending, parent=None):
        super().__init__(parent)
        self._has_pending = has_pending

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ShortcutOverride and (
                event.matches(QKeySequence.Undo) or event.matches(QKeySequence.Redo)):
            if not self._has_pending(obj):
                # Not accepted: Qt goes on to the window's shortcut.
                event.ignore()
                return True
        return False


def pass_undo_keys(field, has_pending):
    '''Install UndoKeysToStack on `field` (parented to it).'''
    f = UndoKeysToStack(has_pending, field)
    field.installEventFilter(f)
    return f
