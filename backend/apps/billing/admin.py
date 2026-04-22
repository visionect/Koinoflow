from django.contrib import admin

from .models import (
    Addon,
    Customer,
    Invoice,
    Plan,
    Subscription,
    SubscriptionAddon,
    WorkspaceSubscription,
)


class SubscriptionAddonInline(admin.TabularInline):
    model = SubscriptionAddon
    extra = 0


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("email", "company", "workspace", "created_at")
    search_fields = ("email", "company", "workspace__name")
    raw_id_fields = ("workspace",)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "tier", "price_display", "billing_period", "is_active")
    list_filter = ("tier", "billing_period", "is_active")

    @admin.display(description="Price")
    def price_display(self, obj):
        return f"{obj.price_cents / 100:.2f} {obj.currency}"


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = ("name", "price_cents", "currency", "is_active")
    list_filter = ("is_active",)


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "customer_email",
        "plan_name",
        "status",
        "current_term_start",
        "current_term_end",
        "created_at",
    )
    list_filter = ("status", "plan__tier")
    search_fields = ("customer__email", "customer__company")
    raw_id_fields = ("customer", "plan")
    inlines = [SubscriptionAddonInline]
    actions = ["mark_active", "mark_cancelled"]

    @admin.display(description="Customer")
    def customer_email(self, obj):
        return obj.customer.email

    @admin.display(description="Plan")
    def plan_name(self, obj):
        return obj.plan.name

    @admin.action(description="Mark selected as active")
    def mark_active(self, request, queryset):
        queryset.update(status="active")

    @admin.action(description="Mark selected as cancelled")
    def mark_cancelled(self, request, queryset):
        from django.utils import timezone

        queryset.update(status="cancelled", cancelled_at=timezone.now())


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "customer_email",
        "status",
        "total_display",
        "issued_at",
        "due_at",
        "paid_at",
    )
    list_filter = ("status",)
    search_fields = ("customer__email",)
    raw_id_fields = ("customer", "subscription")

    @admin.display(description="Customer")
    def customer_email(self, obj):
        return obj.customer.email

    @admin.display(description="Total")
    def total_display(self, obj):
        return f"{obj.total_cents / 100:.2f} {obj.currency}"


@admin.register(WorkspaceSubscription)
class WorkspaceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("workspace_name", "subscription_status", "created_at")
    list_filter = ("subscription__status",)
    search_fields = ("workspace__name",)
    raw_id_fields = ("workspace", "subscription")

    @admin.display(description="Workspace")
    def workspace_name(self, obj):
        return obj.workspace.name

    @admin.display(description="Status")
    def subscription_status(self, obj):
        return obj.subscription.status
