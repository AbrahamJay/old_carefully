from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...api.deps import get_current_user, get_order_service, require_roles
from ...api.schemas import Page
from ...core.enums import Role
from ...db.models import Order, User
from .presenters import to_detail, to_list_item, to_record
from .schemas import (
    AssignIn,
    OrderCreate,
    OrderDetailOut,
    OrderListItem,
    PaymentMarkIn,
    RecordCreate,
    RecordOut,
    ReviewCreate,
    ReviewOut,
)
from .service import OrderService

router = APIRouter(tags=["订单"])


def _detail(service: OrderService, order: Order) -> OrderDetailOut:
    return to_detail(order, service.totals_of(order))


def _page(service: OrderService, orders: list[Order], total: int, page: int, page_size: int):
    return Page[OrderListItem](
        items=[to_list_item(order, service.totals_of(order)) for order in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/orders", response_model=OrderDetailOut, status_code=201)
def create_order(
    payload: OrderCreate,
    user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.create(user, payload))


@router.get("/orders", response_model=Page[OrderListItem])
def list_orders(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> Page[OrderListItem]:
    orders, total = service.list_page(user, status=status, page=page, page_size=page_size)
    return _page(service, orders, total, page, page_size)


@router.get("/orders/{order_id}", response_model=OrderDetailOut)
def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.get_for_actor(user, order_id))


@router.post("/orders/{order_id}/cancel", response_model=OrderDetailOut)
def cancel_order(
    order_id: int,
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.cancel(user, order_id))


@router.post("/orders/{order_id}/confirm", response_model=OrderDetailOut)
def confirm_order(
    order_id: int,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.confirm(user, order_id))


@router.post("/orders/{order_id}/assign", response_model=OrderDetailOut)
def assign_order(
    order_id: int,
    payload: AssignIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.assign(user, order_id, payload.staff_id))


@router.post("/orders/{order_id}/accept", response_model=OrderDetailOut)
def accept_order(
    order_id: int,
    user: User = Depends(require_roles(Role.STAFF)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.accept(user, order_id))


@router.post("/orders/{order_id}/start", response_model=OrderDetailOut)
def start_order(
    order_id: int,
    user: User = Depends(require_roles(Role.STAFF)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.start(user, order_id))


@router.post("/orders/{order_id}/complete", response_model=OrderDetailOut)
def complete_order(
    order_id: int,
    user: User = Depends(require_roles(Role.STAFF)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.complete(user, order_id))


@router.post("/orders/{order_id}/pay", response_model=OrderDetailOut)
def pay_order(
    order_id: int,
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.pay(user, order_id))


@router.post("/orders/{order_id}/pay-offline", response_model=OrderDetailOut)
def mark_paid(
    order_id: int,
    payload: PaymentMarkIn,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.pay_offline(user, order_id, method=payload.method))


@router.post("/orders/{order_id}/refund", response_model=OrderDetailOut)
def refund_order(
    order_id: int,
    user: User = Depends(require_roles(Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.refund(user, order_id))


@router.post("/orders/{order_id}/review", response_model=ReviewOut, status_code=201)
def review_order(
    order_id: int,
    payload: ReviewCreate,
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: OrderService = Depends(get_order_service),
) -> ReviewOut:
    return ReviewOut.model_validate(service.review(user, order_id, payload))


@router.post("/orders/{order_id}/records", response_model=RecordOut, status_code=201)
def create_record(
    order_id: int,
    payload: RecordCreate,
    user: User = Depends(require_roles(Role.STAFF)),
    service: OrderService = Depends(get_order_service),
) -> RecordOut:
    return to_record(service.add_record(user, order_id, payload))


@router.get("/orders/{order_id}/records", response_model=list[RecordOut])
def list_records(
    order_id: int,
    user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> list[RecordOut]:
    return [to_record(record) for record in service.list_records(user, order_id)]


@router.post("/orders/{order_id}/confirm-service", response_model=OrderDetailOut)
def confirm_service(
    order_id: int,
    user: User = Depends(require_roles(Role.CUSTOMER)),
    service: OrderService = Depends(get_order_service),
) -> OrderDetailOut:
    return _detail(service, service.confirm_service(user, order_id))


@router.get("/admin/orders", response_model=Page[OrderListItem])
def admin_orders(
    status: str | None = Query(default=None),
    station_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_roles(Role.ADMIN)),
    service: OrderService = Depends(get_order_service),
) -> Page[OrderListItem]:
    orders, total = service.admin_page(
        status=status,
        station_id=station_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return _page(service, orders, total, page, page_size)
