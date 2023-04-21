SELECT r.*
    , Count(c.ParentRecipe) As Components 
    , r.Id
FROM RecipeDetails r
LEFT JOIN Connections c ON r.Id = C.ParentRecipe
{filter}
GROUP BY r.Id