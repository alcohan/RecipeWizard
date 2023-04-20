import PySimpleGUI as sg
import db

def format_data():
    data = db.get_ingredients()
    return [(i['Name'], i['Unit'], i['Id']) for i in data]

# Pass the main window object
def reload_table(window):
    print('Reloading all ingredients data')
    window['-INGREDIENT-TABLE-'].Update(values=format_data())
    
def render():
    headings = ['Name', 'Unit']

    return sg.Table(values=format_data(), 
                        headings=headings, 
                        max_col_width=25, 
                        auto_size_columns=True,
                        display_row_numbers=False,
                        justification='right',
                        bind_return_key=True,
                        key='-INGREDIENT-TABLE-'
                        )
