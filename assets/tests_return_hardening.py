"""Return condition validation tests."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .models import Category, Checkout, Device


class ReturnConditionHardeningTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="returnhardadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Return Hardening Co", code="CMP-RHD001", admin=self.admin,
        )
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="returnhardemp", password="empass12345", role=User.ROLE_EMPLOYEE,
            company=self.company,
        )
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="RHD-001", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_BORROWED,
        )
        self.checkout = Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            created_by=self.employee,
            device=self.device,
            requested_device_name="",
            status=Checkout.STATUS_ACTIVE,
            checked_out_at=timezone.now(),
            due_date=timezone.localdate() + timedelta(days=3),
        )
        self.return_url = reverse("assets:checkout_return", args=[self.checkout.pk])
        self.client.force_login(self.admin)

    def test_return_without_condition_is_rejected(self):
        response = self.client.post(self.return_url, {})
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        self.checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.checkout.status, Checkout.STATUS_ACTIVE)
        self.assertIsNone(self.checkout.returned_at)
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_blank_condition_is_rejected(self):
        response = self.client.post(self.return_url, {"return_condition": ""})
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        self.checkout.refresh_from_db()
        self.assertEqual(self.checkout.status, Checkout.STATUS_ACTIVE)

    def test_reports_quick_checkin_requires_condition_selector(self):
        self.checkout.due_date = timezone.localdate() - timedelta(days=1)
        self.checkout.save(update_fields=["due_date"])

        response = self.client.get(reverse("assets:reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="return_condition"')
        self.assertContains(response, "required")
        self.assertContains(response, 'value="reports"')

        response = self.client.post(self.return_url, {
            "return_condition": Checkout.CONDITION_NEEDS_REPAIR,
            "next": "reports",
        })
        self.assertRedirects(response, reverse("assets:reports"))
        self.checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.checkout.status, Checkout.STATUS_RETURNED)
        self.assertEqual(self.checkout.return_condition, Checkout.CONDITION_NEEDS_REPAIR)
        self.assertEqual(self.device.status, Device.STATUS_REPAIR)

    def test_returned_checkout_without_condition_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Checkout.objects.create(
                    company=self.company,
                    employee=self.employee,
                    device=self.device,
                    requested_device_name="",
                    status=Checkout.STATUS_RETURNED,
                    return_condition="",
                )
