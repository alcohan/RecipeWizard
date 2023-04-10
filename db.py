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
        SELECT Name, Unit, OutputQty, Id
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
        , COALESCE(r.Id, i.Id) AS Id
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

# Get the eligible ingredients for a given recipe 
def get_eligible_ingredients(id: int):
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        -- Get all eligible recipes (avoiding circular references)
        WITH tree AS (
            SELECT {id} AS ParentRecipe
            
            UNION ALL
            
            SELECT c.ParentRecipe
            FROM connections c
            INNER JOIN tree ON c.ChildRecipe = tree.ParentRecipe
        )
        SELECT Id, 'recipe' AS Type, Name, Unit
        FROM Recipes
        WHERE id NOT IN (
            SELECT ParentRecipe FROM tree
        )

        UNION
        SELECT Id, 'ingredient' AS Type, Name, Unit
        FROM Ingredients
        ORDER BY Name;
    ''')
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)

def add_ingredient(parent: int, mode: str, child: int, qty: float):
    if mode=='ingredient':
        recipe = 'NULL'
        ingredient = child
    if mode == 'recipe':
        recipe = child
        ingredient = 'NULL'

    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        INSERT INTO Connections Values 
        ({parent},{recipe},{ingredient},{qty});
    ''')
    connection.commit()
    connection.close()
    return()

def update_ingredient(parent: int, mode: str, child: int, qty: float):
    if mode=='ingredient':
        filter=f'AND ChildIngredient={child}'
    if mode == 'recipe':
        filter=f'AND ChildRecipe={child}'

    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute(f'''
        UPDATE Connections SET Quantity={qty}
        WHERE ParentRecipe={parent}
        {filter}
        ;
    ''')
    connection.commit()
    connection.close()
    return()