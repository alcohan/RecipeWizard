import PySimpleGUI as sg
import db
import config

FIELDS = [('name', 'Name'), ('address', 'Address'), ('city', 'City'), ('state', 'State'), ('zip', 'Zip')]
TABLE_HEADINGS = ['Name', 'City', 'State']


def _format_data():
    return [(s['name'] or '', s['city'] or '', s['state'] or '', s['id']) for s in db.get_suppliers()]


def _edit(supplier_id=None, location=(None, None)):
    '''
    Popup to create (supplier_id=None) or edit an existing supplier.
    Returns True if the suppliers list was modified.
    '''
    is_new = supplier_id is None
    if is_new:
        row = {'id': None, 'name': '', 'address': '', 'city': '', 'state': '', 'zip': ''}
        title_suffix = '> NEW SUPPLIER <'
    else:
        row = db.get_suppliers(supplier_id)
        title_suffix = row['name']

    layout_fields = [
        [sg.Text(label, size=(8, 1)), sg.InputText(row[key] or '', k=key, size=(40, 1))]
        for key, label in FIELDS
    ]

    save_button = sg.Button('Save', k='-SAVE-')
    delete_button = sg.Button('Delete', k='-DELETE-', button_color=('white', 'red'), visible=not is_new)
    close_button = sg.Button('Cancel' if is_new else 'Close', button_color=('white', 'gray'), k='-CLOSE-')
    layout = layout_fields + [[save_button, delete_button, close_button]]

    window = sg.Window(f'{config.APPNAME} | Supplier | {title_suffix}', layout, icon=config.ICON, location=location)
    modified = False

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, '-CLOSE-'):
            break
        if event == '-SAVE-':
            if not values['name'].strip():
                sg.popup_ok('Name is required.', title='Missing Name', icon=config.ICON)
                continue
            if is_new:
                db.create_supplier(values)
            else:
                db.update_supplier(supplier_id, values)
            modified = True
            break
        if event == '-DELETE-':
            if sg.popup_ok_cancel(f"Delete {row['name']}?", title='Delete', icon=config.ICON) == 'OK':
                try:
                    db.delete_supplier(supplier_id)
                    modified = True
                    break
                except Exception as err:
                    sg.popup_ok(err, title='Supplier In Use', icon=config.ICON)

    window.close()
    return modified


def render():
    '''
    Top-level Suppliers manager. List of suppliers with row-click to edit and a New button.
    '''
    table = sg.Table(
        values=_format_data(),
        headings=TABLE_HEADINGS,
        max_col_width=30,
        auto_size_columns=True,
        display_row_numbers=False,
        justification='left',
        bind_return_key=True,
        num_rows=15,
        key='-SUPPLIERS-TABLE-',
    )
    layout = [
        [table],
        [sg.Button('New Supplier', k='-NEW-'), sg.Push(), sg.Button('Close', button_color=('white', 'gray'), k='-CLOSE-')],
    ]
    window = sg.Window(f'{config.APPNAME} | Suppliers', layout, icon=config.ICON)

    def refresh():
        window['-SUPPLIERS-TABLE-'].Update(values=_format_data())

    while True:
        event, values = window.read()
        if event in (sg.WIN_CLOSED, '-CLOSE-'):
            break
        if event == '-SUPPLIERS-TABLE-':
            if not values['-SUPPLIERS-TABLE-']:
                continue
            row_index = values['-SUPPLIERS-TABLE-'][0]
            clicked_row = window['-SUPPLIERS-TABLE-'].get()[row_index]
            supplier_id = clicked_row[-1]
            current = window.CurrentLocation()
            popup_location = (current[0] + 32, current[1] + 32)
            if _edit(supplier_id, location=popup_location):
                refresh()
        elif event == '-NEW-':
            if _edit():
                refresh()

    window.close()
