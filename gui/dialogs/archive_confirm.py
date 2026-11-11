'''Archive guards. Recipes (the Library and the recipe tab): archiving
a sub-recipe that recipes on the menu still use asks first, since your
prep still makes it. Ingredients: archiving one that active recipes
use asks first, since they keep it.'''
from PySide6.QtWidgets import QMessageBox

import db


def confirm_archive(parent, recipe_id, name, always=False):
    '''True to go ahead and archive. Asks when live recipes use it, or
    (with `always`) every time.'''
    live = [p['Name'] for p in db.get_parent_recipes(recipe_id) if p.get('Status') != 'archived']
    if not live:
        if not always:
            return True
        box = QMessageBox(QMessageBox.Question, 'Archive recipe',
                          f'Archive {name}?', parent=parent)
        box.setInformativeText('You can restore it later.')
        archive = box.addButton('Archive', QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        box.exec()
        return box.clickedButton() is archive
    n = len(live)
    names = ', '.join(live[:5]) + (f' and {n - 5} more' if n > 5 else '')
    box = QMessageBox(QMessageBox.Warning, 'Archive sub-recipe',
                      f"{name} is used in {n} recipe{'s' if n != 1 else ''} on the menu: {names}.",
                      parent=parent)
    box.setInformativeText('Archiving hides it from the Library, but those recipes keep using it'
                           ' and their costs still include it.')
    archive = box.addButton('Archive anyway', QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(QMessageBox.Cancel)
    box.exec()
    return box.clickedButton() is archive


def confirm_archive_ingredient(parent, ingredient_id, name):
    '''True to go ahead and archive an ingredient. Asks only when
    active recipes use it.'''
    n = sum(1 for u in db.get_ingredient_usage(ingredient_id) if u.get('Status') != 'archived')
    if not n:
        return True
    box = QMessageBox(QMessageBox.Warning, 'Archive ingredient',
                      f"{name} is still used in {n} active recipe{'s' if n != 1 else ''}.", parent=parent)
    box.setInformativeText('Archiving will not remove it from those recipes. Archive it anyway?')
    archive = box.addButton('Archive anyway', QMessageBox.AcceptRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(QMessageBox.Cancel)
    box.exec()
    return box.clickedButton() is archive
