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

from django.http import JsonResponse


def health(_request):
    return JsonResponse({"status": "ok", "service": "show-ticketing-admin"})


router = DefaultRouter(trailing_slash=False)
router.register("shows", ShowViewSet)
router.register("halls", HallViewSet)
router.register("performances", PerformanceViewSet)
router.register("orders", OrderViewSet)

urlpatterns = [
    path("health", health),
    path("auth/login", LoginView.as_view()),
    path("auth/me", me),
    path("dashboard/stats", dashboard_stats),
    path("halls/<int:pk>/init-seats", hall_init_seats),
    path("performances/<int:pk>/generate-seats", performance_generate_seats),
    path("performances/<int:pk>/seat-map", performance_seat_map),
    path("performances/<int:pk>/lock-seats", performance_lock_seats),
    path("performances/<int:pk>/seat-stats", performance_seat_stats),
    path("orders/<int:pk>/pay", order_pay),
    path("orders/<int:pk>/cancel", order_cancel),
    path("seats/release-expired", release_expired_locks),
]

urlpatterns += router.urls
