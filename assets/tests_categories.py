from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Company, User
from .forms import CategoryForm, DeviceForm
from .models import Category, Device


class CategoryCrudTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="catadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(name="Cat Co", code="CMP-CAT001", admin=self.admin)
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.client.force_login(self.admin)

    def test_admin_can_create_edit_and_delete_category(self):
        self.client.post(reverse("assets:category_create"), {"name": "Tablet", "is_custom": ""})
        category = Category.objects.get(name="Tablet")
        self.client.post(
            reverse("assets:category_edit", args=[category.pk]),
            {"name": "Tablets", "is_custom": "on"},
        )
        category.refresh_from_db()
        self.assertEqual(category.name, "Tablets")
        self.assertTrue(category.is_custom)
        self.client.post(reverse("assets:category_delete", args=[category.pk]))
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())

    def test_category_name_must_be_unique(self):
        Category.objects.create(name="Projector")
        form = CategoryForm(data={"name": "Projector", "is_custom": False})
        self.assertFalse(form.is_valid())

    def test_category_used_by_device_cannot_be_deleted(self):
        category = Category.objects.create(name="Laptop")
        Device.objects.create(
            company=self.company, asset_tag="CAT-DEV-1", model_name="ThinkPad",
            category=category,
        )
        response = self.client.post(reverse("assets:category_delete", args=[category.pk]))
        self.assertRedirects(response, reverse("assets:category_list"))
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())

    def test_device_asset_tag_and_serial_are_unique(self):
        category = Category.objects.create(name="Laptop")
        Device.objects.create(
            company=self.company, asset_tag="CAT-TAG-1", serial_number="SN123",
            model_name="ThinkPad", category=category,
        )
        form = DeviceForm(data={
            "asset_tag": "CAT-TAG-1", "serial_number": "SN999",
            "model_name": "Other", "category": str(category.pk),
            "status": Device.STATUS_AVAILABLE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("asset_tag", form.errors)

        form = DeviceForm(data={
            "asset_tag": "CAT-TAG-2", "serial_number": "SN123",
            "model_name": "Other", "category": str(category.pk),
            "status": Device.STATUS_AVAILABLE,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("serial_number", form.errors)

    def test_device_list_search_and_filters(self):
        laptop = Category.objects.create(name="Laptop")
        monitor = Category.objects.create(name="Monitor")
        Device.objects.create(
            company=self.company, asset_tag="SRCH-1", serial_number="SN-A1",
            model_name="ThinkPad X1", category=laptop, status=Device.STATUS_AVAILABLE,
        )
        Device.objects.create(
            company=self.company, asset_tag="SRCH-2", serial_number="SN-B2",
            model_name="Dell Monitor", category=monitor, status=Device.STATUS_REPAIR,
        )
        response = self.client.get(reverse("assets:device_list"), {"q": "SN-B2"})
        self.assertEqual([d.asset_tag for d in response.context["devices"]], ["SRCH-2"])
        response = self.client.get(reverse("assets:device_list"), {"q": "SN-A1"})
        self.assertEqual([d.asset_tag for d in response.context["devices"]], ["SRCH-1"])
        response = self.client.get(reverse("assets:device_list"), {"status": Device.STATUS_REPAIR})
        self.assertEqual([d.asset_tag for d in response.context["devices"]], ["SRCH-2"])
        response = self.client.get(reverse("assets:device_list"), {"category": monitor.pk})
        self.assertEqual([d.asset_tag for d in response.context["devices"]], ["SRCH-2"])

    def test_invalid_device_status_is_rejected_by_database(self):
        category = Category.objects.create(name="Laptop")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Device.objects.create(
                    company=self.company, asset_tag="BAD-STATUS", model_name="X",
                    category=category, status="unknown",
                )
