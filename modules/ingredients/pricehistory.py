import PySimpleGUI as sg
import matplotlib.pyplot as plt
from config import ICON
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import PySimpleGUI as sg
import matplotlib

import matplotlib.dates as mdates
from datetime import datetime

from db import get_price_history, get_recipe_price_history

matplotlib.use('TkAgg')

def render(id, name='Ingredient', recipeMode=False):
    '''
    Render the price history popup for ingredient id {id}
    '''
    # Draw the figure on the canvas
    def draw_figure(canvas, figure):
        tkcanvas = FigureCanvasTkAgg(figure, canvas)
        tkcanvas.draw()
        tkcanvas.get_tk_widget().pack(side='top', fill='both', expand=1)
        return tkcanvas
        
    def generate_figure(data):
        '''
        Generate the figure. Expects a dictionary with values 'date' and 'price'
        '''
        # Extract the dates and prices
        dates = [datetime.strptime(d['date'], '%Y-%m-%d') for d in data]
        prices = [d['price'] for d in data]

        # Create the figure
        fig, ax = plt.subplots()

        # Plot the data
        ax.plot_date(dates, prices, linestyle='solid')

        # Add labels and title
        ax.set_xlabel('Date')
        ax.set_ylabel('Price')
        ax.set_title(name)

        # Set y-axis minimum to 0
        ax.set_ylim([0, max(prices)*1.1])
        ax.yaxis.set_major_formatter('${x:1.2f}')

        # Rotate x-axis tick labels and show labels for fewer dates
        locator = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        plt.xticks(rotation=45, ha='right')
        fig.subplots_adjust(bottom=0.2)

        # Add labels to data points
        for i, price in enumerate(prices):
            ax.text(dates[i], price, f"${price:.2f}", ha='center', va='bottom')

        return fig
    
    # price_history = [{'date': '4/20/2023', 'price': 24.33}, {'date': '4/26/2023', 'price': 21.01}, {'date': '4/27/2023', 'price': 23.12}]
    # Retrieve price history data from database
    if recipeMode:
        price_history = get_recipe_price_history(id)
        # Create table layout
        table_data = [[row['date'], "$ {:.2f}".format(row['price'])] for row in price_history]
        table_headings = ['Date', 'Unit Price']
    else:
        # Create table layout
        price_history = get_price_history(id)
        table_data = [[row['date'], "$ {:.4f}".format(row['price']), row['supplier']] for row in price_history]
        table_headings = ['Date', 'Unit Price', 'Supplier']


    layout_table = [[sg.Table(values=table_data, headings=table_headings, num_rows=20, auto_size_columns=False)],[sg.VPush()]]
    layout_graph = [[sg.Canvas(key='-CANVAS-', border_width=5, background_color='red')]]
    layout = [
        [sg.Column(layout_table, expand_y=True), sg.Column(layout_graph)]
    ]

    # Create window
    window = sg.Window(f'Price History [{name}]', layout, finalize=True, icon=ICON)
    if len(price_history)>0:
        fig = generate_figure(price_history)
        tkcanvas = draw_figure(window['-CANVAS-'].TKCanvas, fig)

    # Event loop
    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == 'Exit':
            break

    # Close window
    window.close()

if __name__=='__main__':
    render(2)