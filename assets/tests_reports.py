from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .models import Category, Checkout, Department, Device, MaintenanceLog


class ReportsAndAlignmentTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="reportsadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Reports Co", code="CMP-RPT001", admin=self.admin,
        )
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="reportsemp", password="empass12345", role=User.ROLE_EMPLOYEE,
            company=self.company,
        )
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="RPT-001", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_AVAILABLE,
        )
        self.client.force_login(self.admin)

    def _active_checkout(self, device, due_date=None):
        return Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            created_by=self.admin,
            device=device,
            requested_device_name="",
            status=Checkout.STATUS_ACTIVE,
            checked_out_at=timezone.now(),
            due_date=due_date or timezone.localdate() + timedelta(days=3),
        )

    def test_reports_show_recent_returns_and_maintenance_counts(self):
        returned = Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            device=self.device,
            requested_device_name="",
            status=Checkout.STATUS_RETURNED,
            returned_at=timezone.now(),
            return_condition=Checkout.CONDITION_DAMAGED,
        )
        MaintenanceLog.objects.create(
            device=self.device, description="Open hinge issue",
        )
        MaintenanceLog.objects.create(
            device=self.device, description="Battery replaced",
            is_resolved=True, resolved_at=timezone.now(),
        )

        response = self.client.get(reverse("assets:reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recently Returned")
        self.assertContains(response, returned.device.asset_tag)
        self.assertContains(response, "Damaged")
        self.assertContains(response, "1 open")
        self.assertContains(response, "1 resolved")

    def test_device_list_checkin_has_condition_selector(self):
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        checkout = self._active_checkout(self.device)

        response = self.client.get(reverse("assets:device_list"))
        self.assertContains(response, 'name="return_condition"')
        self.assertContains(response, "required")

        response = self.client.post(
            reverse("assets:checkout_return", args=[checkout.pk]),
            {"return_condition": Checkout.CONDITION_GOOD, "next": "device_list"},
        )
        self.assertRedirects(response, reverse("assets:device_list"))
        checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_RETURNED)
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_admin_dashboard_overdue_checkin_has_condition_selector(self):
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        self._active_checkout(
            self.device, due_date=timezone.localdate() - timedelta(days=1)
        )

        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="return_condition"')

    def test_invalid_query_parameters_do_not_raise(self):
        response = self.client.get(reverse("assets:device_list"), {
            "category": "not-a-number",
            "status": "unknown-status",
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse("assets:checkout_assign"), {
            "device": "not-a-number",
        })
        self.assertEqual(response.status_code, 200)

    def test_public_registration_cannot_self_assign_admin_role(self):
        department = Department.objects.create(name="Support")
        self.client.logout()
        response = self.client.post(reverse("accounts:register"), {
            "username": "newemployee",
            "first_name": "New",
            "last_name": "Employee",
            "email": "newemployee@example.com",
            "department": department.pk,
            "role": User.ROLE_ADMIN,
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })
        self.assertRedirects(response, reverse("accounts:login"))
        user = User.objects.get(username="newemployee")
        self.assertEqual(user.role, User.ROLE_EMPLOYEE)
        self.assertEqual(user.department, department)

    def test_invalid_return_condition_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Checkout.objects.create(
                    company=self.company,
                    employee=self.employee,
                    device=self.device,
                    requested_device_name="",
                    status=Checkout.STATUS_ACTIVE,
                    return_condition="broken",
                )

    def test_company_code_is_case_insensitively_unique_at_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Company.objects.create(name="Duplicate", code="cmp-rpt001")
