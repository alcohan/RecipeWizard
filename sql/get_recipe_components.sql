SELECT COALESCE(r.Name, i.Name) AS Name
    , c.Quantity
    , COALESCE(i.Unit, r.Unit) AS Unit
    ,  CASE
        WHEN c.ChildRecipe IS NOT NULL THEN 'recipe'
        ELSE 'ingredient'
        END AS Type
    , ROUND(COALESCE(r.Cost, i.Cost) * c.Quantity,2) AS Cost
    , COALESCE(r.Calories, i.Calories, 0) * c.Quantity AS Calories
    -- Allergens this component brings in: an ingredient's own, or the
    -- rolled-up set of a sub-recipe.
    , CASE WHEN c.ChildRecipe IS NOT NULL THEN
        (SELECT group_concat(name, ', ') FROM
            (SELECT DISTINCT a.name FROM RecipeAllergens ra
             JOIN allergens a ON a.id = ra.allergen_id
             WHERE ra.recipe_id = c.ChildRecipe ORDER BY a.sortOrder, a.id))
      ELSE
        (SELECT group_concat(name, ', ') FROM
            (SELECT a.name FROM ingredient_allergens ia
             JOIN allergens a ON a.id = ia.allergen_id
             WHERE ia.ingredient_id = c.ChildIngredient ORDER BY a.sortOrder, a.id))
      END AS Allergens
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
-- Components shown in the editor include template-added rows (marked
-- "template" in the grid), except packaging the template added: those
-- would clutter every recipe of the format, and the editor's template
-- line names them instead. Packaging the user added themselves stays
-- listed so it can be edited or removed. Cost and nutrition rollups
-- still see every Connections row via the views, so packaging always
-- factors into recipe cost.
WHERE c.ParentRecipe = ?
  AND NOT (
    c.from_template_tag_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM ingredient_tags_mapping itm
      JOIN tags t ON t.id = itm.tag_id
      WHERE itm.ingredient_id = c.ChildIngredient
        AND t.kind = 'ingredient' AND t.name = 'Packaging'
    )
  )
ORDER BY c.SortOrder, c.rowid