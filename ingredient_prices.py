import PySimpleGUI as sg
import db
import config
from datetime import date
from re import sub

def edit_one(ingredient_id):

    this_ingredient = db.get_ingredients(ingredient_id)
    latest_values = db.ingredient_price_latest(ingredient_id)

    formdata = latest_values if latest_values else {'unit_price': 0, 'case_price': 0, 'supplier_id':'', 'units_per_case': ''}

    def format_data():
        display=formdata.copy()
        display['unit_price'] = "$ {:.4f}".format(formdata['unit_price'])
        display['case_price'] = f"$ {formdata['case_price']}"
        
        return display
    display = format_data()
    
    layout_buttons = [sg.Button('Save', key='-SAVE-'),
                      sg.Button('Close', button_color=("white","gray"), k='-CLOSE-')]

    layout = [
            [sg.Push(), sg.Text('Ingredient:'), sg.InputText( this_ingredient['Name'], size=(30,1), disabled=True)],
            [sg.Push(), sg.Text('Supplier ID:'), sg.InputText(display['supplier_id'], size=(30,1), key='supplier_id')],
            [sg.Push(), sg.Text('Case Price:'), sg.InputText(display['case_price'], size=(30,1), key='case_price', enable_events=True)],
            [sg.Push(), sg.Text('Yield:'), sg.InputText(display['units_per_case'], size=(30,1), key='units_per_case', enable_events=True)],
            [sg.Push(), sg.Text('Unit Price:'), sg.InputText(display['unit_price'], size=(30,1), key='unit_price', disabled=True)],
            [sg.Push(), sg.Text('Effective Date:'), sg.Input(date.today(), key='effective_date', size=(20,1)), sg.Button('Select', k='-DATE-POPUP-')],

            layout_buttons 
            ]

    window = sg.Window('Price: {name}'.format(name=this_ingredient['Name']), layout, icon=config.ICON)

    # Event Loop 
    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        
        elif event == '-SAVE-':
            db.ingredient_price_new(ingredient_id, (values['supplier_id'],formdata['case_price'],formdata['units_per_case'],values['effective_date']))
            break

        elif event in ('case_price', 'units_per_case'):
            # Strip all characters from the input that aren't valid numbers
            new = sub(r'[^\d\.]', '', values[event])
            # save this value
            formdata[event] = new
            # Format the currency
            window[event].update(format_data()[event])
            try: # Update the calculated Unit Price
                a, b = float(formdata['case_price']), float(formdata['units_per_case'])
                window['unit_price'].update('$ ' + str("{:.4f}".format(a / b,4)))
            except: # If error (one field is missing) insert a placeholder
                window['unit_price'].update('$ -')


        elif event == '-DATE-POPUP-':
            m, d, y = sg.popup_get_date(close_when_chosen=True) 
            window['effective_date'].update(date(y,m,d))
        else:
            print('Unhandled Event', event, values, )

    window.close()
