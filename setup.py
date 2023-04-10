import sqlite3
import os

# def deleteDB():
#     if os.path.exists('builder.db'):
#         os.remove('builder.db')
#         print('builder.db deleted')
#     else:
#         print('builder.db does not exist')

def initializeDB():
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()

    with open('setup.sql','r') as f:
        sql = f.read()
    cursor.executescript(sql)

    connection.commit()
    connection.close()

    print('Database initialized')