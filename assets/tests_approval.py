from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .forms import CheckoutAssignForm
from .models import Category, Checkout, Device


class ApprovalAndAssignmentRequirementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="approveadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(name="Approve Co", code="CMP-APP001", admin=self.admin)
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="approveemp", password="empass12345", role=User.ROLE_EMPLOYEE,
        )
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="APP-DEV-1", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_AVAILABLE,
        )
        self.client.force_login(self.admin)

    def _make_pending_checkout(self, device=None, name=None):
        return Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            created_by=self.employee,
            device=device,
            requested_device_name=name or "",
            status=Checkout.STATUS_PENDING,
        )

    def test_admin_can_approve_request(self):
        checkout = self._make_pending_checkout(device=self.device)
        response = self.client.post(reverse("assets:checkout_approve", args=[checkout.pk]))
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_ACTIVE)
        self.assertEqual(checkout.approved_by, self.admin)
        self.assertIsNotNone(checkout.checked_out_at)
        self.assertEqual(checkout.due_date, timezone.localdate() + timedelta(days=7))
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_admin_can_reject_request(self):
        checkout = self._make_pending_checkout(device=self.device)
        self.client.post(reverse("assets:checkout_reject", args=[checkout.pk]))
        checkout.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_REJECTED)
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_approval_rejects_device_with_existing_active_checkout(self):
        Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            device=self.device,
            requested_device_name="",
            status=Checkout.STATUS_ACTIVE,
        )
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        pending = self._make_pending_checkout(device=self.device)
        self.client.post(reverse("assets:checkout_approve", args=[pending.pk]))
        pending.refresh_from_db()
        self.assertEqual(pending.status, Checkout.STATUS_PENDING)

    def test_assignment_rejects_device_with_existing_active_checkout(self):
        Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            device=self.device,
            requested_device_name="",
            status=Checkout.STATUS_ACTIVE,
        )
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        form = CheckoutAssignForm(company=self.company, data={
            "device": self.device.pk,
            "employee": self.employee.pk,
            "due_date": timezone.localdate().isoformat(),
            "purpose": "test",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("device", form.errors)

    def test_admin_can_directly_assign_device(self):
        response = self.client.post(reverse("assets:checkout_assign"), {
            "device": self.device.pk,
            "employee": self.employee.pk,
            "due_date": (timezone.localdate() + timedelta(days=3)).isoformat(),
            "purpose": "Direct issue",
        })
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        checkout = Checkout.objects.get(device=self.device, status=Checkout.STATUS_ACTIVE)
        self.assertEqual(checkout.employee, self.employee)
        self.assertEqual(checkout.approved_by, self.admin)
        self.assertEqual(checkout.purpose, "Direct issue")
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_new_model_request_redirects_to_device_creation(self):
        checkout = self._make_pending_checkout(name="Tablet Pro")
        response = self.client.get(reverse("assets:checkout_approve", args=[checkout.pk]))
        self.assertRedirects(
            response,
            f"{reverse('assets:device_create')}?request_id={checkout.pk}&model_name=Tablet+Pro",
        )

    def test_invalid_checkout_status_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Checkout.objects.create(
                    company=self.company,
                    employee=self.employee,
                    device=self.device,
                    requested_device_name="",
                    status="unknown",
                )
