from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    LoginViewSet,
    LogoutViewSet,
    MeViewSet,
    NotificationViewSet,
    OrderViewSet,
    PriceItemViewSet,
    PriceListViewSet,
    RegisterViewSet,
    TokenRefreshDocView,
)

router = DefaultRouter()
router.register(r"register", RegisterViewSet, basename="register")
router.register(r"login", LoginViewSet, basename="login")
router.register(r"logout", LogoutViewSet, basename="logout")
router.register(r"orders", OrderViewSet, basename="orders")
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"price-items", PriceItemViewSet, basename="price-items")

me_detail = MeViewSet.as_view({"get": "retrieve", "patch": "partial_update"})
me_change_password = MeViewSet.as_view({"post": "change_password"})

price_list_info = PriceListViewSet.as_view({"get": "retrieve"})
price_list_download = PriceListViewSet.as_view({"get": "download"})

urlpatterns = [
    path("me/", me_detail, name="me"),
    path("me/change-password/", me_change_password, name="me-change-password"),
    path("price-list/", price_list_info, name="price-list"),
    path("price-list/download/", price_list_download, name="price-list-download"),
    path("token/refresh/", TokenRefreshDocView.as_view(), name="token-refresh"),
    path("", include(router.urls)),
]