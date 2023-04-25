DROP VIEW IF EXISTS RecipeTotalValues;
CREATE VIEW RecipeTotalValues 
AS 
WITH tree AS (
  SELECT ParentRecipe as Id, ParentRecipe, ChildRecipe, ChildIngredient, Quantity, 1 AS level
  FROM connections
  
  UNION ALL
  
  SELECT t.Id, c.ParentRecipe, c.ChildRecipe, c.ChildIngredient, c.Quantity*t.Quantity/r.OutputQty, t.level + 1
  FROM connections c
  INNER JOIN tree t ON c.ParentRecipe = t.ChildRecipe
  INNER JOIN Recipes r on t.ChildRecipe = r.Id
  WHERE t.ChildRecipe IS NOT NULL

)
SELECT 
  r.Id
  , COALESCE( SUM(i.Weight * t.Quantity)/r.OutputQty , 0) AS Weight
  , COALESCE( SUM(i.Cost * t.Quantity)/r.OutputQty , 0) AS Cost
  , COALESCE( SUM(i.Calories * t.Quantity)/r.OutputQty , 0) AS Calories
  , COALESCE( SUM(i.TTLFatGrams * t.Quantity)/r.OutputQty , 0) AS TTLFatGrams
  , COALESCE( SUM(i.SatFatGrams * t.Quantity)/r.OutputQty , 0) AS SatFatGrams
  , COALESCE( SUM(i.CholesterolMilligrams * t.Quantity)/r.OutputQty , 0) AS CholesterolMilligrams
  , COALESCE( SUM(i.SodiumMilligrams * t.Quantity)/r.OutputQty , 0) AS SodiumMilligrams
  , COALESCE( SUM(i.CarbGrams * t.Quantity)/r.OutputQty , 0) AS CarbGrams
  , COALESCE( SUM(i.FiberGrams * t.Quantity)/r.OutputQty , 0) AS FiberGrams
  , COALESCE( SUM(i.SugarGrams * t.Quantity)/r.OutputQty , 0) AS SugarGrams
  , COALESCE( SUM(i.ProteinGrams * t.Quantity)/r.OutputQty , 0) AS ProteinGrams

 FROM Recipes r
 LEFT JOIN tree t on t.Id=r.Id
 LEFT JOIN ingredients i ON t.ChildIngredient = i.id
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