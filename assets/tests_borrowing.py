"""Feature 2 verification: borrowing transaction (employee request -> staff release)."""

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from assets.models import Category, Checkout, Device, SystemSettings


class BorrowingTransactionTests(TestCase):
    def setUp(self):
        self.category, _ = Category.objects.get_or_create(name="Laptop")
        self.admin = User.objects.create_user(
            "borrow_admin", "borrow_admin@example.com", "pass12345",
            role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(
            name="Borrow Co", code="CMP-BRW001", admin=self.admin
        )
        self.admin.company = self.company
        self.admin.save()
        self.employee = User.objects.create_user(
            "borrow_emp", "borrow_emp@example.com", "pass12345",
            role=User.ROLE_EMPLOYEE, company=self.company,
        )
        self.device = Device.objects.create(
            company=self.company, asset_tag="BRW-001",
            model_name="ThinkPad X1", category=self.category,
        )
        settings_obj = SystemSettings.get_solo()
        settings_obj.self_checkout_allowed = True
        settings_obj.save()

        self.admin_client = Client()
        self.admin_client.force_login(self.admin)
        self.emp_client = Client()
        self.emp_client.force_login(self.employee)

    def pending_checkout(self):
        return Checkout.objects.create(
            company=self.company,
            employee=self.employee,
            device=self.device,
            status=Checkout.STATUS_PENDING,
        )

    def test_employee_request_creates_pending_record_linked_to_user(self):
        response = self.emp_client.post(
            reverse("assets:my_checkout_request"),
            {"device": self.device.pk, "purpose": "Class project"},
        )
        self.assertRedirects(response, reverse("accounts:employee_dashboard"))
        checkout = Checkout.objects.get()
        self.assertEqual(checkout.employee, self.employee)
        self.assertEqual(checkout.created_by, self.employee)
        self.assertEqual(checkout.company, self.company)
        self.assertEqual(checkout.device, self.device)
        self.assertEqual(checkout.status, Checkout.STATUS_PENDING)

    def test_admin_approval_activates_checkout_and_marks_device_borrowed(self):
        checkout = self.pending_checkout()
        response = self.admin_client.post(
            reverse("assets:checkout_approve", args=[checkout.pk])
        )
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_ACTIVE)
        self.assertEqual(checkout.approved_by, self.admin)
        self.assertIsNotNone(checkout.checked_out_at)
        self.assertIsNotNone(checkout.due_date)
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_admin_rejection_leaves_device_available(self):
        checkout = self.pending_checkout()
        response = self.admin_client.post(
            reverse("assets:checkout_reject", args=[checkout.pk])
        )
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_REJECTED)
        self.assertEqual(self.device.status, Device.STATUS_AVAILABLE)

    def test_direct_assignment_creates_active_checkout(self):
        due_date = (timezone.localdate() + timezone.timedelta(days=5)).isoformat()
        response = self.admin_client.post(reverse("assets:checkout_assign"), {
            "device": self.device.pk,
            "employee": self.employee.pk,
            "due_date": due_date,
            "purpose": "Lab use",
        })
        self.assertRedirects(response, reverse("assets:active_checkouts"))
        checkout = Checkout.objects.get()
        self.assertEqual(checkout.status, Checkout.STATUS_ACTIVE)
        self.assertEqual(checkout.created_by, self.admin)
        self.assertEqual(checkout.approved_by, self.admin)
        self.assertEqual(checkout.device, self.device)
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.STATUS_BORROWED)

    def test_approval_of_unavailable_device_is_blocked(self):
        self.device.status = Device.STATUS_REPAIR
        self.device.save()
        checkout = self.pending_checkout()
        response = self.admin_client.post(
            reverse("assets:checkout_approve", args=[checkout.pk])
        )
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        checkout.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(checkout.status, Checkout.STATUS_PENDING)
        self.assertEqual(self.device.status, Device.STATUS_REPAIR)

    def test_other_company_admin_cannot_approve_request(self):
        other_admin = User.objects.create_user(
            "other_borrow_admin", "other@example.com", "pass12345",
            role=User.ROLE_ADMIN,
        )
        other_company = Company.objects.create(
            name="Other Co", code="CMP-BRW002", admin=other_admin
        )
        other_admin.company = other_company
        other_admin.save()
        client = Client()
        client.force_login(other_admin)
        checkout = self.pending_checkout()
        self.assertEqual(
            client.post(
                reverse("assets:checkout_approve", args=[checkout.pk])
            ).status_code,
            404,
        )
