from django.contrib import admin
from django.contrib.admin import register

from assettrack.admin_site import assettrack_admin

from accounts.models import Company, User

from .models import Device, Category, Checkout, MaintenanceLog, SystemSettings


class CompanyScopedAdmin(admin.ModelAdmin):
    """Limit Django admin records and relation choices to the reviewer's company."""

    company_filter = "company"

    def _company_for(self, request):
        company = getattr(request.user, "company", None)
        if not company:
            administered = getattr(request.user, "administered_companies", None)
            company = administered.first() if administered else None
        return company

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        company = self._company_for(request)
        if company:
            return queryset.filter(**{self.company_filter: company})
        if request.user.is_superuser:
            return queryset
        return queryset.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        company = self._company_for(request)
        if company:
            if db_field.name == "company":
                kwargs["queryset"] = Company.objects.filter(pk=company.pk)
            elif db_field.name == "employee":
                kwargs["queryset"] = User.objects.filter(company=company)
            elif db_field.name == "device":
                kwargs["queryset"] = Device.objects.filter(company=company)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@register(Device, site=assettrack_admin)
class DeviceAdmin(CompanyScopedAdmin):
    list_display = ("asset_tag", "model_name", "company", "status")
    list_filter = ("status", "company")


@register(Category, site=assettrack_admin)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_custom")


@register(Checkout, site=assettrack_admin)
class CheckoutAdmin(CompanyScopedAdmin):
    list_display = ("device", "employee", "status", "due_date", "company")
    list_filter = ("status", "company")


@register(MaintenanceLog, site=assettrack_admin)
class MaintenanceLogAdmin(CompanyScopedAdmin):
    company_filter = "device__company"
    list_display = ("device", "reported_by", "is_resolved", "reported_at")
    list_filter = ("is_resolved",)


@register(SystemSettings, site=assettrack_admin)
class SystemSettingsAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk=1)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
