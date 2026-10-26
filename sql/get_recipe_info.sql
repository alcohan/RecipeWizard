SELECT r.*
    , rec.menu_price AS MenuPrice
    , rec.cost_snapshot AS CostSnapshot
    , rec.cost_snapshot_at AS CostSnapshotAt
    , rtv.Cost AS CostRaw  -- unformatted numeric cost for food-cost math
    , Count(c.ParentRecipe) As Components
    , r.Id
    , (SELECT t.name FROM tags t
        JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
        WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagName
    , (SELECT t.color FROM tags t
        JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
        WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagColor
FROM RecipeDetails r
JOIN Recipes rec ON rec.Id = r.Id
LEFT JOIN RecipeTotalValues rtv ON rtv.Id = r.Id
LEFT JOIN Connections c ON r.Id = C.ParentRecipe
{filter}
GROUP BY r.Id
ORDER BY Name COLLATE NOCASE ASC