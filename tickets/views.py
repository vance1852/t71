from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.contrib.auth import authenticate
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Hall,
    OrderSeat,
    Performance,
    PerformanceSeat,
    PerformanceSeatPrice,
    SeatTemplate,
    Show,
    TicketOrder,
)
from .serializers import (
    GenerateSeatsSerializer,
    HallSeatInitSerializer,
    HallSerializer,
    LockSeatsSerializer,
    LoginSerializer,
    PerformanceSerializer,
    PerformanceSeatPriceSerializer,
    PerformanceSeatSerializer,
    SeatTemplateSerializer,
    ShowSerializer,
    TicketOrderSerializer,
)

LOCK_MINUTES = 10


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(username=s.validated_data["username"], password=s.validated_data["password"])
        if user is None:
            return Response({"detail": "用户名或密码错误"}, status=status.HTTP_401_UNAUTHORIZED)
        token = RefreshToken.for_user(user)
        return Response({"access_token": str(token.access_token), "token_type": "bearer"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    return Response({"id": u.id, "username": u.username, "display_name": u.get_full_name() or "平台管理员"})


class ShowViewSet(viewsets.ModelViewSet):
    queryset = Show.objects.all().order_by("id")
    serializer_class = ShowSerializer


class HallViewSet(viewsets.ModelViewSet):
    queryset = Hall.objects.all().order_by("id")
    serializer_class = HallSerializer


class PerformanceViewSet(viewsets.ModelViewSet):
    queryset = Performance.objects.select_related("show", "hall").all().order_by("start_at")
    serializer_class = PerformanceSerializer


class OrderViewSet(viewsets.ModelViewSet):
    queryset = TicketOrder.objects.select_related("performance", "performance__show").all().order_by("-id")
    http_method_names = ["get"]
    serializer_class = TicketOrderSerializer


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def hall_init_seats(request, pk):
    try:
        hall = Hall.objects.get(pk=pk)
    except Hall.DoesNotExist:
        return Response({"detail": "厅不存在"}, status=status.HTTP_404_NOT_FOUND)

    s = HallSeatInitSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    zones = s.validated_data["zones"]

    created = 0
    templates = []
    for zone_data in zones:
        zone_name = zone_data["name"]
        grade = zone_data["grade"]
        for row_data in zone_data["rows"]:
            row_label = str(row_data["row"])
            seat_count = row_data["seats"]
            for n in range(1, seat_count + 1):
                templates.append(
                    SeatTemplate(hall=hall, zone=zone_name, row=row_label, number=str(n), grade=grade)
                )

    existing = set(
        SeatTemplate.objects.filter(hall=hall).values_list("zone", "row", "number")
    )
    new_templates = [
        t for t in templates if (t.zone, t.row, t.number) not in existing
    ]
    SeatTemplate.objects.bulk_create(new_templates)
    created = len(new_templates)

    return Response({
        "hall_id": hall.id,
        "created": created,
        "total_templates": SeatTemplate.objects.filter(hall=hall).count(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def performance_generate_seats(request, pk):
    try:
        perf = Performance.objects.select_related("hall").get(pk=pk)
    except Performance.DoesNotExist:
        return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

    if PerformanceSeat.objects.filter(performance=perf).exists():
        return Response({"detail": "该场次座位已生成，不可重复"}, status=status.HTTP_409_CONFLICT)

    s = GenerateSeatsSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    prices = s.validated_data["prices"]

    price_records = []
    for grade, price in prices.items():
        price_records.append(PerformanceSeatPrice(performance=perf, grade=grade, price=price))
    PerformanceSeatPrice.objects.bulk_create(price_records)

    price_map = dict(prices)

    templates = SeatTemplate.objects.filter(hall=perf.hall).order_by("zone", "row", "number")
    if not templates.exists():
        return Response({"detail": "该厅尚未初始化座位模板"}, status=status.HTTP_400_BAD_REQUEST)

    seat_records = []
    for t in templates:
        if t.grade not in price_map:
            continue
        seat_records.append(
            PerformanceSeat(
                performance=perf,
                seat_template=t,
                zone=t.zone,
                row=t.row,
                number=t.number,
                grade=t.grade,
                price=price_map[t.grade],
            )
        )

    PerformanceSeat.objects.bulk_create(seat_records)

    return Response({
        "performance_id": perf.id,
        "generated": len(seat_records),
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def performance_seat_map(request, pk):
    try:
        perf = Performance.objects.select_related("show", "hall").get(pk=pk)
    except Performance.DoesNotExist:
        return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

    seats = PerformanceSeat.objects.filter(performance=perf).order_by("zone", "row", "number")
    prices = PerformanceSeatPrice.objects.filter(performance=perf)

    grouped = {}
    for seat in seats:
        key = seat.zone
        if key not in grouped:
            grouped[key] = {"zone": key, "grade": seat.grade, "rows": {}}
        row_key = seat.row
        if row_key not in grouped[key]["rows"]:
            grouped[key]["rows"][row_key] = []
        grouped[key]["rows"][row_key].append(PerformanceSeatSerializer(seat).data)

    zones = []
    for zone_name, zone_data in grouped.items():
        rows_list = []
        for row_label in sorted(zone_data["rows"].keys(), key=lambda x: int(x) if x.isdigit() else x):
            rows_list.append({"row": row_label, "seats": zone_data["rows"][row_label]})
        zones.append({"zone": zone_name, "grade": zone_data["grade"], "rows": rows_list})

    return Response({
        "performance_id": perf.id,
        "show_title": perf.show.title,
        "hall_name": perf.hall.name,
        "start_at": perf.start_at,
        "prices": PerformanceSeatPriceSerializer(prices, many=True).data,
        "zones": zones,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def performance_lock_seats(request, pk):
    try:
        perf = Performance.objects.get(pk=pk)
    except Performance.DoesNotExist:
        return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

    s = LockSeatsSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data
    seat_ids = data["seat_ids"]

    with transaction.atomic():
        _release_expired_for_performance(perf.id)

        seats = list(
            PerformanceSeat.objects.select_for_update().filter(performance_id=perf.id, id__in=seat_ids)
        )

        if len(seats) != len(seat_ids):
            return Response({"detail": "部分座位不存在"}, status=status.HTTP_404_NOT_FOUND)

        for seat in seats:
            if seat.status != "available":
                return Response(
                    {"detail": f"座位 {seat.zone}-{seat.row}排{seat.number}号 不可售，当前状态: {seat.get_status_display()}"},
                    status=status.HTTP_409_CONFLICT,
                )

        now = datetime.now()
        locked_until = now + timedelta(minutes=LOCK_MINUTES)
        total = sum(seat.price for seat in seats)

        order = TicketOrder.objects.create(
            performance=perf,
            user=request.user,
            customer_name=data["customer_name"],
            phone=data.get("phone", ""),
            amount=total,
            status="pending",
            locked_until=locked_until,
        )

        order_seats = []
        for seat in seats:
            seat.status = "locked"
            order_seats.append(OrderSeat(order=order, performance_seat=seat))

        PerformanceSeat.objects.bulk_update(seats, ["status"])
        OrderSeat.objects.bulk_create(order_seats)

    return Response(TicketOrderSerializer(order).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def order_pay(request, pk):
    with transaction.atomic():
        try:
            order = TicketOrder.objects.select_for_update().select_related("performance").get(pk=pk)
        except TicketOrder.DoesNotExist:
            return Response({"detail": "订单不存在"}, status=status.HTTP_404_NOT_FOUND)

        if order.user_id != request.user.id:
            return Response({"detail": "无权操作他人订单"}, status=status.HTTP_403_FORBIDDEN)

        if order.status != "pending":
            return Response({"detail": f"订单状态为 {order.get_status_display()}，无法支付"}, status=status.HTTP_409_CONFLICT)

        if order.locked_until and datetime.now() > order.locked_until:
            _release_order_seats(order)
            return Response({"detail": "锁座已过期，请重新选座"}, status=status.HTTP_410_GONE)

        order.status = "paid"
        order.locked_until = None
        order.save(update_fields=["status", "locked_until"])

        PerformanceSeat.objects.filter(
            performance_id=order.performance_id,
            status="locked",
            id__in=order.order_seats.values_list("performance_seat_id", flat=True),
        ).update(status="sold")

    return Response(TicketOrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def order_cancel(request, pk):
    with transaction.atomic():
        try:
            order = TicketOrder.objects.select_for_update().get(pk=pk)
        except TicketOrder.DoesNotExist:
            return Response({"detail": "订单不存在"}, status=status.HTTP_404_NOT_FOUND)

        if order.user_id != request.user.id:
            return Response({"detail": "无权操作他人订单"}, status=status.HTTP_403_FORBIDDEN)

        if order.status not in ("pending",):
            return Response({"detail": f"订单状态为 {order.get_status_display()}，无法取消"}, status=status.HTTP_409_CONFLICT)

        _release_order_seats(order)

    return Response(TicketOrderSerializer(order).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def release_expired_locks(request):
    now = datetime.now()
    expired_orders = TicketOrder.objects.filter(status="pending", locked_until__lt=now)
    count = expired_orders.count()

    for order in expired_orders.select_related("performance"):
        with transaction.atomic():
            order = TicketOrder.objects.select_for_update().get(pk=order.pk)
            if order.status != "pending":
                continue
            _release_order_seats(order)

    return Response({"released_orders": count})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def performance_seat_stats(request, pk):
    try:
        perf = Performance.objects.select_related("show", "hall").get(pk=pk)
    except Performance.DoesNotExist:
        return Response({"detail": "场次不存在"}, status=status.HTTP_404_NOT_FOUND)

    total = PerformanceSeat.objects.filter(performance=perf).count()
    sold = PerformanceSeat.objects.filter(performance=perf, status="sold").count()
    locked = PerformanceSeat.objects.filter(performance=perf, status="locked").count()
    available = total - sold - locked

    grade_stats = list(
        PerformanceSeat.objects.filter(performance=perf)
        .values("grade")
        .annotate(
            total=Count("id"),
            sold=Count("id", filter=Q(status="sold")),
            locked=Count("id", filter=Q(status="locked")),
        )
        .order_by("grade")
    )

    for gs in grade_stats:
        gs["available"] = gs["total"] - gs["sold"] - gs["locked"]

    return Response({
        "performance_id": perf.id,
        "show_title": perf.show.title,
        "hall_name": perf.hall.name,
        "total": total,
        "sold": sold,
        "locked": locked,
        "available": available,
        "grade_stats": grade_stats,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_stats(request):
    show_total = Show.objects.count()
    show_on_sale = Show.objects.filter(status="on_sale").count()
    perf_total = Performance.objects.count()
    order_paid = TicketOrder.objects.filter(status="paid").count()
    sold = PerformanceSeat.objects.filter(status="sold").count()
    capacity = PerformanceSeat.objects.count()
    return Response({
        "show_total": show_total,
        "show_on_sale": show_on_sale,
        "performance_total": perf_total,
        "order_paid": order_paid,
        "seats_sold": sold,
        "seats_capacity": capacity,
    })


def _release_expired_for_performance(performance_id):
    now = datetime.now()
    expired = TicketOrder.objects.filter(
        performance_id=performance_id, status="pending", locked_until__lt=now
    )
    for order in expired:
        order = TicketOrder.objects.select_for_update().get(pk=order.pk)
        if order.status != "pending":
            continue
        _release_order_seats(order)


def _release_order_seats(order):
    seat_ids = list(order.order_seats.values_list("performance_seat_id", flat=True))
    PerformanceSeat.objects.filter(id__in=seat_ids, status="locked").update(status="available")
    order.status = "cancelled"
    order.locked_until = None
    order.save(update_fields=["status", "locked_until"])
