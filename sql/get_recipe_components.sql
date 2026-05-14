SELECT COALESCE(r.Name, i.Name) AS Name
    , c.Quantity
    , COALESCE(i.Unit, r.Unit) AS Unit
    ,  CASE
        WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
        ELSE 'ingredient'
        END AS Type
    , ROUND(COALESCE(r.Cost, i.Cost) * c.Quantity,2) AS Cost
    , COALESCE(r.Id, i.Id) AS Id
    , c.SortOrder AS SortOrder
    , c.from_template_tag_id AS FromTemplateTagId
    , (SELECT t.name FROM tags t
        JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
        WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagName
    , (SELECT t.color FROM tags t
        JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
        WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagColor
FROM Connections c
LEFT JOIN RecipesWithNutrition r on r.Id=c.ChildRecipe
LEFT JOIN Ingredients i on i.Id=c.ChildIngredient
-- Components shown in the editor and wedge include template-added rows
-- (the user sees a "added by template" marker in the model), but
-- exclude anything tagged Packaging — packaging items aren't visually
-- meaningful and would clutter both the list and the wedge. Cost and
-- nutrition rollups still see every Connections row via the views, so
-- packaging continues to factor into recipe cost.
WHERE c.ParentRecipe = ?
  AND NOT EXISTS (
    SELECT 1 FROM ingredient_tags_mapping itm
    JOIN tags t ON t.id = itm.tag_id
    WHERE itm.ingredient_id = c.ChildIngredient
      AND t.kind = 'ingredient' AND t.name = 'Packaging'
  )
ORDER BY c.SortOrder, c.rowid