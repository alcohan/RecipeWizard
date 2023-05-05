import PySimpleGUI as sg
from config import ICON
from config import get_image

def render():
    '''
    Popup window for "About" this application
    '''
    # Define the layout for the popup window
    layout = [[sg.Text('RecipeWizard v0.0.1')],
            [sg.Text('by Adrian Cohan')],
            [sg.Image(get_image('static/NutritionixAPI_hires_flat.png'))]]

    # Create the popup window
    window = sg.Window('About', layout,icon=ICON)

    # Display the popup window and wait for a button press
    event, values = window.read()

    # Close the popup window
    window.close()
