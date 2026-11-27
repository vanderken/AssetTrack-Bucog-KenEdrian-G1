from django.test import TestCase
from django.urls import reverse

from assets.models import Department
from .forms import RegistrationForm
from .models import User


class DepartmentManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="deptadmin", password="adminpass123",
            role=User.ROLE_ADMIN,
        )
        self.employee = User.objects.create_user(
            username="deptemp", password="empass12345",
            role=User.ROLE_EMPLOYEE,
        )
        self.client.force_login(self.admin)

    def test_admin_can_create_edit_and_delete_department(self):
        response = self.client.post(reverse("assets:department_create"), {"name": "Engineering"})
        self.assertRedirects(response, reverse("assets:department_list"))
        department = Department.objects.get(name="Engineering")

        response = self.client.post(
            reverse("assets:department_edit", args=[department.pk]),
            {"name": "IT Support"},
        )
        self.assertRedirects(response, reverse("assets:department_list"))
        department.refresh_from_db()
        self.assertEqual(department.name, "IT Support")

        response = self.client.post(reverse("assets:department_delete", args=[department.pk]))
        self.assertRedirects(response, reverse("assets:department_list"))
        self.assertFalse(Department.objects.filter(pk=department.pk).exists())

    def test_department_name_is_unique(self):
        Department.objects.create(name="Finance")
        form = RegistrationForm(data={
            "username": "newuser", "first_name": "New", "last_name": "User",
            "email": "new@example.com", "role": User.ROLE_EMPLOYEE,
            "department": Department.objects.get(name="Finance").pk,
            "password1": "StrongPass123!", "password2": "StrongPass123!",
        })
        self.assertTrue(form.is_valid())
        user = form.save()
        self.assertEqual(user.department.name, "Finance")

        from assets.forms import DepartmentForm
        self.assertFalse(DepartmentForm(data={"name": "Finance"}).is_valid())

    def test_profile_edit_can_assign_department(self):
        department = Department.objects.create(name="Operations")
        self.client.force_login(self.employee)
        response = self.client.post(reverse("accounts:profile_edit"), {
            "first_name": "Emp", "last_name": "Loyee",
            "email": "emp@example.com", "contact_number": "09170000000",
            "department": department.pk,
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.department, department)

    def test_deleting_department_unassigns_members(self):
        department = Department.objects.create(name="Sales")
        self.employee.department = department
        self.employee.save(update_fields=["department"])
        self.client.force_login(self.admin)
        self.client.post(reverse("assets:department_delete", args=[department.pk]))
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.department)

    def test_employee_cannot_access_department_pages(self):
        self.client.force_login(self.employee)
        for name in ("department_list", "department_create"):
            response = self.client.get(reverse(f"assets:{name}"))
            self.assertEqual(response.status_code, 403)
