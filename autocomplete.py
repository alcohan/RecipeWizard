import PySimpleGUI as sg
import config
import db

class Autocomplete:
    '''
    Text box + Listbox autocomplete. Provide a list of choices and a key in which the value will be found
    Window has to have return_keyboard_events=true
    '''
    def __init__(self, choices, key='-IN-'):
        _input_width = 20
        _num_items_to_show = 3

        self.choices = choices
        self.key=key
        self.layout = [
                [sg.Input(size=(_input_width, 1), enable_events=True, key=key)],
                [sg.pin(sg.Col([[sg.Listbox(values=choices, size=(_input_width, _num_items_to_show), enable_events=True, key='-BOX-',
                                            select_mode=sg.LISTBOX_SELECT_MODE_SINGLE, no_scrollbar=True)]],
                                            key='-BOX-CONTAINER-', pad=(0, 0), visible=False))]
            ]
        
        self._prediction_list = [] 
        self._input_text = ""
        self._sel_item = 0
        self.selection = ""
    
    def handle_select(self, window, values):
        # Store the value of the selected option
        value = values['-BOX-'][0]
        # Update our text box
        window[self.key].update(value)
        # Update the variable to be accessed
        self.selection = value
        # Hide the listbox of other options
        window['-BOX-CONTAINER-'].update(visible=False)


    def loop(self, window, event, values):
        '''run the event loop'''
        if event.startswith('Escape'):
            window[self.key].update('')
            window['-BOX-CONTAINER-'].update(visible=True)
        elif event.startswith('Down') and len(self._prediction_list):
            self._sel_item = (self._sel_item + 1) % len(self._prediction_list)
            window['-BOX-'].update(set_to_index=self._sel_item, scroll_to_index=self._sel_item)
        elif event.startswith('Up') and len(self._prediction_list):
            self._sel_item = (self._sel_item + (len(self._prediction_list) - 1)) % len(self._prediction_list)
            window['-BOX-'].update(set_to_index=self._sel_item, scroll_to_index=self._sel_item)
        elif event == '\r':
            if len(values['-BOX-']) > 0:
                self.handle_select(window, values)
        elif event == self.key:
            text = values[self.key].lower()
            if text == self._input_text:
                return
            else:
                self._input_text = text
            self._prediction_list = [item for item in self.choices if text in item.lower()]

            window['-BOX-'].update(values=self._prediction_list)
            self._sel_item = 0
            window['-BOX-'].update(set_to_index=self._sel_item)

            if len(self._prediction_list) > 0:
                window['-BOX-CONTAINER-'].update(visible=True)
            else:
                window['-BOX-CONTAINER-'].update(visible=False)
        elif event == '-BOX-':
            self.handle_select(window, values)
        
def demo(choices, key='-IN-'):
    '''
    Autocomplete element
    '''

    window_title = f'{config.APPNAME} | > AUTOCOMPLETE DEMO <'
    
    a = Autocomplete(choices, key)
    layout = [  [a.layout]
            ]

    # Create the Window
    window = sg.Window(window_title, layout, return_keyboard_events=True, finalize=True, icon=config.ICON)

    while True:
        event, values = window.read()
        print(event,values)
        if event == sg.WIN_CLOSED or event == '-CLOSE-': # if user closes window or clicks cancel
            print('Closing without saving changes')
            break
        
        a.loop(window, event, values)

    window.close()

if __name__=='__main__':
    
    data = db.get_eligible_ingredients(2)
    choices = [f'{d[2]} ({d[3]}) - {d[1]}[{d[0]}]' for d in data]
    demo(choices, key='-ANOTHERKEY-')