from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from assets.models import Department
from .models import User, Company, CompanyMembershipRequest


class AssetTrackUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Role & Company", {"fields": ("role", "company", "department", "contact_number", "profile_photo")}),
    )
    list_display = ("username", "email", "role", "company", "is_active")
    list_filter = ("role", "company", "is_active")


admin.site.register(User, AssetTrackUserAdmin)
admin.site.register(Company)
admin.site.register(CompanyMembershipRequest)
admin.site.register(Department)
