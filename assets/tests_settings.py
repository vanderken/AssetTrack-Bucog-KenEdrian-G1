from datetime import timedelta

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .admin import CheckoutAdmin, SystemSettingsAdmin
from .forms import DeviceForm, SystemSettingsForm
from .models import Category, Checkout, Device, SystemSettings


class SystemSettingsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="settingsadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Settings Co", code="CMP-SET001", admin=self.admin,
        )
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="settingsemp", password="empass12345", role=User.ROLE_EMPLOYEE,
            company=self.company,
        )
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="SET-001", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_AVAILABLE,
        )
        self.settings_url = reverse("assets:system_settings")
        self.client.force_login(self.admin)

    def test_get_solo_uses_singleton_row_id_one(self):
        first = SystemSettings.get_solo()
        second = SystemSettings.get_solo()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(SystemSettings.objects.count(), 1)

    def test_database_rejects_a_second_settings_row(self):
        SystemSettings.get_solo()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SystemSettings.objects.bulk_create([SystemSettings(pk=2)])

    def test_overdue_days_must_be_positive(self):
        form = SystemSettingsForm(data={"overdue_days": 0})
        self.assertFalse(form.is_valid())
        self.assertIn("overdue_days", form.errors)

        SystemSettings.get_solo()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SystemSettings.objects.filter(pk=1).update(overdue_days=0)

    def test_settings_view_saves_toggles_and_threshold(self):
        response = self.client.post(self.settings_url, {
            "self_checkout_allowed": "on",
            "overdue_days": "10",
            "field_purchase_date_enabled": "on",
            "field_brand_enabled": "on",
            "field_location_enabled": "on",
            "field_notes_enabled": "on",
            "field_warranty_expiry_enabled": "on",
        })
        self.assertRedirects(response, self.settings_url)
        settings_obj = SystemSettings.get_solo()
        self.assertTrue(settings_obj.self_checkout_allowed)
        self.assertEqual(settings_obj.overdue_days, 10)
        self.assertTrue(settings_obj.field_location_enabled)
        self.assertTrue(settings_obj.field_warranty_expiry_enabled)

        response = self.client.get(self.settings_url)
        self.assertContains(response, "Default loan length used to set due dates")
        self.assertContains(response, 'name="overdue_days"')

    def test_self_checkout_toggle_controls_employee_requests(self):
        self.client.logout()
        self.client.force_login(self.employee)
        request_url = reverse("assets:my_checkout_request")
        self.assertEqual(self.client.get(request_url).status_code, 403)

        self.client.logout()
        self.client.force_login(self.admin)
        settings_obj = SystemSettings.get_solo()
        settings_obj.self_checkout_allowed = True
        settings_obj.save()

        self.client.logout()
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(request_url).status_code, 200)

    def test_optional_field_toggles_change_device_form(self):
        settings_obj = SystemSettings.get_solo()
        settings_obj.field_purchase_date_enabled = False
        settings_obj.field_brand_enabled = False
        settings_obj.field_location_enabled = False
        settings_obj.field_notes_enabled = False
        settings_obj.field_warranty_expiry_enabled = False
        settings_obj.save()

        form = DeviceForm(settings_obj=settings_obj)
        for field_name in [
            "purchase_date", "brand", "location", "notes", "warranty_expiry",
        ]:
            self.assertNotIn(field_name, form.fields)

        for field_name in [
            "field_purchase_date_enabled", "field_brand_enabled",
            "field_location_enabled", "field_notes_enabled",
            "field_warranty_expiry_enabled",
        ]:
            setattr(settings_obj, field_name, True)
        settings_obj.save()

        form = DeviceForm(settings_obj=settings_obj)
        for field_name in [
            "purchase_date", "brand", "location", "notes", "warranty_expiry",
        ]:
            self.assertIn(field_name, form.fields)

    def test_checkout_model_rejects_a_past_due_date(self):
        checkout = Checkout(
            company=self.company,
            employee=self.employee,
            requested_device_name="",
            due_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError) as caught:
            checkout.full_clean()
        self.assertIn("due_date", caught.exception.message_dict)

    def test_admin_querysets_are_company_scoped(self):
        other_company = Company.objects.create(
            name="Scoped Out Co", code="CMP-SCP001",
        )
        other_employee = User.objects.create_user(
            username="scopedemp", password="empass12345", role=User.ROLE_EMPLOYEE,
            company=other_company,
        )
        other_device = Device.objects.create(
            company=other_company, asset_tag="SCP-001", model_name="Other Device",
            category=self.category,
        )
        other_checkout = Checkout.objects.create(
            company=other_company, employee=other_employee, device=other_device,
            requested_device_name="", status=Checkout.STATUS_ACTIVE,
        )
        own_checkout = Checkout.objects.create(
            company=self.company, employee=self.employee, device=self.device,
            requested_device_name="", status=Checkout.STATUS_ACTIVE,
        )

        request = RequestFactory().get("/admin/assets/checkout/")
        request.user = self.admin
        queryset = CheckoutAdmin(Checkout, admin.site).get_queryset(request)

        self.assertIn(own_checkout, queryset)
        self.assertNotIn(other_checkout, queryset)

    def test_system_settings_admin_is_singleton_only(self):
        request = RequestFactory().get("/admin/assets/systemsettings/")
        request.user = self.admin
        model_admin = SystemSettingsAdmin(SystemSettings, admin.site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_threshold_sets_default_due_date_for_direct_assignment(self):
        settings_obj = SystemSettings.get_solo()
        settings_obj.overdue_days = 12
        settings_obj.save()

        response = self.client.post(reverse("assets:checkout_assign"), {
            "device": self.device.pk,
            "employee": self.employee.pk,
            "purpose": "Quarterly review",
        })
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        checkout = Checkout.objects.get(device=self.device)
        self.assertEqual(
            checkout.due_date, timezone.localdate() + timedelta(days=12)
        )
