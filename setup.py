import sqlite3
import config

# def deleteDB():
#     if os.path.exists('builder.db'):
#         os.remove('builder.db')
#         print('builder.db deleted')
#     else:
#         print('builder.db does not exist')

def initializeDB():
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()

    for file in ('sql/setup/tables.sql', 'sql/setup/views.sql','sql/setup/sampledata.sql'):
        print(f'Executing script {file}')
        sql = config.get_resource(file)
        cursor.executescript(sql)

    connection.commit()
    connection.close()

    print('Database initialized')

if __name__=="__main__":
    initializeDB()