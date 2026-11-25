-- 家属（20 位）与工作人员（6 位）账号基础数据
--
-- 依赖：01_stations.sql（station_id 引用 1~6）
-- 幂等：users 按 phone 判重，staff_profiles 按 user_id 判重，可反复执行
-- 登录方式：家属与工作人员统一初始密码 123456（argon2id 哈希在文件末的 UPDATE 里，仅用于测试数据）；
--           管理员密码由 scripts/create_admin.py 单独管理。
-- 尚未包含：家属与老人的绑定（family_bindings）——需要先有老人档案，见后续 SQL。
--
-- 手机号说明：均为虚构号段（1390732xxxx 湘潭风格 / 1735268xxxx 与管理员同段），
--             不指向真实用户，接入短信前请勿用于生产触达。

-- ---------------------------------------------------------------- 家属 20 位
-- 密码不在这里写：文件末统一 UPDATE 一次性给家属与工作人员补初始密码。
INSERT INTO users (openid, phone, name, role, password_hash, status, station_id, created_at, updated_at)
SELECT NULL, v.phone, v.name, 'customer', NULL, 'active', v.station_id, now(), now()
FROM (VALUES
    ('13907320001', '王秀兰', 1),
    ('13907320002', '李建国', 2),
    ('13907320003', '张丽华', 3),
    ('13907320004', '刘志强', 4),
    ('13907320005', '陈美玲', 5),
    ('13907320006', '杨海燕', 6),
    ('13907320007', '周文斌', 1),
    ('13907320008', '黄小琴', 2),
    ('13907320009', '赵国庆', 3),
    ('13907320010', '吴春梅', 4),
    ('13907320011', '徐志远', 5),
    ('13907320012', '孙丽萍', 6),
    ('13907320013', '马建军', 1),
    ('13907320014', '朱晓红', 2),
    ('13907320015', '胡国强', 3),
    ('13907320016', '郭永红', 4),
    ('13907320017', '何文军', 5),
    ('13907320018', '高秀英', 6),
    ('13907320019', '林志刚', 1),
    ('13907320020', '罗红梅', 2)
) AS v(phone, name, station_id)
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.phone = v.phone)
ORDER BY v.phone;

-- ------------------------------------------------------------ 工作人员 6 位
INSERT INTO users (openid, phone, name, role, password_hash, status, station_id, created_at, updated_at)
SELECT NULL, v.phone, v.name, 'staff', NULL, 'active', v.station_id, now(), now()
FROM (VALUES
    ('17352680001', '王桂芳', 1),
    ('17352680002', '李秀珍', 2),
    ('17352680003', '陈玉梅', 3),
    ('17352680004', '周建平', 4),
    ('17352680005', '谭志强', 5),
    ('17352680006', '张翠兰', 6)
) AS v(phone, name, station_id)
WHERE NOT EXISTS (SELECT 1 FROM users u WHERE u.phone = v.phone)
ORDER BY v.phone;

-- ------------------------------------------- 家属与工作人员：统一初始密码 123456
-- argon2id 哈希写成固定值，所有测试账号复用同一串（避免把 97 字符重复 20+ 次）；
-- 只补空值，不覆盖以后改过的密码；管理员（role=admin）不在此列，其密码由 create_admin.py 管理；
-- 需要换密码时重新生成哈希替换。
UPDATE users
SET password_hash = '$argon2id$v=19$m=65536,t=3,p=4$uFInYaDb2W7hszr/mwz7cw$QBNTNIFiaJdNolnW46YDLVLmX9QEwQJR+QjSFARkbPc',
    updated_at = now()
WHERE role IN ('customer', 'staff') AND password_hash IS NULL;

-- ------------------------------------------------------- 工作人员档案（技能/评分）
INSERT INTO staff_profiles (user_id, supplier_id, skills, rating, status)
SELECT u.id, NULL, v.skills::jsonb, v.rating, 'active'
FROM (VALUES
    ('17352680001', '["保洁","陪诊","代办"]',            4.9),
    ('17352680002', '["陪诊","用药提醒","代办"]',        4.7),
    ('17352680003', '["保洁","适老化评估"]',             4.5),
    ('17352680004', '["水电维修","适老化改造"]',         4.8),
    ('17352680005', '["陪诊","代办","助浴"]',            4.6),
    ('17352680006', '["保洁","助浴","用药提醒"]',        4.4)
) AS v(phone, skills, rating)
JOIN users u ON u.phone = v.phone
WHERE NOT EXISTS (SELECT 1 FROM staff_profiles sp WHERE sp.user_id = u.id);
