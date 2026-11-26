-- 服务项目（8 项，下单与派单的前提）
--
-- 数据来源：dev.db 中已存在的 5 项（陪诊/保洁/适老化评估/代办/助餐），
--           补充 3 项以覆盖工作人员技能（助浴、水电维修、用药提醒）。
-- 幂等方式：code 是唯一业务键，用 ON CONFLICT DO UPDATE 只同步「文案类」字段
--           （name / category / description / duration_minutes / unit / sort）。
-- 价格与上架状态：price_cents、active 只在首次插入时写入，之后以后台运营修改为准，
--           重跑本文件不会把调过的价格或已下架的服务回滚。
-- 价格：price_cents 单位为「分」，25800 = 258.00 元（仅作新库的初始值）。

INSERT INTO services (
    code, name, category, description,
    price_cents, duration_minutes, unit, active, sort, required_skill
)
SELECT v.code, v.name, v.category, v.description,
       v.price_cents, v.duration_minutes, v.unit, TRUE, v.sort, v.required_skill
FROM (VALUES
    ('companion', '陪诊服务', 'companion',
     '挂号、取号、排队、陪同就诊、记录医嘱、取药（不含诊疗费用）',
     25800, 240, '半天', 1, '陪诊'),
    ('cleaning', '居家保洁', 'cleaning',
     '日常保洁 2 小时，合作家政上门，含厨卫清洁',
     15800, 120, '2小时', 2, '保洁'),
    ('renovation', '适老化评估', 'renovation',
     '防滑、扶手、洗澡椅、夜灯等上门评估并出具改造方案',
     9900, 90, '次', 3, '适老化评估'),
    ('errand', '代办跑腿', 'errand',
     '缴费、取药、买菜、寄取快递等日常代办',
     3000, 60, '次', 4, '代办'),
    ('meal', '助餐配送', 'meal',
     '合作社区食堂订餐并送餐上门（试点）',
     1500, 30, '餐', 5, '助餐'),
    ('bath', '上门助浴', 'bath',
     '携带防滑垫、洗澡椅上门协助洗浴，适合失能半失能老人',
     19800, 90, '次', 6, '助浴'),
    ('repair', '水电维修', 'repair',
     '换灯泡、修水龙头、疏通下水等居家小修，材料费另计',
     5000, 60, '次', 7, '水电维修'),
    ('medication', '用药提醒', 'medication',
     '上门核对药盒、协助分药并提醒按时服药',
     1000, 15, '次', 8, '用药提醒')
) AS v(code, name, category, description, price_cents, duration_minutes, unit, sort, required_skill)
ON CONFLICT (code) DO UPDATE SET
    name             = EXCLUDED.name,
    category         = EXCLUDED.category,
    description      = EXCLUDED.description,
    duration_minutes = EXCLUDED.duration_minutes,
    unit             = EXCLUDED.unit,
    sort             = EXCLUDED.sort,
    required_skill   = EXCLUDED.required_skill;
-- 刻意不更新 price_cents / active：运营调价、下架后重跑 SQL 不应被回滚
