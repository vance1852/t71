from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from tickets.models import (
    Hall,
    OrderSeat,
    Performance,
    PerformanceSeat,
    PerformanceSeatPrice,
    SeatTemplate,
    Show,
    TicketOrder,
)


class Command(BaseCommand):
    help = "初始化管理员与演出票务种子数据"

    def handle(self, *args, **options):
        username = settings.DEFAULT_ADMIN_USERNAME
        password = settings.DEFAULT_ADMIN_PASSWORD
        admin_user = None
        if not User.objects.filter(username=username).exists():
            admin_user = User.objects.create_superuser(
                username=username, password=password, first_name="平台管理员"
            )
            self.stdout.write("已创建管理员账号")
        else:
            admin_user = User.objects.get(username=username)

        if Hall.objects.exists():
            self.stdout.write("业务数据已存在，跳过")
            return

        hall = Hall.objects.create(name="星河大剧院")

        vip_rows = [
            {"row": "1", "seats": 12},
            {"row": "2", "seats": 14},
        ]
        a_rows = [
            {"row": "3", "seats": 16},
            {"row": "4", "seats": 16},
            {"row": "5", "seats": 18},
        ]
        b_rows = [
            {"row": "6", "seats": 20},
            {"row": "7", "seats": 20},
            {"row": "8", "seats": 22},
            {"row": "9", "seats": 22},
        ]

        templates = []
        for row_data in vip_rows:
            for n in range(1, row_data["seats"] + 1):
                templates.append(SeatTemplate(hall=hall, zone="VIP区", row=row_data["row"], number=str(n), grade="VIP"))
        for row_data in a_rows:
            for n in range(1, row_data["seats"] + 1):
                templates.append(SeatTemplate(hall=hall, zone="A区", row=row_data["row"], number=str(n), grade="A"))
        for row_data in b_rows:
            for n in range(1, row_data["seats"] + 1):
                templates.append(SeatTemplate(hall=hall, zone="B区", row=row_data["row"], number=str(n), grade="B"))
        SeatTemplate.objects.bulk_create(templates)

        total_seats = len(templates)
        self.stdout.write(f"厅 [{hall.name}] 初始化 {total_seats} 个座位模板")

        shows = [
            Show.objects.create(title="星河巡回演唱会", troupe="星河乐团", genre="concert", status="on_sale"),
            Show.objects.create(title="金陵往事话剧", troupe="城南剧社", genre="drama", status="on_sale"),
            Show.objects.create(title="敦煌音乐剧", troupe="丝路艺术团", genre="musical", status="upcoming"),
        ]

        now = datetime.now().replace(microsecond=0)

        perf1 = Performance.objects.create(show=shows[0], hall=hall, start_at=now + timedelta(days=3))
        perf2 = Performance.objects.create(show=shows[0], hall=hall, start_at=now + timedelta(days=4))
        perf3 = Performance.objects.create(show=shows[1], hall=hall, start_at=now + timedelta(days=2))

        performances = [perf1, perf2, perf3]
        price_configs = [
            {"VIP": 880, "A": 580, "B": 380},
            {"VIP": 880, "A": 580, "B": 380},
            {"VIP": 480, "A": 280, "B": 180},
        ]

        template_map = {t.id: t for t in SeatTemplate.objects.filter(hall=hall)}

        for perf, prices in zip(performances, price_configs):
            price_records = [
                PerformanceSeatPrice(performance=perf, grade=grade, price=price)
                for grade, price in prices.items()
            ]
            PerformanceSeatPrice.objects.bulk_create(price_records)

            seat_records = []
            for t in template_map.values():
                seat_records.append(
                    PerformanceSeat(
                        performance=perf,
                        seat_template=t,
                        zone=t.zone,
                        row=t.row,
                        number=t.number,
                        grade=t.grade,
                        price=prices[t.grade],
                    )
                )
            PerformanceSeat.objects.bulk_create(seat_records)

        some_seat_pks = list(
            PerformanceSeat.objects.filter(performance=perf1)
            .order_by("zone", "row", "number")
            .values_list("id", flat=True)[:5]
        )
        some_seats = PerformanceSeat.objects.filter(id__in=some_seat_pks)
        order1 = TicketOrder.objects.create(
            performance=perf1,
            user=admin_user,
            customer_name="陈静",
            phone="13900001111",
            amount=sum(s.price for s in some_seats),
            status="paid",
            locked_until=None,
        )
        os_records = []
        for seat in some_seats:
            seat.status = "sold"
            os_records.append(OrderSeat(order=order1, performance_seat=seat))
        PerformanceSeat.objects.bulk_update(some_seats, ["status"])
        OrderSeat.objects.bulk_create(os_records)

        locked_seat_pks = list(
            PerformanceSeat.objects.filter(performance=perf1, status="available")
            .order_by("zone", "row", "number")
            .values_list("id", flat=True)[:3]
        )
        locked_seats = PerformanceSeat.objects.filter(id__in=locked_seat_pks)
        order2 = TicketOrder.objects.create(
            performance=perf1,
            user=admin_user,
            customer_name="刘洋",
            phone="13900002222",
            amount=sum(s.price for s in locked_seats),
            status="pending",
            locked_until=now + timedelta(minutes=10),
        )
        os_records2 = []
        for seat in locked_seats:
            seat.status = "locked"
            os_records2.append(OrderSeat(order=order2, performance_seat=seat))
        PerformanceSeat.objects.bulk_update(locked_seats, ["status"])
        OrderSeat.objects.bulk_create(os_records2)

        order3 = TicketOrder.objects.create(
            performance=perf2,
            user=admin_user,
            customer_name="孙琳",
            phone="13900003333",
            amount=880,
            status="cancelled",
            locked_until=None,
        )

        self.stdout.write(
            f"种子数据初始化完成: {len(performances)} 场次, "
            f"{TicketOrder.objects.count()} 订单, "
            f"{PerformanceSeat.objects.filter(status='sold').count()} 已售, "
            f"{PerformanceSeat.objects.filter(status='locked').count()} 锁定"
        )
