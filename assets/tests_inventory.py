"""Feature 1 verification: equipment/category inventory CRUD through the UI."""

from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import Company, User
from assets.forms import DeviceForm
from assets.models import Category, Device


class EquipmentInventoryTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="inventory_admin",
            email="inventory@example.com",
            password="pass12345",
            role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Inventory Co", code="CMP-INV001", admin=self.admin
        )
        self.admin.company = self.company
        self.admin.save()
        self.category, _ = Category.objects.get_or_create(name="Laptop")
        self.client = Client()
        self.client.force_login(self.admin)

    def payload(self, tag="INV-001", model="ThinkPad T14"):
        return {
            "asset_tag": tag,
            "serial_number": f"SN-{tag}",
            "model_name": model,
            "status": Device.STATUS_AVAILABLE,
            "category": str(self.category.pk),
        }

    def test_create_device_from_inventory_page(self):
        response = self.client.post(reverse("assets:device_create"), self.payload())
        self.assertRedirects(response, reverse("assets:device_list"))
        device = Device.objects.get(asset_tag="INV-001")
        self.assertEqual(device.company, self.company)
        self.assertEqual(device.created_by, self.admin)

    def test_read_device_list_shows_company_inventory(self):
        Device.objects.create(
            company=self.company,
            asset_tag="INV-002",
            model_name="Dell Latitude",
            category=self.category,
        )
        response = self.client.get(reverse("assets:device_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INV-002")

    def test_update_device_from_inventory_page(self):
        device = Device.objects.create(
            company=self.company,
            asset_tag="INV-003",
            model_name="Old Model",
            category=self.category,
        )
        response = self.client.post(
            reverse("assets:device_edit", args=[device.pk]),
            self.payload(tag="INV-003", model="New Model"),
        )
        self.assertRedirects(response, reverse("assets:device_list"))
        device.refresh_from_db()
        self.assertEqual(device.model_name, "New Model")

    def test_delete_device_from_inventory_page(self):
        device = Device.objects.create(
            company=self.company,
            asset_tag="INV-004",
            model_name="Delete Me",
            category=self.category,
        )
        response = self.client.post(
            reverse("assets:device_delete", args=[device.pk])
        )
        self.assertRedirects(response, reverse("assets:device_list"))
        self.assertFalse(Device.objects.filter(pk=device.pk).exists())

    def test_duplicate_asset_tag_is_rejected(self):
        Device.objects.create(
            company=self.company,
            asset_tag="INV-005",
            model_name="First",
            category=self.category,
        )
        form = DeviceForm(data=self.payload(tag="INV-005", model="Second"))
        self.assertFalse(form.is_valid())
        self.assertIn("asset_tag", form.errors)

    def test_employee_cannot_access_admin_inventory(self):
        employee = User.objects.create_user(
            "inventory_emp",
            "inventory_emp@example.com",
            "pass12345",
            role=User.ROLE_EMPLOYEE,
            company=self.company,
        )
        client = Client()
        client.force_login(employee)
        self.assertEqual(
            client.get(reverse("assets:device_list")).status_code, 403
        )
