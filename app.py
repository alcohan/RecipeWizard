import PySimpleGUI as sg
import setup
import config
import modules.ingredients_module as ingredients_module
import modules.recipes_module as recipes_module
<<<<<<< HEAD
import modules.about as about
import modules.suppliers.suppliers as suppliers

=======
>>>>>>> 3bfae57e0e03c372581f51e254dacdeb31dd4240

def refresh():
    print('Refreshing Ingredients & Recipes Data')
    recipes_module.format_recipes_data.cache_clear()
    ingredients_module.format_data.cache_clear()
    window['-INGREDIENT-TABLE-'].Update(values=ingredients_module.format_data())
    window['-RECIPES-TABLE-'].Update(values=recipes_module.format_recipes_data())

sg.theme('LightGrey1')   # Add a touch of color

# All the stuff inside your window.
menu_layout = [['&File', ['[todo] import from csv', '[todo] export to csv', '---', 'E&xit']],
              ['&Manage',['&Suppliers', '---', 'Tags', 'Templates']],
              ['&Tools', ['&Refresh::-REFRESH-','Reset Database::-RESET-']],
              ['&Help', ['About']]]

layout_ingredients = sg.Frame('Ingredients',ingredients_module.render())
layout_recipes = sg.Frame('Recipes',recipes_module.render())

layout = [[sg.Menu(menu_layout, k='-MENU-'),
          [layout_ingredients], 
          [layout_recipes]
          ]]


# Create the Window
window = sg.Window(config.APPNAME, layout, icon=config.ICON)

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
    elif event == 'About':
        about.render()
    elif event == 'Suppliers':
        suppliers.render()
    else:
        print('Unhandled Event', event, values)

window.close()