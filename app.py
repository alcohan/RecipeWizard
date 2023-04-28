import PySimpleGUI as sg
import setup
import config
import ingredients_module
import recipes_module

def refresh():
    print('Refreshing Ingredients & Recipes Data')
    window['-INGREDIENT-TABLE-'].Update(values=ingredients_module.format_data())
    window['-RECIPES-TABLE-'].Update(values=recipes_module.format_recipes_data())

sg.theme('LightGrey1')   # Add a touch of color

# All the stuff inside your window.
menu_layout = [['&File', ['[not implemented] import from csv', '[not implemented] export to csv', '[not implemented] get csv template', '---', 'E&xit']],
              ['&Tools', ['&Refresh::-REFRESH-','Reset Database::-RESET-']],
              ['&Help', ['About']]]

layout_ingredients = sg.Frame('Ingredients',ingredients_module.render())
layout_recipes = sg.Frame('Recipes',recipes_module.render())

layout = [[sg.Menu(menu_layout, k='-MENU-'),
          [layout_ingredients], 
          [layout_recipes]
          ]]


# Create the Window
window = sg.Window(f'Recipe Builder - {config.DATABASE}', layout, icon=config.ICON)

# Event Loop to process "events" and get the "values" of the inputs
while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, '-CLOSE-', 'Exit'): # if user closes window or clicks cancel
        break

    # Run the 'ingredients' events
    elif result := ingredients_module.loop(event,values,window):
        # If the loop returned 2, we need to refresh the data.
        if result == 2:
            refresh()
        pass

    # Run the 'recipes' events
    elif result := recipes_module.loop(event,values,window):
        if result == 2:
            refresh()
        pass

    elif event in ('-RESET-', 'Reset Database::-RESET-'):
        print('running setup script')
        setup.initializeDB()
        refresh()
    elif event in ('Refresh', 'Refresh::-REFRESH-'):
        print('Refreshing values')
        refresh()
    else:
        print('Unhandled Event', event, values)

window.close()