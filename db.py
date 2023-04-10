import sqlite3

def query():
    connection = sqlite3.connect("builder.db")
    # connection.row_factory = lambda cursor, row: [row[0],row[1],row[2],row[3]]
    # connection.row_factory = sqlite3.Row
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM RecipeDetails")
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)

def recipeinfo(id: int):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        SELECT Id, Name, Unit, OutputQty
        FROM Recipes
        WHERE Id={id}
        ;
    ''')
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)

def recipedetails(id: int):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        SELECT COALESCE(r.Name, i.Name) AS Name 
        , c.Quantity
        , COALESCE(i.Unit, r.Unit) AS Unit
        ,  CASE 
            WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
            ELSE 'ingredient'
            END AS Type
        , ROUND(COALESCE(r.Cost, i.Cost) * c.Quantity,2) AS Cost
        FROM Connections c
        LEFT JOIN RecipesWithNutrition r on r.Id=c.ChildRecipe
        LEFT JOIN Ingredients i on i.Id=c.ChildIngredient
        WHERE c.ParentRecipe={id}
        ;
    ''')
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)

def updaterecipe(id: int, name: str, unit: str, outputqty):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        UPDATE Recipes
        SET Name='{name}', Unit='{unit}', OutputQty={outputqty}
        WHERE Id={id}
    ''')
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)