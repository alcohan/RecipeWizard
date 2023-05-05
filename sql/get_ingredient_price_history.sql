SELECT 
    p.effective_date AS date
    , p.unit_price AS price 
    , s.name AS supplier
FROM ingredient_prices p
LEFT JOIN suppliers s ON p.supplier_id = s.id
WHERE ingredient_id = ?
ORDER BY p.effective_date ASC;