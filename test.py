import PySimpleGUI as sg
import db

data = db.get_eligible_ingredients(2)
view = [f'{d[2]} ({d[3]})' for d in data]

layout = [
    [sg.Combo(view, size=20, enable_events=True, key='COMBO')],
    [sg.Push(), sg.Button('Check')],
]
window = sg.Window('Title', layout)

while True:

    event, values = window.read()

    if event == sg.WIN_CLOSED:
        break
    elif event in ('COMBO', 'Check'):
        text = values['COMBO']
        index1 = window['COMBO'].widget.current()
        index2 = view.index(text) if text in view else -1
        print(index1, index2, repr(values['COMBO']))
        print(data[index2])

window.close()


# names = ['Roberta', 'Kylie', 'Jenny', 'Helen',
#          'Andrea', 'Meredith', 'Deborah', 'Pauline',
#          'Belinda', 'Wendy']

# layout = [[sg.Text('Listbox with search')],
#           [sg.Input(size=(20, 1), enable_events=True, key='-INPUT-')],
#           [sg.Listbox(names, size=(20, 4), enable_events=True, key='-LIST-')],
#           [sg.Button('Chrome'), sg.Button('Exit')]]

# window = sg.Window('Listbox with Search', layout)
# # Event Loop
# while True:
#     event, values = window.read()
#     if event in (sg.WIN_CLOSED, 'Exit'):                # always check for closed window
#         break
#     if values['-INPUT-'] != '':                         # if a keystroke entered in search field
#         search = values['-INPUT-']
#         new_values = [x for x in names if search in x]  # do the filtering
#         window['-LIST-'].update(new_values)     # display in the listbox
#     else:
#         # display original unfiltered list
#         window['-LIST-'].update(names)
#     # if a list item is chosen
#     if event == '-LIST-' and len(values['-LIST-']):
#         sg.popup('Selected ', values['-LIST-'])

# window.close()