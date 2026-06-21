from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

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

User = get_user_model()


class SeatTicketingTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(username="alice", password="alice123")
        self.user2 = User.objects.create_user(username="bob", password="bob123")

        self.hall = Hall.objects.create(name="测试大厅")

        templates = []
        for row in range(1, 4):
            for n in range(1, 6):
                templates.append(
                    SeatTemplate(
                        hall=self.hall,
                        zone="VIP区" if row == 1 else "A区",
                        row=str(row),
                        number=str(n),
                        grade="VIP" if row == 1 else "A",
                    )
                )
        SeatTemplate.objects.bulk_create(templates)

        self.show = Show.objects.create(
            title="测试演唱会", troupe="测试乐团", genre="concert", status="on_sale"
        )

        now = datetime.now()
        self.perf = Performance.objects.create(
            show=self.show, hall=self.hall, start_at=now + timedelta(days=3)
        )

        self.prices = {"VIP": 880, "A": 580, "B": 380}
        price_records = [
            PerformanceSeatPrice(performance=self.perf, grade=g, price=p)
            for g, p in self.prices.items()
        ]
        PerformanceSeatPrice.objects.bulk_create(price_records)

        seat_records = []
        for t in SeatTemplate.objects.filter(hall=self.hall):
            seat_records.append(
                PerformanceSeat(
                    performance=self.perf,
                    seat_template=t,
                    zone=t.zone,
                    row=t.row,
                    number=t.number,
                    grade=t.grade,
                    price=self.prices[t.grade],
                )
            )
        PerformanceSeat.objects.bulk_create(seat_records)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_01_hall_seat_init(self):
        self._auth(self.user1)
        hall2 = Hall.objects.create(name="大厅2")
        url = reverse("hall-init-seats", args=[hall2.id])
        resp = self.client.post(url, {
            "zones": [
                {
                    "name": "VIP区", "grade": "VIP",
                    "rows": [{"row": "1", "seats": 5}, {"row": "2", "seats": 5}],
                },
                {
                    "name": "A区", "grade": "A",
                    "rows": [{"row": "3", "seats": 6}],
                },
            ]
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["created"], 16)
        self.assertEqual(resp.data["total_templates"], 16)

    def test_02_performance_generate_seats(self):
        self._auth(self.user1)
        now = datetime.now()
        perf2 = Performance.objects.create(
            show=self.show, hall=self.hall, start_at=now + timedelta(days=4)
        )
        url = reverse("performance-generate-seats", args=[perf2.id])
        resp = self.client.post(url, {"prices": {"VIP": 880, "A": 580, "B": 380}}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["generated"], 15)
        self.assertEqual(PerformanceSeat.objects.filter(performance=perf2).count(), 15)
        self.assertEqual(PerformanceSeatPrice.objects.filter(performance=perf2).count(), 3)

    def test_03_performance_generate_seats_duplicate(self):
        self._auth(self.user1)
        url = reverse("performance-generate-seats", args=[self.perf.id])
        resp = self.client.post(url, {"prices": {"VIP": 880}}, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_04_seat_map(self):
        self._auth(self.user1)
        url = reverse("performance-seat-map", args=[self.perf.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        zones = resp.data["zones"]
        self.assertEqual(len(zones), 2)
        zone_names = {z["zone"] for z in zones}
        self.assertIn("VIP区", zone_names)
        self.assertIn("A区", zone_names)

        vip_zone = next(z for z in zones if z["zone"] == "VIP区")
        self.assertEqual(vip_zone["grade"], "VIP")
        self.assertEqual(len(vip_zone["rows"]), 1)
        self.assertEqual(vip_zone["rows"][0]["row"], "1")
        self.assertEqual(len(vip_zone["rows"][0]["seats"]), 5)

        a_zone = next(z for z in zones if z["zone"] == "A区")
        self.assertEqual(len(a_zone["rows"]), 2)
        for row in a_zone["rows"]:
            self.assertEqual(len(row["seats"]), 5)

        for seat in vip_zone["rows"][0]["seats"]:
            self.assertEqual(seat["status"], "available")

    def test_05_lock_seats_success(self):
        self._auth(self.user1)
        seats = list(
            PerformanceSeat.objects.filter(performance=self.perf, status="available")[:2]
        )
        seat_ids = [s.id for s in seats]
        url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(url, {
            "seat_ids": seat_ids,
            "customer_name": "用户A",
            "phone": "13800001111",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")
        self.assertIsNotNone(resp.data["locked_until"])
        self.assertEqual(len(resp.data["seats"]), 2)
        self.assertEqual(resp.data["user_id"], self.user1.id)

        for s in PerformanceSeat.objects.filter(id__in=seat_ids):
            self.assertEqual(s.status, "locked")

    def test_06_lock_same_seat_again_fails(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        url = reverse("performance-lock-seats", args=[self.perf.id])

        resp1 = self.client.post(url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        self.assertEqual(resp1.status_code, 201)

        self._auth(self.user2)
        resp2 = self.client.post(url, {
            "seat_ids": [seat.id],
            "customer_name": "用户B",
        }, format="json")
        self.assertEqual(resp2.status_code, 409)
        self.assertIn("不可售", resp2.data["detail"])

    def test_07_lock_non_available_fails(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf).first()
        seat.status = "sold"
        seat.save()
        url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        self.assertEqual(resp.status_code, 409)

    def test_08_pay_order_success(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        order_id = resp.data["id"]

        pay_url = reverse("order-pay", args=[order_id])
        resp2 = self.client.post(pay_url)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["status"], "paid")
        self.assertIsNone(resp2.data["locked_until"])

        seat.refresh_from_db()
        self.assertEqual(seat.status, "sold")

    def test_09_pay_expired_order_fails(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        order = TicketOrder.objects.get(pk=order_id)
        order.locked_until = datetime.now() - timedelta(minutes=1)
        order.save()

        pay_url = reverse("order-pay", args=[order_id])
        resp2 = self.client.post(pay_url)
        self.assertEqual(resp2.status_code, 410)

        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

        seat.refresh_from_db()
        self.assertEqual(seat.status, "available")

    def test_10_cancel_order_success(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        cancel_url = reverse("order-cancel", args=[order_id])
        resp2 = self.client.post(cancel_url)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["status"], "cancelled")

        seat.refresh_from_db()
        self.assertEqual(seat.status, "available")

    def test_11_paid_order_cannot_be_cancelled(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        self.client.post(reverse("order-pay", args=[order_id]))

        cancel_url = reverse("order-cancel", args=[order_id])
        resp2 = self.client.post(cancel_url)
        self.assertEqual(resp2.status_code, 409)

        seat.refresh_from_db()
        self.assertEqual(seat.status, "sold")

    def test_12_release_expired_locks(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        order = TicketOrder.objects.get(pk=order_id)
        order.locked_until = datetime.now() - timedelta(minutes=1)
        order.save()

        self._auth(self.user2)
        release_url = reverse("release-expired-locks")
        resp2 = self.client.post(release_url)
        self.assertEqual(resp2.status_code, 200)
        self.assertGreaterEqual(resp2.data["released_orders"], 1)

        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")

        seat.refresh_from_db()
        self.assertEqual(seat.status, "available")

    def test_13_seat_stats(self):
        self._auth(self.user1)
        stats_url = reverse("performance-seat-stats", args=[self.perf.id])
        resp = self.client.get(stats_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["total"], 15)
        self.assertEqual(resp.data["sold"], 0)
        self.assertEqual(resp.data["locked"], 0)
        self.assertEqual(resp.data["available"], 15)

        seats = list(PerformanceSeat.objects.filter(performance=self.perf, status="available")[:3])
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp2 = self.client.post(lock_url, {
            "seat_ids": [seats[0].id],
            "customer_name": "用户A",
        }, format="json")
        self.client.post(reverse("order-pay", args=[resp2.data["id"]]))

        self.client.post(lock_url, {
            "seat_ids": [seats[1].id, seats[2].id],
            "customer_name": "用户A",
        }, format="json")

        resp3 = self.client.get(stats_url)
        self.assertEqual(resp3.data["sold"], 1)
        self.assertEqual(resp3.data["locked"], 2)
        self.assertEqual(resp3.data["available"], 12)
        self.assertEqual(len(resp3.data["grade_stats"]), 2)

    def test_14_cross_user_pay_forbidden(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        self._auth(self.user2)
        pay_url = reverse("order-pay", args=[order_id])
        resp2 = self.client.post(pay_url)
        self.assertEqual(resp2.status_code, 403)

        order = TicketOrder.objects.get(pk=order_id)
        self.assertEqual(order.status, "pending")

    def test_15_cross_user_cancel_forbidden(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        lock_url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(lock_url, {
            "seat_ids": [seat.id],
            "customer_name": "用户A",
        }, format="json")
        order_id = resp.data["id"]

        self._auth(self.user2)
        cancel_url = reverse("order-cancel", args=[order_id])
        resp2 = self.client.post(cancel_url)
        self.assertEqual(resp2.status_code, 403)

        order = TicketOrder.objects.get(pk=order_id)
        self.assertEqual(order.status, "pending")

    def test_16_pay_non_pending_order_fails(self):
        self._auth(self.user1)
        seat = PerformanceSeat.objects.filter(performance=self.perf, status="available").first()
        order = TicketOrder.objects.create(
            performance=self.perf,
            user=self.user1,
            customer_name="用户A",
            amount=seat.price,
            status="cancelled",
        )
        OrderSeat.objects.create(order=order, performance_seat=seat)

        pay_url = reverse("order-pay", args=[order.id])
        resp = self.client.post(pay_url)
        self.assertEqual(resp.status_code, 409)

    def test_17_lock_nonexistent_seats_fails(self):
        self._auth(self.user1)
        url = reverse("performance-lock-seats", args=[self.perf.id])
        resp = self.client.post(url, {
            "seat_ids": [999999],
            "customer_name": "用户A",
        }, format="json")
        self.assertEqual(resp.status_code, 404)
