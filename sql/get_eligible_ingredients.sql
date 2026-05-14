-- Get all eligible recipes (avoiding circular references). Each row also
-- carries the component's tag name + color for the badge painted by the
-- picker delegate — recipes show their format tag, ingredients their
-- category tag. NULLs are fine; the delegate renders a generic fallback.
WITH tree AS (
    SELECT ? AS ParentRecipe

    UNION ALL

    SELECT c.ParentRecipe
    FROM connections c
    INNER JOIN tree ON c.ChildRecipe = tree.ParentRecipe
)
SELECT r.Id, 'recipe' AS Type, r.Name, r.Unit,
    (SELECT t.name FROM tags t JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
     WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagName,
    (SELECT t.color FROM tags t JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
     WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagColor
FROM Recipes r
WHERE r.Id NOT IN (SELECT ParentRecipe FROM tree)

UNION
SELECT i.Id, 'ingredient' AS Type, i.Name, i.Unit,
    (SELECT t.name FROM tags t JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
     WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagName,
    (SELECT t.color FROM tags t JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
     WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagColor
FROM Ingredients i
ORDER BY Name;