'''The food-cost target: one place for every view that flags recipes
over it (gallery cards, inspector, Needs review, the recipe editor's
bar, Analytics, the compare tray, the filter pane).

Set on Configure › Preferences. Stored in QSettings as a fraction under
'food_cost/target_pct' (the key the editor already read) plus an on/off
switch, 'food_cost/enabled'. When it's off nothing is flagged and no
target is drawn.
'''
from PySide6.QtCore import QSettings

KEY_TARGET = 'food_cost/target_pct'
KEY_ENABLED = 'food_cost/enabled'
DEFAULT_FRACTION = 0.28


def enabled():
    return QSettings().value(KEY_ENABLED, True, type=bool)


def stored_fraction():
    '''The saved target even while it's switched off (for the settings UI).'''
    value = QSettings().value(KEY_TARGET, DEFAULT_FRACTION, type=float)
    return value if 0 < value < 1 else DEFAULT_FRACTION


def target_fraction():
    '''The target as a fraction (0.28), or None when switched off.'''
    return stored_fraction() if enabled() else None


def target_percent():
    '''The target as a percent (28.0), or None when switched off.'''
    t = target_fraction()
    return None if t is None else t * 100


def over_percent(pct):
    '''True when a food-cost percent (28.6) is over an active target.'''
    t = target_percent()
    return t is not None and pct is not None and pct > t


def save(is_enabled, fraction):
    QSettings().setValue(KEY_ENABLED, bool(is_enabled))
    QSettings().setValue(KEY_TARGET, float(fraction))
