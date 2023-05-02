import PySimpleGUI as sg
import db
import modules.ingredients.ingredient as ingredient
from functools import cache

@cache
def format_data():
    data = db.get_ingredients()
    return [(i['Name'], i['Unit'], i['Id']) for i in data]

def render():
    headings = ['Name', 'Unit']

    return [
        [sg.Text('🔍'), sg.InputText('',enable_events=True, k='-INGREDIENTS-FILTER-')],
        [sg.Table(values=format_data(), 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=True,
                        key='-INGREDIENT-TABLE-'
                        )],
        [sg.Button('New Ingredient', key='-NEW-INGREDIENT-')]
    ]

def loop(event, values, window):
    '''Run the event loop for Ingredients. Return values: 0=nothing, 1=event processed, 2=event processed + refresh needed'''
    if event == '-INGREDIENT-TABLE-':
        if(len(values['-INGREDIENT-TABLE-'])>0):
            row_index = values['-INGREDIENT-TABLE-'][0]
            clicked_row = window['-INGREDIENT-TABLE-'].get()[row_index]
            id = clicked_row[-1]
            print(f"Popup for {clicked_row[0]}")
            ingredient.edit(id)
        return 2
    elif event == '-NEW-INGREDIENT-':
        new_id = ingredient.create()
        # If nothing was created, return without refresh
        if new_id == 0:
            return 1
        # Edit the newly created ingredient
        ingredient.edit(new_id)
        return 2
    elif event == '-INGREDIENTS-FILTER-':
        print('Searching for: ', values[event])
        filter_value = values['-INGREDIENTS-FILTER-'].lower()
        filtered_data = [row for row in format_data() if filter_value in ' '.join(map(str, row)).lower()]
        window['-INGREDIENT-TABLE-'].Update(values=filtered_data)
        return 1
    
    # return 0 if we didn't do anything
    return 0