from django.db import models


class Hall(models.Model):
    name = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "halls"


class SeatTemplate(models.Model):
    GRADE_CHOICES = [
        ("VIP", "VIP"),
        ("A", "A"),
        ("B", "B"),
    ]

    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name="seat_templates")
    zone = models.CharField(max_length=32)
    row = models.CharField(max_length=8)
    number = models.CharField(max_length=8)
    grade = models.CharField(max_length=8, choices=GRADE_CHOICES, default="B")

    class Meta:
        db_table = "seat_templates"
        unique_together = [("hall", "zone", "row", "number")]


class Show(models.Model):
    GENRE_CHOICES = [
        ("concert", "演唱会"),
        ("drama", "话剧"),
        ("musical", "音乐剧"),
        ("opera", "戏曲"),
        ("other", "其他"),
    ]
    STATUS_CHOICES = [
        ("on_sale", "售票中"),
        ("upcoming", "待开票"),
        ("ended", "已结束"),
    ]

    title = models.CharField(max_length=128)
    troupe = models.CharField(max_length=128, blank=True, default="")
    genre = models.CharField(max_length=16, choices=GENRE_CHOICES, default="concert")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="upcoming")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "shows"


class Performance(models.Model):
    show = models.ForeignKey(Show, on_delete=models.CASCADE, related_name="performances")
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name="performances")
    start_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "performances"


class PerformanceSeatPrice(models.Model):
    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="seat_prices")
    grade = models.CharField(max_length=8)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = "performance_seat_prices"
        unique_together = [("performance", "grade")]


class PerformanceSeat(models.Model):
    STATUS_CHOICES = [
        ("available", "可售"),
        ("locked", "锁定"),
        ("sold", "已售"),
    ]

    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="seats")
    seat_template = models.ForeignKey(SeatTemplate, on_delete=models.CASCADE)
    zone = models.CharField(max_length=32)
    row = models.CharField(max_length=8)
    number = models.CharField(max_length=8)
    grade = models.CharField(max_length=8)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="available")

    class Meta:
        db_table = "performance_seats"
        unique_together = [("performance", "seat_template")]


class TicketOrder(models.Model):
    STATUS_CHOICES = [
        ("pending", "待支付"),
        ("paid", "已支付"),
        ("cancelled", "已取消"),
    ]

    performance = models.ForeignKey(Performance, on_delete=models.CASCADE, related_name="orders")
    customer_name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_orders"


class OrderSeat(models.Model):
    order = models.ForeignKey(TicketOrder, on_delete=models.CASCADE, related_name="order_seats")
    performance_seat = models.ForeignKey(PerformanceSeat, on_delete=models.CASCADE)

    class Meta:
        db_table = "order_seats"
        unique_together = [("order", "performance_seat")]
