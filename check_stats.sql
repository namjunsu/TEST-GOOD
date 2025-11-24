SELECT 
    COUNT(*) as total,
    SUM(CASE WHEN drafter IS NOT NULL AND drafter != '' THEN 1 ELSE 0 END) as with_drafter,
    SUM(CASE WHEN filename LIKE '2017-%' THEN 1 ELSE 0 END) as files_2017,
    SUM(CASE WHEN filename LIKE '2017-%' AND drafter IS NOT NULL AND drafter != '' THEN 1 ELSE 0 END) as drafters_2017
FROM documents;
