-- Recursively expand recipes to component ingredients
DROP VIEW IF EXISTS recipe_ingredients_expanded;
CREATE VIEW recipe_ingredients_expanded AS
WITH RECURSIVE tree AS (
    SELECT ParentRecipe as Id, ParentRecipe, ChildRecipe, ChildIngredient, Quantity, 1 AS level
    FROM connections

    UNION ALL

    SELECT t.Id, c.ParentRecipe, c.ChildRecipe, c.ChildIngredient, c.Quantity * t.Quantity / r.OutputQty, t.level + 1
    FROM connections c
    INNER JOIN tree t ON c.ParentRecipe = t.ChildRecipe
    INNER JOIN recipes r ON t.ChildRecipe = r.Id
    WHERE t.ChildRecipe IS NOT NULL
)
SELECT Id AS recipe_id, ChildIngredient AS ingredient_id, Quantity, level
FROM tree
WHERE ChildIngredient IS NOT NULL;

DROP VIEW IF EXISTS RecipeTotalValues;
CREATE VIEW RecipeTotalValues 
AS SELECT 
  r.Id
  , COALESCE( SUM(i.Weight * rx.Quantity)/r.OutputQty , 0) AS Weight
  , COALESCE( SUM(i.Cost * rx.Quantity)/r.OutputQty , 0) AS Cost
  , COALESCE( SUM(i.Calories * rx.Quantity)/r.OutputQty , 0) AS Calories
  , COALESCE( SUM(i.TTLFatGrams * rx.Quantity)/r.OutputQty , 0) AS TTLFatGrams
  , COALESCE( SUM(i.SatFatGrams * rx.Quantity)/r.OutputQty , 0) AS SatFatGrams
  , COALESCE( SUM(i.CholesterolMilligrams * rx.Quantity)/r.OutputQty , 0) AS CholesterolMilligrams
  , COALESCE( SUM(i.SodiumMilligrams * rx.Quantity)/r.OutputQty , 0) AS SodiumMilligrams
  , COALESCE( SUM(i.CarbGrams * rx.Quantity)/r.OutputQty , 0) AS CarbGrams
  , COALESCE( SUM(i.FiberGrams * rx.Quantity)/r.OutputQty , 0) AS FiberGrams
  , COALESCE( SUM(i.SugarGrams * rx.Quantity)/r.OutputQty , 0) AS SugarGrams
  , COALESCE( SUM(i.ProteinGrams * rx.Quantity)/r.OutputQty , 0) AS ProteinGrams

 FROM Recipes r
 LEFT JOIN recipe_ingredients_expanded rx on rx.recipe_id=r.Id
 LEFT JOIN ingredients i ON rx.ingredient_id = i.id
 GROUP BY r.Id,r.OutputQty;

-- Join recipe data back to the result from view above
DROP VIEW IF EXISTS RecipesWithNutrition;
CREATE VIEW RecipesWithNutrition 
AS SELECT r.Name, r.Unit, r.OutputQty, rtv.* FROM Recipes r LEFT JOIN RecipeTotalValues rtv ON r.id=rtv.Id;

DROP VIEW IF EXISTS RecipeDetails;
CREATE VIEW RecipeDetails
AS SELECT Id
 , Name
 , Unit
 , OutputQty
 , CAST(Weight AS Int) AS Weight
 , '$' + CAST(ROUND(Cost, 2) AS Varchar) AS Cost
 , CAST(Calories AS Int) AS Calories
 , CAST(TTLFatGrams AS Int) AS TTLFatGrams
 , CAST(SatFatGrams AS Int) AS SatFatGrams
 , CAST(CholesterolMilligrams AS Int) AS CholesterolMilligrams
 , CAST(SodiumMilligrams AS Int) AS SodiumMilligrams
 , CAST(CarbGrams AS Int) AS CarbGrams
 , CAST(FiberGrams AS Int) AS FiberGrams
 , CAST(SugarGrams AS Int) AS SugarGrams
 , CAST(ProteinGrams AS Int) AS ProteinGrams
FROM RecipesWithNutrition;