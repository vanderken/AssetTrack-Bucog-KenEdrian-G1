from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from assets.models import Department

from .models import User, Company, CompanyMembershipRequest


class CompanyScopedAdminMixin:
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
            filter_value = company.pk if self.company_filter == "pk" else company
            return queryset.filter(**{self.company_filter: filter_value})
        if request.user.is_superuser:
            return queryset
        return queryset.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        company = self._company_for(request)
        if company and db_field.name == "company":
            kwargs["queryset"] = Company.objects.filter(pk=company.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(User)
class AssetTrackUserAdmin(CompanyScopedAdminMixin, UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role & Company", {"fields": ("role", "company", "department", "contact_number", "profile_photo")}),
    )
    list_display = ("username", "email", "role", "company", "is_active")
    list_filter = ("role", "company", "is_active")


@admin.register(Company)
class CompanyAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    company_filter = "pk"
    list_display = ("name", "code", "admin", "created_at")


@admin.register(CompanyMembershipRequest)
class CompanyMembershipRequestAdmin(CompanyScopedAdminMixin, admin.ModelAdmin):
    company_filter = "company"
    list_display = ("user", "company", "request_type", "status", "created_at")
    list_filter = ("request_type", "status")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name",)
