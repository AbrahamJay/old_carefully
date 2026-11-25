"""演示数据。

仅在 ``AUTO_SEED=true``（本地/演示环境）时执行，生产环境由配置校验强制关闭。
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.enums import (
    AssignmentStatus,
    BindingStatus,
    OrderStatus,
    PaymentProvider,
    PaymentRecordStatus,
    PaymentStatus,
    Role,
    StaffStatus,
    UserStatus,
)
from ..core.ids import new_order_no
from ..core.security import hash_password
from ..core.time import utcnow
from ..domain.pricing import calc_deposit
from .models import (
    Elder,
    FamilyBinding,
    Order,
    OrderAssignment,
    Payment,
    Review,
    Service,
    ServiceRecord,
    StaffProfile,
    Station,
    Supplier,
    User,
)
from .session import SessionLocal


def seed(db: Session | None = None) -> None:
    own_session = db is None
    session = db or SessionLocal()
    try:
        if session.scalars(select(User).where(User.phone == "13900000000")).first():
            return

        station = Station(
            name="湘潭市·示范街道综合养老服务中心",
            street="示范街道",
            address="示范社区 1 号",
            active=True,
        )
        session.add(station)
        session.flush()

        admin = User(
            name="管理员",
            phone="13900000000",
            role=Role.ADMIN,
            password_hash=hash_password(settings.seed_admin_password),
            status=UserStatus.ACTIVE,
            station_id=station.id,
        )
        # 演示账号（家属 + 工作人员）的初始密码，与 sql/02_members.sql 保持一致
        demo_password = hash_password("123456")
        customer1 = User(
            name="张女士",
            phone="13800000001",
            role=Role.CUSTOMER,
            password_hash=demo_password,
            status=UserStatus.ACTIVE,
        )
        customer2 = User(
            name="李先生",
            phone="13800000004",
            role=Role.CUSTOMER,
            password_hash=demo_password,
            status=UserStatus.ACTIVE,
        )
        staff1 = User(
            name="王阿姨",
            phone="13800000002",
            role=Role.STAFF,
            password_hash=demo_password,
            status=UserStatus.ACTIVE,
            station_id=station.id,
        )
        staff2 = User(
            name="李师傅",
            phone="13800000003",
            role=Role.STAFF,
            password_hash=demo_password,
            status=UserStatus.ACTIVE,
            station_id=station.id,
        )
        session.add_all([admin, customer1, customer2, staff1, staff2])
        session.flush()

        supplier1 = Supplier(
            name="湘潭安心家政",
            category="cleaning",
            contact_name="周经理",
            contact_phone="0731-0000001",
            contract_status="signed",
            insurance_status="valid",
        )
        supplier2 = Supplier(
            name="湖南适老化改造服务部",
            category="renovation",
            contact_name="刘工",
            contact_phone="0731-0000002",
            contract_status="signed",
            insurance_status="valid",
        )
        session.add_all([supplier1, supplier2])
        session.flush()

        session.add_all(
            [
                StaffProfile(
                    user_id=staff1.id,
                    supplier_id=supplier1.id,
                    skills=["保洁", "陪诊", "代办"],
                    status=StaffStatus.ACTIVE,
                ),
                StaffProfile(
                    user_id=staff2.id,
                    supplier_id=supplier2.id,
                    skills=["陪诊", "适老化评估"],
                    status=StaffStatus.ACTIVE,
                ),
            ]
        )

        services = [
            Service(
                code="companion",
                name="陪诊服务",
                category="companion",
                description="挂号、取号、排队、陪同就诊、记录医嘱、取药（不含诊疗）",
                price_cents=25800,
                duration_minutes=240,
                unit="半天",
                sort=1,
            ),
            Service(
                code="cleaning",
                name="居家保洁",
                category="cleaning",
                description="日常保洁 2 小时，合作家政上门",
                price_cents=15000,
                duration_minutes=120,
                unit="2小时",
                sort=2,
            ),
            Service(
                code="renovation",
                name="适老化评估",
                category="renovation",
                description="防滑、扶手、洗澡椅、夜灯等上门评估与方案",
                price_cents=9900,
                duration_minutes=90,
                unit="次",
                sort=3,
            ),
            Service(
                code="errand",
                name="代办跑腿",
                category="errand",
                description="缴费、取药、买菜、寄取快递",
                price_cents=3000,
                duration_minutes=60,
                unit="次",
                sort=4,
            ),
            Service(
                code="meal",
                name="助餐配送",
                category="meal",
                description="合作社区食堂订餐与配送（试点）",
                price_cents=1500,
                duration_minutes=30,
                unit="餐",
                sort=5,
            ),
        ]
        session.add_all(services)
        session.flush()

        elders = [
            Elder(
                station_id=station.id,
                name="张爷爷",
                gender="male",
                birth_year=1942,
                phone="13700000001",
                address="示范社区 3 栋 201",
                community="示范社区",
                health_notes="高血压，行动尚可，需陪同复查",
                emergency_name="张女士",
                emergency_phone="13800000001",
                invite_code="DEMO01",
                created_by=customer1.id,
            ),
            Elder(
                station_id=station.id,
                name="李奶奶",
                gender="female",
                birth_year=1948,
                phone="13700000002",
                address="示范社区 5 栋 102",
                community="示范社区",
                health_notes="膝关节不好，家里需要防滑和扶手",
                emergency_name="李先生",
                emergency_phone="13800000004",
                invite_code="DEMO02",
                created_by=customer2.id,
            ),
            Elder(
                station_id=station.id,
                name="王爷爷",
                gender="male",
                birth_year=1939,
                phone="13700000003",
                address="示范社区 1 栋 301",
                community="示范社区",
                health_notes="独居，子女在外地，需要定期探望",
                emergency_name="王女士",
                emergency_phone="13800000005",
                invite_code="DEMO03",
                created_by=customer1.id,
            ),
        ]
        session.add_all(elders)
        session.flush()

        session.add_all(
            [
                FamilyBinding(
                    user_id=customer1.id,
                    elder_id=elders[0].id,
                    relation="女儿",
                    status=BindingStatus.ACTIVE,
                ),
                FamilyBinding(
                    user_id=customer1.id,
                    elder_id=elders[2].id,
                    relation="女儿",
                    status=BindingStatus.ACTIVE,
                ),
                FamilyBinding(
                    user_id=customer2.id,
                    elder_id=elders[1].id,
                    relation="儿子",
                    status=BindingStatus.ACTIVE,
                ),
            ]
        )

        now = utcnow()

        # 1) 待确认
        order1 = Order(
            order_no=new_order_no(),
            station_id=station.id,
            elder_id=elders[0].id,
            customer_id=customer1.id,
            service_id=services[0].id,
            status=OrderStatus.PENDING_CONFIRM,
            scheduled_at=now + timedelta(days=1),
            address=elders[0].address,
            contact_name="张女士",
            contact_phone="13800000001",
            notes="周三上午湘雅医院复查，需要提前取号",
            amount_cents=25800,
            deposit_cents=calc_deposit(25800),
        )
        # 2) 已派单
        order2 = Order(
            order_no=new_order_no(),
            station_id=station.id,
            elder_id=elders[1].id,
            customer_id=customer2.id,
            service_id=services[1].id,
            status=OrderStatus.ASSIGNED,
            scheduled_at=now + timedelta(days=2),
            address=elders[1].address,
            contact_name="李先生",
            contact_phone="13800000004",
            notes="日常保洁，重点厨房和卫生间",
            amount_cents=15000,
            deposit_cents=calc_deposit(15000),
        )
        # 3) 服务中
        order3 = Order(
            order_no=new_order_no(),
            station_id=station.id,
            elder_id=elders[0].id,
            customer_id=customer1.id,
            service_id=services[3].id,
            status=OrderStatus.IN_SERVICE,
            scheduled_at=now,
            address=elders[0].address,
            contact_name="张女士",
            contact_phone="13800000001",
            notes="代取降压药",
            amount_cents=3000,
            deposit_cents=calc_deposit(3000),
        )
        # 4) 已完成 + 已收款 + 已评价
        order4 = Order(
            order_no=new_order_no(),
            station_id=station.id,
            elder_id=elders[2].id,
            customer_id=customer1.id,
            service_id=services[3].id,
            status=OrderStatus.COMPLETED,
            scheduled_at=now - timedelta(days=3),
            address=elders[2].address,
            contact_name="张女士",
            contact_phone="13800000001",
            notes="代缴水电费",
            amount_cents=3000,
            deposit_cents=calc_deposit(3000),
            payment_status=PaymentStatus.PAID_OFFLINE,
        )
        session.add_all([order1, order2, order3, order4])
        session.flush()

        session.add_all(
            [
                OrderAssignment(
                    order_id=order2.id,
                    staff_id=staff1.id,
                    status=AssignmentStatus.ACCEPTED,
                ),
                OrderAssignment(
                    order_id=order3.id,
                    staff_id=staff2.id,
                    status=AssignmentStatus.ACCEPTED,
                ),
                OrderAssignment(
                    order_id=order4.id,
                    staff_id=staff1.id,
                    status=AssignmentStatus.COMPLETED,
                    completed_at=now - timedelta(days=3),
                ),
            ]
        )
        session.add(
            ServiceRecord(
                order_id=order4.id,
                staff_id=staff1.id,
                content="已到老人家中确认需求，代缴水电费 186 元，票据已交给老人。",
                photos=[],
                elder_confirmed=True,
            )
        )
        session.add(
            Payment(
                order_id=order4.id,
                provider=PaymentProvider.OFFLINE,
                amount_cents=3000,
                status=PaymentRecordStatus.PAID,
                transaction_id="OFFLINE-SEED-0001",
                raw={"method": "wechat_transfer"},
            )
        )
        session.add(
            Review(
                order_id=order4.id,
                customer_id=customer1.id,
                rating=5,
                content="小王很耐心，办完还把票据拍照发给我了。",
            )
        )
        session.commit()
    finally:
        if own_session:
            session.close()


if __name__ == "__main__":
    seed()
    print("seed done")
