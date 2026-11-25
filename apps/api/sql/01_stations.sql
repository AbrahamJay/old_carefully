-- 湘潭市岳塘区 · 社区站点基础数据
--
-- 作用：老人建档、下单、派单都要归属站点，清库重建后必须先有这批数据。
-- 幂等：按 name 判重，重复执行不会产生重复行（可安全地反复跑）。
--
-- 执行方式（任选其一）：
--   1) 本机（已开 SSH 隧道）：.venv/bin/python scripts/apply_sql.py
--   2) 服务器上：
--      docker exec -i pg psql -U socialoldcare -d socialoldcare < sql/01_stations.sql
--
-- 说明：address 只写到「街道 + 社区」，没有编造门牌号；
--       需要精确门牌的，登录后台编辑，或直接改本文件后重跑（幂等）。

INSERT INTO stations (name, street, address, active)
SELECT v.name, v.street, v.address, TRUE
FROM (VALUES
    (1, '霞光社区',   '五里堆街道', '湘潭市岳塘区五里堆街道霞光社区'),
    (2, '菊花塘社区', '建设路街道', '湘潭市岳塘区建设路街道菊花塘社区'),
    (3, '燕儿窝社区', '宝塔街道',   '湘潭市岳塘区宝塔街道燕儿窝社区'),
    (4, '晓塘社区',   '书院路街道', '湘潭市岳塘区书院路街道晓塘社区'),
    (5, '三义井社区', '东坪街道',   '湘潭市岳塘区东坪街道三义井社区'),
    (6, '瓦窑塘社区', '岳塘街道',   '湘潭市岳塘区岳塘街道瓦窑塘社区')
) AS v(sort_no, name, street, address)
WHERE NOT EXISTS (
    SELECT 1 FROM stations s WHERE s.name = v.name
)
-- 按写的顺序分配自增 id，保证「1 = 霞光社区」这类引用稳定
ORDER BY v.sort_no;
