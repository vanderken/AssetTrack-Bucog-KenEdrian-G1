from django.contrib import admin as django_admin
from django.test import TestCase

from accounts.models import Company, User
from assettrack.admin_site import assettrack_admin

from .models import Category, Device


class CustomAdminUITests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="adminui",
            email="adminui@example.com",
            password="adminpass123",
            role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Admin UI Co", code="CMP-ADM001", admin=self.admin,
        )
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company,
            asset_tag="ADM-UI-001",
            model_name="ThinkPad",
            category=self.category,
        )

    def test_models_are_registered_on_custom_site_only(self):
        self.assertIn(Device, assettrack_admin._registry)
        self.assertNotIn(Device, django_admin.site._registry)

    def test_admin_index_uses_assettrack_shell(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AssetTrack Administration")
        self.assertContains(response, "at-card")
        self.assertContains(response, "Devices")
        self.assertNotContains(response, "Django administration")
        self.assertNotContains(response, 'id="site-name"')

    def test_admin_login_uses_assettrack_shell(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-wrapper")
        self.assertContains(response, "AssetTrack Admin")
        self.assertNotContains(response, "Django administration")

    def test_changelist_uses_assettrack_shell(self):
        self.client.force_login(self.admin)
        response = self.client.get("/admin/assets/device/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at-admin-shell")
        self.assertContains(response, self.device.asset_tag)
        self.assertNotContains(response, "Django administration")
