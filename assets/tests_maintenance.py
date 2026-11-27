from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .forms import MaintenanceLogForm
from .models import Category, Checkout, Device, MaintenanceLog


class MaintenanceLogTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="maintadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Maintenance Co", code="CMP-MNT001", admin=self.admin,
        )
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="maintemp", password="empass12345", role=User.ROLE_EMPLOYEE,
            company=self.company,
        )
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="MNT-001", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_AVAILABLE,
        )
        self.list_url = reverse("assets:maintenance_list")
        self.client.force_login(self.admin)

    def test_admin_can_log_damage_and_device_goes_under_repair(self):
        response = self.client.post(self.list_url, {
            "device": self.device.pk,
            "description": "Screen has a cracked panel",
        })
        self.assertRedirects(response, self.list_url)
        log = MaintenanceLog.objects.get(device=self.device)
        self.assertEqual(log.reported_by, self.admin)
        self.assertFalse(log.is_resolved)
        self.assertIsNone(log.resolved_at)
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_REPAIR)

    def test_description_is_required_and_detailed(self):
        form = MaintenanceLogForm(
            company=self.company,
            data={"device": self.device.pk, "description": "   "},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

        form = MaintenanceLogForm(
            company=self.company,
            data={"device": self.device.pk, "description": "bad"},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("description", form.errors)

    def test_oversized_photo_is_rejected(self):
        upload = SimpleUploadedFile(
            "damage.png", b"0" * (5 * 1024 * 1024 + 1), content_type="image/png",
        )
        form = MaintenanceLogForm(
            company=self.company,
            data={"device": self.device.pk, "description": "Cracked screen"},
            files={"image": upload},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image", form.errors)

    def test_resolution_records_timestamp_and_restores_device(self):
        log = MaintenanceLog.objects.create(
            device=self.device, reported_by=self.admin, description="Battery will not charge",
        )
        self.device.status = Device.STATUS_REPAIR
        self.device.save(update_fields=["status"])

        response = self.client.post(reverse("assets:maintenance_resolve", args=[log.pk]))
        self.assertRedirects(response, self.list_url)
        log.refresh_from_db()
        self.device.refresh_from_db()
        self.assertTrue(log.is_resolved)
        self.assertIsNotNone(log.resolved_at)
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

        response = self.client.post(reverse("assets:maintenance_resolve", args=[log.pk]))
        self.assertEqual(response.status_code, 404)

    def test_device_stays_under_repair_until_all_logs_are_resolved(self):
        first = MaintenanceLog.objects.create(
            device=self.device, description="Bent hinge",
        )
        second = MaintenanceLog.objects.create(
            device=self.device, description="Loose keyboard ribbon",
        )
        self.device.status = Device.STATUS_REPAIR
        self.device.save(update_fields=["status"])

        self.client.post(reverse("assets:maintenance_resolve", args=[first.pk]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_REPAIR)

        self.client.post(reverse("assets:maintenance_resolve", args=[second.pk]))
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_resolved_log_without_timestamp_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                MaintenanceLog.objects.create(
                    device=self.device,
                    description="Resolved without a timestamp",
                    is_resolved=True,
                    resolved_at=None,
                )

    def test_other_company_admin_cannot_resolve_log(self):
        log = MaintenanceLog.objects.create(
            device=self.device, description="Water damage",
        )
        other_admin = User.objects.create_user(
            username="otheradmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        Company.objects.create(name="Other Co", code="CMP-OTH001", admin=other_admin)
        self.client.force_login(other_admin)
        response = self.client.post(reverse("assets:maintenance_resolve", args=[log.pk]))
        self.assertEqual(response.status_code, 404)
        log.refresh_from_db()
        self.assertFalse(log.is_resolved)

    def test_maintenance_on_borrowed_device_closes_active_checkout(self):
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        checkout = Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            created_by=self.admin,
            device=self.device,
            requested_device_name="",
            status=Checkout.STATUS_ACTIVE,
            checked_out_at=timezone.now(),
        )

        self.client.post(self.list_url, {
            "device": self.device.pk,
            "description": "Laptop dropped during use",
        })
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_RETURNED)
        self.assertEqual(checkout.return_condition, Checkout.CONDITION_NEEDS_REPAIR)
        self.assertIsNotNone(checkout.returned_at)
