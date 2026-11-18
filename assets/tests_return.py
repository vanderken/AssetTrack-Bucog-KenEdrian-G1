"""Feature 3 verification: return recording with condition and maintenance handling."""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from assets.models import Category, Checkout, Device, MaintenanceLog


class ReturnAndConditionTests(TestCase):
    def setUp(self):
        self.category, _ = Category.objects.get_or_create(name="Laptop")
        self.admin = User.objects.create_user(
            "return_admin", "return_admin@example.com", "pass12345",
            role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Return Co", code="CMP-RET001", admin=self.admin
        )
        self.admin.company = self.company
        self.admin.save()
        self.employee = User.objects.create_user(
            "return_emp", "return_emp@example.com", "pass12345",
            role=User.ROLE_EMPLOYEE, company=self.company,
        )
        self.device = Device.objects.create(
            company=self.company, asset_tag="RET-001",
            model_name="Dell XPS 13", category=self.category,
            status=Device.STATUS_BORROWED,
        )
        self.checkout = Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            created_by=self.employee,
            device=self.device,
            status=Checkout.STATUS_ACTIVE,
            checked_out_at=timezone.now(),
            due_date=timezone.localdate() + timezone.timedelta(days=3),
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_return_with_good_condition_makes_device_available(self):
        response = self.client.post(
            reverse("assets:checkout_return", args=[self.checkout.pk]),
            {"return_condition": Checkout.CONDITION_GOOD},
        )
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        self.checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.checkout.status, Checkout.STATUS_RETURNED)
        self.assertIsNotNone(self.checkout.returned_at)
        self.assertEqual(self.checkout.return_condition, Checkout.CONDITION_GOOD)
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_return_with_damaged_condition_moves_device_to_repair(self):
        response = self.client.post(
            reverse("assets:checkout_return", args=[self.checkout.pk]),
            {"return_condition": Checkout.CONDITION_DAMAGED},
        )
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        self.checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.checkout.return_condition, Checkout.CONDITION_DAMAGED)
        self.assertEqual(self.device.status, Device.STATUS_REPAIR)

    def test_invalid_return_condition_is_rejected(self):
        response = self.client.post(
            reverse("assets:checkout_return", args=[self.checkout.pk]),
            {"return_condition": "not-a-real-condition"},
        )
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        self.checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.checkout.status, Checkout.STATUS_ACTIVE)
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_overdue_flag_is_computed_from_due_date(self):
        self.assertFalse(self.checkout.is_overdue)
        self.checkout.due_date = timezone.localdate() - timezone.timedelta(days=1)
        self.checkout.save()
        self.assertTrue(self.checkout.is_overdue)
        self.checkout.status = Checkout.STATUS_RETURNED
        self.checkout.save()
        self.assertFalse(self.checkout.is_overdue)

    def test_maintenance_log_resolution_restores_device(self):
        log = MaintenanceLog.objects.create(
            device=self.device,
            reported_by=self.admin,
            description="Screen cracked during lab use",
        )
        self.device.status = Device.STATUS_REPAIR
        self.device.save()
        response = self.client.post(
            reverse("assets:maintenance_resolve", args=[log.pk])
        )
        self.assertRedirects(response, reverse("assets:maintenance_list"))
        log.refresh_from_db()
        self.device.refresh_from_db()
        self.assertTrue(log.is_resolved)
        self.assertIsNotNone(log.resolved_at)
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_returned_checkout_disappears_from_active_list(self):
        self.client.post(
            reverse("assets:checkout_return", args=[self.checkout.pk]),
            {"return_condition": Checkout.CONDITION_MINOR_WEAR},
        )
        response = self.client.get(reverse("assets:active_checkouts"))
        self.assertEqual(list(response.context["checkouts"]), [])
