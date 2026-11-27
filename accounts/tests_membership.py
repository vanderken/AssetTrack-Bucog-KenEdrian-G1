from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import CompanyForm
from .models import Company, CompanyMembershipRequest, User


class CompanyMembershipRequirementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="membershipadmin", password="adminpass123",
            role=User.ROLE_ADMIN,
        )
        self.company = Company.objects.create(name="KMB", code="CMP-KMB001", admin=self.admin)
        self.admin.company = self.company
        self.admin.save(update_fields=["company"])
        self.employee = User.objects.create_user(
            username="memberemp", password="empass12345",
            role=User.ROLE_EMPLOYEE,
        )
        self.client.force_login(self.admin)

    def test_join_code_is_unique_case_insensitively(self):
        form = CompanyForm(data={"name": "Other", "address": "", "code": "cmp-kmb001"})
        self.assertFalse(form.is_valid())
        self.assertIn("code", form.errors)

        form = CompanyForm(data={"name": "Other", "address": "", "code": "cmp-new002"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["code"], "CMP-NEW002")

    def test_employee_cannot_submit_second_pending_join_request(self):
        CompanyMembershipRequest.objects.create(
            company=self.company,
            user=self.employee,
            request_type=CompanyMembershipRequest.TYPE_JOIN,
            status=CompanyMembershipRequest.STATUS_PENDING,
        )
        second_company = Company.objects.create(name="Second Co", code="CMP-SEC002")
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("accounts:employee_join_company"),
            {"company_code": second_company.code},
        )
        self.assertEqual(response.status_code, 200)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.company)
        self.assertEqual(
            CompanyMembershipRequest.objects.filter(user=self.employee).count(), 1
        )

    def test_employee_with_company_cannot_join_another(self):
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("accounts:employee_join_company"),
            {"company_code": "CMP-NEW002"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CompanyMembershipRequest.objects.filter(user=self.employee).exists())

    def test_admin_accept_and_reject_join_request(self):
        join_request = CompanyMembershipRequest.objects.create(
            company=self.company,
            user=self.employee,
            request_type=CompanyMembershipRequest.TYPE_JOIN,
            status=CompanyMembershipRequest.STATUS_PENDING,
        )
        url = reverse("accounts:company_request_review", args=[
            join_request.pk, "accept",
        ])
        self.client.post(url)
        self.employee.refresh_from_db()
        join_request.refresh_from_db()
        self.assertEqual(self.employee.company, self.company)
        self.assertEqual(join_request.status, CompanyMembershipRequest.STATUS_APPROVED)

        reject_request = CompanyMembershipRequest.objects.create(
            company=self.company,
            user=self.employee,
            request_type=CompanyMembershipRequest.TYPE_LEAVE,
            status=CompanyMembershipRequest.STATUS_PENDING,
        )
        self.client.post(reverse("accounts:company_request_review", args=[
            reject_request.pk, "reject",
        ]))
        reject_request.refresh_from_db()
        self.assertEqual(reject_request.status, CompanyMembershipRequest.STATUS_REJECTED)
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.company, self.company)

    def test_admin_accept_leave_request_clears_company(self):
        self.employee.company = self.company
        self.employee.save(update_fields=["company"])
        leave_request = CompanyMembershipRequest.objects.create(
            company=self.company,
            user=self.employee,
            request_type=CompanyMembershipRequest.TYPE_LEAVE,
            status=CompanyMembershipRequest.STATUS_PENDING,
        )
        self.client.post(reverse("accounts:company_request_review", args=[
            leave_request.pk, "accept",
        ]))
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.company)

    def test_other_company_admin_cannot_review_request(self):
        other_admin = User.objects.create_user(
            username="otheradmin", password="adminpass123",
            role=User.ROLE_ADMIN,
        )
        other_company = Company.objects.create(name="Other", code="CMP-OTH003", admin=other_admin)
        other_admin.company = other_company
        other_admin.save(update_fields=["company"])
        join_request = CompanyMembershipRequest.objects.create(
            company=self.company,
            user=self.employee,
            request_type=CompanyMembershipRequest.TYPE_JOIN,
        )
        self.client.force_login(other_admin)
        response = self.client.post(reverse("accounts:company_request_review", args=[
            join_request.pk, "accept",
        ]))
        self.assertEqual(response.status_code, 404)
        join_request.refresh_from_db()
        self.assertEqual(join_request.status, CompanyMembershipRequest.STATUS_PENDING)

    def test_invalid_membership_status_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CompanyMembershipRequest.objects.create(
                    company=self.company,
                    user=self.employee,
                    request_type=CompanyMembershipRequest.TYPE_JOIN,
                    status="unknown",
                )
