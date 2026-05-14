SELECT r.*
    , Count(c.ParentRecipe) As Components
    , r.Id
    , (SELECT t.name FROM tags t
        JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
        WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagName
    , (SELECT t.color FROM tags t
        JOIN recipe_tags_mapping rtm ON rtm.tag_id=t.id
        WHERE rtm.recipe_id=r.Id AND t.kind='recipe' LIMIT 1) AS TagColor
FROM RecipeDetails r
LEFT JOIN Connections c ON r.Id = C.ParentRecipe
{filter}
GROUP BY r.Id
ORDER BY Name COLLATE NOCASE ASC