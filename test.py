import sqlite3

def query():
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM RecipeDetails")
    records = cursor.fetchall()
    print(records)
    connection.commit()
    connection.close()

def recipedetails():
    connection = sqlite3.connect("builder.db")
    cursor = connection.cursor()
    cursor.execute("""
        SELECT COALESCE(r.Name, i.Name) AS Name 
        , c.Quantity
        , COALESCE(i.Unit, r.Unit) AS Unit
        ,  CASE 
            WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
            ELSE 'ingredient'
            END AS Type
        , COALESCE(r.Cost, i.Cost) * c.Quantity AS Cost
        FROM Connections c
        LEFT JOIN RecipesWithNutrition r on r.Id=c.ChildRecipe
        LEFT JOIN Ingredients i on i.Id=c.ChildIngredient
        WHERE c.ParentRecipe=16
        ;
    """)
    records = cursor.fetchall()
    connection.commit()
    connection.close()
    return(records)



print (recipedetails())