# Import Module
from tkinter import Tk
from tkhtmlview import HTMLLabel, RenderHTML

# Create Object
root = Tk()

# Set Geometry
# root.geometry("400x400")

# Add label

my_label = HTMLLabel(root, html=RenderHTML('static/template.html'))
my_label.pack(fill="both",expand=True)
my_label.fit_height()

# Adjust label
# my_label.pack(pady=20, padx=20)

# Execute Tkinter
root.mainloop()
