from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Company, User
from .forms import CheckoutRequestForm
from .models import Category, Checkout, Device, SystemSettings


class BorrowingRequestRequirementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="reqadmin", password="adminpass123", role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(name="Req Co", code="CMP-REQ001", admin=self.admin)
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="reqemp", password="empass12345", role=User.ROLE_EMPLOYEE,
        )
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])
        self.category = Category.objects.create(name="Laptop")
        self.device = Device.objects.create(
            company=self.company, asset_tag="REQ-DEV-1", model_name="ThinkPad",
            category=self.category, status=Device.STATUS_AVAILABLE,
        )
        settings_obj = SystemSettings.get_solo()
        settings_obj.self_checkout_allowed = True
        settings_obj.save()
        self.url = reverse("assets:my_checkout_request")

    def test_employee_can_request_available_device(self):
        self.client.force_login(self.employee)
        response = self.client.post(self.url, {
            "device": self.device.pk,
            "purpose": "Client presentation",
        })
        self.assertRedirects(response, reverse("accounts:employee_dashboard"))
        checkout = Checkout.objects.get(device=self.device)
        self.assertEqual(checkout.employee, self.employee)
        self.assertEqual(checkout.created_by, self.employee)
        self.assertEqual(checkout.company, self.company)
        self.assertEqual(checkout.status, Checkout.STATUS_PENDING)
        self.assertEqual(checkout.purpose, "Client presentation")
        self.assertIsNotNone(checkout.requested_at)
        self.assertLessEqual(checkout.requested_at, timezone.now())

    def test_employee_can_request_new_model(self):
        self.client.force_login(self.employee)
        response = self.client.post(self.url, {
            "requested_device_name": "MacBook Pro 16",
            "requested_category": self.category.pk,
            "purpose": "Field work",
        })
        self.assertRedirects(response, reverse("accounts:employee_dashboard"))
        checkout = Checkout.objects.get(requested_device_name="MacBook Pro 16")
        self.assertIsNone(checkout.device)
        self.assertEqual(checkout.requested_category, self.category)
        self.assertEqual(checkout.status, Checkout.STATUS_PENDING)

    def test_request_requires_device_or_new_model(self):
        form = CheckoutRequestForm(data={"purpose": "No target"}, company=self.company)
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_borrowed_device_cannot_be_requested(self):
        self.device.status = Device.STATUS_BORROWED
        self.device.save(update_fields=["status"])
        form = CheckoutRequestForm(data={"device": self.device.pk}, company=self.company)
        self.assertFalse(form.is_valid())
        self.assertIn("device", form.errors)

    def test_cross_company_device_cannot_be_requested(self):
        other_company = Company.objects.create(name="Other Co", code="CMP-OTH001")
        other_device = Device.objects.create(
            company=other_company, asset_tag="REQ-OTHER", model_name="X",
            category=self.category,
        )
        form = CheckoutRequestForm(data={"device": other_device.pk}, company=self.company)
        self.assertFalse(form.is_valid())
        self.assertIn("device", form.errors)

        self.client.force_login(self.employee)
        self.client.post(self.url, {"device": other_device.pk})
        self.assertFalse(Checkout.objects.filter(device=other_device).exists())

    def test_self_checkout_disabled_blocks_requests(self):
        settings_obj = SystemSettings.get_solo()
        settings_obj.self_checkout_allowed = False
        settings_obj.save()
        self.client.force_login(self.employee)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_employee_without_company_is_redirected(self):
        self.employee.company = None
        self.employee.save(update_fields=["company"])
        self.client.force_login(self.employee)
        response = self.client.get(self.url)
        self.assertRedirects(response, reverse("accounts:employee_join_company"))

    def test_admin_cannot_submit_employee_request(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
