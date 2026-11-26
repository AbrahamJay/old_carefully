"""组织资源：服务区域、员工、供给方。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...core.config import settings
from ...core.enums import AssignmentStatus, Role, StaffStatus, UserStatus
from ...core.errors import BadRequestError, NotFoundError
from ...core.time import business_day_start_utc, business_tz
from ...db.models import (
    Order,
    OrderAssignment,
    StaffLeave,
    StaffProfile,
    Station,
    Supplier,
    User,
)
from .schemas import (
    StaffCreate,
    StaffLeaveCreate,
    StaffOut,
    StaffUpdate,
    StationCreate,
    StationUpdate,
    SupplierCreate,
)


class StationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_active(self) -> list[Station]:
        return list(
            self._db.scalars(
                select(Station).where(Station.active.is_(True)).order_by(Station.id)
            ).all()
        )

    def list_all(self) -> list[Station]:
        return list(self._db.scalars(select(Station).order_by(Station.id)).all())

    def get(self, station_id: int) -> Station:
        station = self._db.get(Station, station_id)
        if station is None:
            raise NotFoundError("区域不存在")
        return station

    def create(self, payload: StationCreate) -> Station:
        name = payload.name.strip()
        if self._db.scalars(select(Station).where(Station.name == name)).first():
            raise BadRequestError("区域名称已存在")
        station = Station(
            name=name,
            street=payload.street.strip(),
            address=payload.address.strip(),
            active=payload.active,
        )
        self._db.add(station)
        self._db.commit()
        self._db.refresh(station)
        return station

    def update(self, station_id: int, payload: StationUpdate) -> Station:
        station = self.get(station_id)
        updates = payload.model_dump(exclude_unset=True)
        if updates.get("name") is not None:
            updates["name"] = updates["name"].strip()
        for field, value in updates.items():
            setattr(station, field, value)
        self._db.commit()
        self._db.refresh(station)
        return station


class StaffService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self, station_id: int | None = None) -> list[StaffOut]:
        stmt = (
            select(User)
            .options(selectinload(User.station))
            .where(User.role == Role.STAFF)
            .order_by(User.id)
        )
        if station_id:
            stmt = stmt.where(User.station_id == station_id)
        users = list(self._db.scalars(stmt).all())
        staff_ids = [user.id for user in users]
        loads = self._today_loads(staff_ids)
        on_leave = self._today_leave_ids(staff_ids)
        return [
            self.to_out(
                user,
                today_load=loads.get(user.id, 0),
                on_leave_today=user.id in on_leave,
            )
            for user in users
        ]

    def create(self, payload: StaffCreate) -> StaffOut:
        if self._db.scalars(select(User).where(User.phone == payload.phone)).first():
            raise BadRequestError("手机号已存在")

        station_id = payload.station_id or settings.default_station_id
        station = self._db.get(Station, station_id)
        if station is None:
            raise BadRequestError("服务区域不存在")

        user = User(
            name=payload.name,
            phone=payload.phone,
            role=Role.STAFF,
            status=UserStatus.ACTIVE,
            station_id=station_id,
        )
        self._db.add(user)
        self._db.flush()
        self._db.add(
            StaffProfile(
                user_id=user.id,
                supplier_id=payload.supplier_id,
                skills=payload.skills,
                status=StaffStatus.ACTIVE,
            )
        )
        self._db.commit()
        self._db.refresh(user)
        return self.to_out(user, on_leave_today=self._is_on_leave_today(user.id))

    def update(self, staff_id: int, payload: StaffUpdate) -> StaffOut:
        user = self._db.get(User, staff_id)
        if user is None or user.role != Role.STAFF:
            raise NotFoundError("员工不存在")

        profile = self._db.get(StaffProfile, staff_id)
        if profile is None:
            profile = StaffProfile(user_id=staff_id, skills=[], status=StaffStatus.ACTIVE)
            self._db.add(profile)

        if payload.name is not None:
            user.name = payload.name
        if payload.skills is not None:
            profile.skills = payload.skills
        if payload.status is not None:
            profile.status = payload.status
            user.status = (
                UserStatus.ACTIVE if payload.status == StaffStatus.ACTIVE else UserStatus.DISABLED
            )
        if payload.supplier_id is not None:
            profile.supplier_id = payload.supplier_id
        if payload.station_id is not None:
            if self._db.get(Station, payload.station_id) is None:
                raise BadRequestError("服务区域不存在")
            user.station_id = payload.station_id
        if payload.work_days is not None:
            profile.work_days = payload.work_days
        if payload.work_start_minute is not None:
            profile.work_start_minute = payload.work_start_minute
        if payload.work_end_minute is not None:
            profile.work_end_minute = payload.work_end_minute
        if payload.daily_capacity is not None:
            profile.daily_capacity = payload.daily_capacity
        if payload.accepting_orders is not None:
            profile.accepting_orders = payload.accepting_orders
        if profile.work_start_minute >= profile.work_end_minute:
            raise BadRequestError("上班时间必须早于下班时间")

        self._db.commit()
        self._db.refresh(user)
        return self.to_out(user, on_leave_today=self._is_on_leave_today(user.id))

    # ------------------------------------------------------------------ 请假
    def list_leaves(
        self,
        staff_id: int,
        *,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[StaffLeave]:
        self._require_staff(staff_id)
        stmt = select(StaffLeave).where(StaffLeave.staff_id == staff_id)
        if from_date is not None:
            stmt = stmt.where(StaffLeave.leave_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(StaffLeave.leave_date <= to_date)
        return list(self._db.scalars(stmt.order_by(StaffLeave.leave_date)).all())

    def add_leaves(self, staff_id: int, payload: StaffLeaveCreate) -> list[StaffLeave]:
        """按日期区间请假：区间内每天一条，已存在的当天记录只更新备注。"""
        self._require_staff(staff_id)
        start = payload.start_date
        end = payload.end_date or start
        reason = payload.reason.strip()
        existing = {
            leave.leave_date: leave
            for leave in self._db.scalars(
                select(StaffLeave).where(
                    StaffLeave.staff_id == staff_id,
                    StaffLeave.leave_date >= start,
                    StaffLeave.leave_date <= end,
                )
            ).all()
        }
        result: list[StaffLeave] = []
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            leave = existing.get(day)
            if leave is None:
                leave = StaffLeave(staff_id=staff_id, leave_date=day, reason=reason)
                self._db.add(leave)
            else:
                leave.reason = reason
            result.append(leave)
        self._db.commit()
        return result

    def delete_leaves(
        self,
        staff_id: int,
        *,
        from_date: date,
        to_date: date | None = None,
    ) -> int:
        """按日期区间整段删除，返回删除条数。"""
        self._require_staff(staff_id)
        end = to_date or from_date
        if end < from_date:
            raise BadRequestError("结束日期不能早于开始日期")
        leaves = list(
            self._db.scalars(
                select(StaffLeave).where(
                    StaffLeave.staff_id == staff_id,
                    StaffLeave.leave_date >= from_date,
                    StaffLeave.leave_date <= end,
                )
            ).all()
        )
        for leave in leaves:
            self._db.delete(leave)
        self._db.commit()
        return len(leaves)

    def delete_leave(self, staff_id: int, leave_id: int) -> None:
        leave = self._db.get(StaffLeave, leave_id)
        if leave is None or leave.staff_id != staff_id:
            raise NotFoundError("请假记录不存在")
        self._db.delete(leave)
        self._db.commit()

    def to_out(
        self,
        user: User,
        *,
        today_load: int = 0,
        on_leave_today: bool = False,
    ) -> StaffOut:
        profile = self._db.get(StaffProfile, user.id)
        return StaffOut(
            id=user.id,
            name=user.name,
            phone=user.phone,
            role=user.role,
            skills=profile.skills if profile else [],
            rating=profile.rating if profile else 5.0,
            status=profile.status if profile else user.status,
            station_id=user.station_id,
            station_name=user.station.name if user.station else "",
            work_days=profile.work_days if profile else [1, 2, 3, 4, 5, 6, 7],
            work_start_minute=profile.work_start_minute if profile else 480,
            work_end_minute=profile.work_end_minute if profile else 1080,
            daily_capacity=profile.daily_capacity if profile else 4,
            accepting_orders=profile.accepting_orders if profile else True,
            today_load=today_load,
            on_leave_today=on_leave_today,
        )

    # ------------------------------------------------------------------ 内部
    def _require_staff(self, staff_id: int) -> User:
        user = self._db.get(User, staff_id)
        if user is None or user.role != Role.STAFF:
            raise NotFoundError("员工不存在")
        return user

    def _today_loads(self, staff_ids: list[int]) -> dict[int, int]:
        """业务时区「今天」已派且未结束的单数，按员工聚合，避免逐人查询。"""
        if not staff_ids:
            return {}
        start = business_day_start_utc()
        end = business_day_start_utc(1)
        rows = self._db.execute(
            select(OrderAssignment.staff_id, func.count())
            .join(Order, Order.id == OrderAssignment.order_id)
            .where(
                OrderAssignment.staff_id.in_(staff_ids),
                OrderAssignment.status.in_(
                    (AssignmentStatus.ASSIGNED, AssignmentStatus.ACCEPTED)
                ),
                Order.scheduled_at >= start,
                Order.scheduled_at < end,
            )
            .group_by(OrderAssignment.staff_id)
        ).all()
        return {int(staff_id): int(count) for staff_id, count in rows}

    def _today_leave_ids(self, staff_ids: list[int]) -> set[int]:
        """业务时区今天请假的员工 id，用于列表「今日请假」徽标。"""
        if not staff_ids:
            return set()
        today = datetime.now(business_tz()).date()
        rows = self._db.scalars(
            select(StaffLeave.staff_id).where(
                StaffLeave.staff_id.in_(staff_ids),
                StaffLeave.leave_date == today,
            )
        ).all()
        return {int(staff_id) for staff_id in rows}

    def _is_on_leave_today(self, staff_id: int) -> bool:
        return bool(self._today_leave_ids([staff_id]))


class SupplierService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list(self) -> list[Supplier]:
        return list(self._db.scalars(select(Supplier).order_by(Supplier.id)).all())

    def create(self, payload: SupplierCreate) -> Supplier:
        supplier = Supplier(**payload.model_dump())
        self._db.add(supplier)
        self._db.commit()
        self._db.refresh(supplier)
        return supplier

    def update(self, supplier_id: int, payload: SupplierCreate) -> Supplier:
        supplier = self._db.get(Supplier, supplier_id)
        if supplier is None:
            raise NotFoundError("供给方不存在")
        for field, value in payload.model_dump().items():
            setattr(supplier, field, value)
        self._db.commit()
        self._db.refresh(supplier)
        return supplier
