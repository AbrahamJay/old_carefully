-- 清空全部业务数据（只保留数据库实例本身）
--
-- ⚠️ 不可恢复。执行后必须按顺序重建：
--   1) .venv/bin/alembic upgrade head                          # 重建 17 张表
--   2) .venv/bin/python scripts/apply_sql.py                   # 6 个社区站点
--   3) .venv/bin/python scripts/create_admin.py --phone 手机号 --name 姓名
--
-- 为什么放在 reset/ 子目录：scripts/apply_sql.py 默认只跑 sql/*.sql，
-- 不会递归子目录，避免误把清库脚本当基础数据执行。
--
-- 执行方式（任选其一）：
--   1) 本机（已开 SSH 隧道）：.venv/bin/python scripts/apply_sql.py sql/reset
--   2) 服务器上：
--      docker exec -i pg psql -U socialoldcare -d socialoldcare < sql/reset/reset_all.sql
--
-- 注意：会一并删掉 alembic_version，所以第 1 步的 upgrade 是必须的。

DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO socialoldcare;
GRANT ALL ON SCHEMA public TO public;
