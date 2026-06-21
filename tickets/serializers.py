from rest_framework import serializers

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


class ShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Show
        fields = ["id", "title", "troupe", "genre", "status", "created_at"]
        read_only_fields = ["id", "created_at"]


class HallSerializer(serializers.ModelSerializer):
    seat_count = serializers.SerializerMethodField()

    class Meta:
        model = Hall
        fields = ["id", "name", "seat_count", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_seat_count(self, obj):
        return obj.seat_templates.count()


class SeatTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeatTemplate
        fields = ["id", "hall", "zone", "row", "number", "grade"]
        read_only_fields = ["id"]


class HallSeatInitSerializer(serializers.Serializer):
    zones = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_zones(self, value):
        for zone in value:
            if "name" not in zone or "grade" not in zone or "rows" not in zone:
                raise serializers.ValidationError("每个区需要 name、grade、rows 字段")
            for row in zone["rows"]:
                if "row" not in row or "seats" not in row:
                    raise serializers.ValidationError("每排需要 row、seats 字段")
                if not isinstance(row["seats"], int) or row["seats"] < 1:
                    raise serializers.ValidationError("seats 必须是正整数")
        return value


class PerformanceSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="show.title", read_only=True)
    hall_name = serializers.CharField(source="hall.name", read_only=True)

    class Meta:
        model = Performance
        fields = ["id", "show", "show_title", "hall", "hall_name", "start_at", "created_at"]
        read_only_fields = ["id", "created_at"]


class PerformanceSeatPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceSeatPrice
        fields = ["id", "performance", "grade", "price"]
        read_only_fields = ["id"]


class GenerateSeatsSerializer(serializers.Serializer):
    prices = serializers.DictField(child=serializers.DecimalField(max_digits=10, decimal_places=2))


class PerformanceSeatSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerformanceSeat
        fields = ["id", "zone", "row", "number", "grade", "price", "status"]


class LockSeatsSerializer(serializers.Serializer):
    seat_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)
    customer_name = serializers.CharField(max_length=64)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class OrderSeatReadSerializer(serializers.ModelSerializer):
    zone = serializers.CharField(source="performance_seat.zone")
    row = serializers.CharField(source="performance_seat.row")
    number = serializers.CharField(source="performance_seat.number")
    grade = serializers.CharField(source="performance_seat.grade")
    price = serializers.DecimalField(source="performance_seat.price", max_digits=10, decimal_places=2)

    class Meta:
        model = OrderSeat
        fields = ["id", "zone", "row", "number", "grade", "price"]


class TicketOrderSerializer(serializers.ModelSerializer):
    show_title = serializers.CharField(source="performance.show.title", read_only=True)
    seats = OrderSeatReadSerializer(source="order_seats", many=True, read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = TicketOrder
        fields = [
            "id", "performance", "show_title", "user_id", "customer_name", "phone",
            "amount", "status", "locked_until", "seats", "created_at",
        ]
        read_only_fields = ["id", "user_id", "amount", "status", "locked_until", "created_at"]


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField()
