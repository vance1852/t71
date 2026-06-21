from django.http import JsonResponse
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    HallViewSet,
    LoginView,
    OrderViewSet,
    PerformanceViewSet,
    ShowViewSet,
    dashboard_stats,
    hall_init_seats,
    me,
    order_cancel,
    order_pay,
    performance_generate_seats,
    performance_lock_seats,
    performance_seat_map,
    performance_seat_stats,
    release_expired_locks,
)


def health(_request):
    return JsonResponse({"status": "ok", "service": "show-ticketing-admin"})


router = DefaultRouter(trailing_slash=False)
router.register("shows", ShowViewSet)
router.register("halls", HallViewSet)
router.register("performances", PerformanceViewSet)
router.register("orders", OrderViewSet)

urlpatterns = [
    path("health", health, name="health"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/me", me, name="auth-me"),
    path("dashboard/stats", dashboard_stats, name="dashboard-stats"),
    path("halls/<int:pk>/init-seats", hall_init_seats, name="hall-init-seats"),
    path("performances/<int:pk>/generate-seats", performance_generate_seats, name="performance-generate-seats"),
    path("performances/<int:pk>/seat-map", performance_seat_map, name="performance-seat-map"),
    path("performances/<int:pk>/lock-seats", performance_lock_seats, name="performance-lock-seats"),
    path("performances/<int:pk>/seat-stats", performance_seat_stats, name="performance-seat-stats"),
    path("orders/<int:pk>/pay", order_pay, name="order-pay"),
    path("orders/<int:pk>/cancel", order_cancel, name="order-cancel"),
    path("seats/release-expired", release_expired_locks, name="release-expired-locks"),
]

urlpatterns += router.urls
