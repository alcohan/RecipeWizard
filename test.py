import sqlite3

def query(id):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f"SELECT * FROM RecipeDetails WHERE Id={id}")
    columns = [description[0] for description in cursor.description]
    records = cursor.fetchall()
    results = []
    for record in records:
        result_dict = dict(zip(columns,record))
        results.append(result_dict)
    connection.commit()
    connection.close()

    return results
    
dict = query(9)[0]
print(dict.values())