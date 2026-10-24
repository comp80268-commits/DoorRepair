from django.contrib import admin

from .models import (
    Employee, Notification, Order, OrderFile, PriceItem, PriceList, Profile,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("store_name", "manager_name", "phone", "get_email", "city", "created_at")
    search_fields = ("store_name", "manager_name", "phone", "user__email", "city")
    list_filter = ("created_at",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    list_select_related = ("user",)

    @admin.display(description="Email", ordering="user__email")
    def get_email(self, obj):
        return obj.user.email


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "role")
    list_filter = ("role",)
    search_fields = ("full_name", "phone")


class OrderFileInline(admin.TabularInline):
    model = OrderFile
    extra = 1
    fields = ("source", "file", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number", "title", "get_shop", "status",
        "created_at", "desired_date_from", "desired_date_to", "scheduled_date",
    )
    # статус можно менять прямо в списке — сигналы отправят магазину уведомление
    list_editable = ("status",)
    list_filter = ("status", "order_type", "created_at")
    search_fields = ("number", "shop__email", "shop__profile__store_name")
    readonly_fields = ("number", "created_at")
    list_select_related = ("shop__profile", "manager", "installer")
    inlines = [OrderFileInline]
    ordering = ("-created_at",)

    fieldsets = (
        ("Заявка", {"fields": ("number", "shop", "title", "order_type", "status", "created_at")}),
        ("Даты", {"fields": ("desired_date_from", "desired_date_to", "scheduled_date")}),
        ("Адрес", {"fields": ("city", "street", "house")}),
        ("Сотрудники", {"fields": ("manager", "installer")}),
        ("Комментарий", {"fields": ("comment",)}),
    )

    @admin.display(description="Магазин", ordering="shop__profile__store_name")
    def get_shop(self, obj):
        profile = getattr(obj.shop, "profile", None)
        return profile.store_name if profile else obj.shop.email


@admin.register(PriceItem)
class PriceItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "position")
    list_editable = ("price", "position")
    search_fields = ("name",)
    ordering = ("position", "id")


@admin.register(PriceList)
class PriceListAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("created_at",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("text", "order", "user", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("text", "order__number", "user__email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)