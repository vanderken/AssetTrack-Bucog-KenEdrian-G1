from urllib.parse import urlencode

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User, Company
from assets.models import Device, Category, Checkout, SystemSettings
from assets.forms import DeviceForm, CheckoutAssignForm, CheckoutRequestForm, DEFAULT_CATEGORIES


class CategoryAndDeviceFormTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminuser",
            email="admin@example.com",
            password="adminpassword123",
            role=User.ROLE_ADMIN,
        )
        self.client = Client()
        self.client.force_login(self.admin)

    def test_device_form_choices_include_defaults_and_custom_as_last(self):
        form = DeviceForm()
        choice_labels = [label for _, label in form.fields["category"].choices]
        self.assertEqual(choice_labels[0], "-- Select Category --")
        self.assertIn("Laptop", choice_labels)
        self.assertIn("Computer Parts", choice_labels)
        self.assertIn("Tools", choice_labels)
        self.assertEqual(choice_labels[-1], "+ Add Custom Category / Other")
        self.assertEqual(form.fields["category"].choices[-1][0], DeviceForm.CUSTOM_CATEGORY_VALUE)

    def test_device_form_standard_category_save(self):
        DeviceForm()
        laptop_cat = Category.objects.get(name="Laptop")
        form_data = {
            "asset_tag": "DEV-001",
            "serial_number": "SN-001",
            "model_name": "Dell XPS 15",
            "status": Device.STATUS_AVAILABLE,
            "category": str(laptop_cat.pk),
        }
        form = DeviceForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        device = form.save()
        self.assertEqual(device.category.name, "Laptop")
        self.assertEqual(device.display_category, "Laptop")
        self.assertFalse(hasattr(device, "custom_category_label"))

    def test_device_form_custom_category_creation(self):
        form_data = {
            "asset_tag": "DEV-002",
            "serial_number": "SN-002",
            "model_name": "Epson 4K Projector",
            "status": Device.STATUS_AVAILABLE,
            "category": DeviceForm.CUSTOM_CATEGORY_VALUE,
            "custom_category": "Projector",
        }
        form = DeviceForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        device = form.save()
        self.assertEqual(device.category.name, "Projector")
        self.assertTrue(Category.objects.filter(name="Projector").exists())
        self.assertEqual(device.display_category, "Projector")

    def test_device_form_custom_category_requires_name(self):
        form_data = {
            "asset_tag": "DEV-003",
            "serial_number": "SN-003",
            "model_name": "No-Cat Device",
            "status": Device.STATUS_AVAILABLE,
            "category": DeviceForm.CUSTOM_CATEGORY_VALUE,
            "custom_category": "   ",
        }
        form = DeviceForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("custom_category", form.errors)

    def test_serial_number_optional_multiple_empty_devices(self):
        DeviceForm()
        laptop_cat = Category.objects.get(name="Laptop")
        d1 = Device.objects.create(
            asset_tag="TAG-NO-SN-1",
            serial_number="",
            model_name="Generic Keyboard",
            category=laptop_cat,
        )
        d2 = Device.objects.create(
            asset_tag="TAG-NO-SN-2",
            serial_number=None,
            model_name="Generic Mouse",
            category=laptop_cat,
        )
        self.assertIsNone(d1.serial_number)
        self.assertIsNone(d2.serial_number)
        self.assertEqual(Device.objects.count(), 2)


class CompanyScopingBase(TestCase):
    def setUp(self):
        self.laptop, _ = Category.objects.get_or_create(name="Laptop")

        self.admin_a = User.objects.create_user("admin_a", "a@a.com", "pass12345", role=User.ROLE_ADMIN)
        self.company_a = Company.objects.create(name="Company A", code="CMP-AAAAAA", admin=self.admin_a)
        self.admin_a.company = self.company_a
        self.admin_a.save()
        self.emp_a = User.objects.create_user("emp_a", "ea@a.com", "pass12345", role=User.ROLE_EMPLOYEE, company=self.company_a)

        self.admin_b = User.objects.create_user("admin_b", "b@b.com", "pass12345", role=User.ROLE_ADMIN)
        self.company_b = Company.objects.create(name="Company B", code="CMP-BBBBBB", admin=self.admin_b)
        self.admin_b.company = self.company_b
        self.admin_b.save()
        self.emp_b = User.objects.create_user("emp_b", "eb@b.com", "pass12345", role=User.ROLE_EMPLOYEE, company=self.company_b)

        self.dev_a = Device.objects.create(
            company=self.company_a, asset_tag="A-001", model_name="A Laptop", category=self.laptop,
        )
        self.dev_b = Device.objects.create(
            company=self.company_b, asset_tag="B-001", model_name="B Laptop", category=self.laptop,
        )

        settings_obj = SystemSettings.get_solo()
        settings_obj.self_checkout_allowed = True
        settings_obj.save()

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client


class AdminCompanyScopeTests(CompanyScopingBase):
    def test_unaffiliated_admin_is_redirected_from_every_admin_page(self):
        loner = User.objects.create_user("loner", "l@l.com", "pass12345", role=User.ROLE_ADMIN)
        client = self.login(loner)
        for name in [
            "assets:device_list", "assets:device_create", "assets:checkout_requests",
            "assets:checkout_assign", "assets:active_checkouts", "assets:maintenance_list",
            "assets:reports", "assets:system_settings",
        ]:
            response = client.get(reverse(name))
            self.assertRedirects(response, reverse("accounts:company_manage"), msg_prefix=name)

    def test_admin_only_sees_own_company_devices(self):
        response = self.login(self.admin_a).get(reverse("assets:device_list"))
        tags = [d.asset_tag for d in response.context["devices"]]
        self.assertEqual(tags, ["A-001"])

    def test_admin_cannot_edit_or_delete_other_company_device(self):
        client = self.login(self.admin_a)
        self.assertEqual(client.get(reverse("assets:device_edit", args=[self.dev_b.pk])).status_code, 404)
        self.assertEqual(client.post(reverse("assets:device_delete", args=[self.dev_b.pk])).status_code, 404)
        self.assertTrue(Device.objects.filter(pk=self.dev_b.pk).exists())

    def test_new_device_is_saved_under_admin_company(self):
        response = self.login(self.admin_a).post(reverse("assets:device_create"), {
            "asset_tag": "A-002", "model_name": "New A", "status": Device.STATUS_AVAILABLE,
            "category": str(self.laptop.pk),
        })
        self.assertRedirects(response, reverse("assets:device_list"))
        self.assertEqual(Device.objects.get(asset_tag="A-002").company, self.company_a)

    def test_assign_form_lists_only_company_devices_and_employees(self):
        form = CheckoutAssignForm(company=self.company_a)
        self.assertEqual(list(form.fields["device"].queryset), [self.dev_a])
        self.assertEqual(list(form.fields["employee"].queryset), [self.emp_a])

    def test_checkout_assign_redirects_when_no_devices_available(self):
        self.dev_a.status = Device.STATUS_BORROWED
        self.dev_a.save()
        response = self.login(self.admin_a).get(reverse("assets:checkout_assign"))
        self.assertRedirects(response, reverse("assets:device_create"))


class EmployeeRequestTests(CompanyScopingBase):
    def test_request_form_only_offers_own_company_devices(self):
        form = CheckoutRequestForm(company=self.company_a)
        self.assertEqual(list(form.fields["device"].queryset), [self.dev_a])

    def test_employee_cannot_request_other_company_device(self):
        response = self.login(self.emp_a).post(reverse("assets:my_checkout_request"), {
            "device": self.dev_b.pk, "purpose": "test",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Checkout.objects.exists())

    def test_employee_can_request_device_not_in_inventory(self):
        response = self.login(self.emp_a).post(reverse("assets:my_checkout_request"), {
            "requested_device_name": "Dell XPS 13", "requested_category": self.laptop.pk, "purpose": "work",
        })
        self.assertRedirects(response, reverse("accounts:employee_dashboard"))
        checkout = Checkout.objects.get()
        self.assertIsNone(checkout.device)
        self.assertEqual(checkout.company, self.company_a)
        self.assertEqual(checkout.requested_device_name, "Dell XPS 13")
        self.assertEqual(checkout.status, Checkout.STATUS_PENDING)

    def test_unaffiliated_employee_must_join_company_first(self):
        loner = User.objects.create_user("loner", "l@l.com", "pass12345", role=User.ROLE_EMPLOYEE)
        response = self.login(loner).get(reverse("assets:my_checkout_request"))
        self.assertRedirects(response, reverse("accounts:employee_join_company"))


class RequestForNewDeviceFlowTests(CompanyScopingBase):
    def setUp(self):
        super().setUp()
        self.req = Checkout.objects.create(
            company=self.company_a, employee=self.emp_a, status=Checkout.STATUS_PENDING,
            requested_device_name="MacBook Pro & Co", requested_category=self.laptop,
        )

    def test_approving_request_without_device_redirects_to_prefilled_add_device(self):
        response = self.login(self.admin_a).post(reverse("assets:checkout_approve", args=[self.req.pk]))
        expected = reverse("assets:device_create") + "?" + urlencode({
            "request_id": self.req.pk, "model_name": "MacBook Pro & Co", "category": self.laptop.pk,
        })
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_add_device_form_is_prefilled_with_requested_name(self):
        response = self.login(self.admin_a).get(reverse("assets:device_create"), {"request_id": self.req.pk})
        self.assertEqual(response.context["form"].initial["model_name"], "MacBook Pro & Co")
        self.assertEqual(response.context["fulfilling_request"], self.req)

    def test_saving_device_assigns_it_to_requester(self):
        response = self.login(self.admin_a).post(reverse("assets:device_create"), {
            "request_id": self.req.pk, "asset_tag": "A-NEW", "model_name": "MacBook Pro & Co",
            "status": Device.STATUS_AVAILABLE, "category": str(self.laptop.pk),
        })
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        self.req.refresh_from_db()
        device = Device.objects.get(asset_tag="A-NEW")
        self.assertEqual(device.company, self.company_a)
        self.assertEqual(device.status, Device.STATUS_BORROWED)
        self.assertEqual(self.req.device, device)
        self.assertEqual(self.req.status, Checkout.STATUS_ACTIVE)

    def test_other_company_admin_cannot_touch_the_request(self):
        client = self.login(self.admin_b)
        self.assertEqual(client.post(reverse("assets:checkout_approve", args=[self.req.pk])).status_code, 404)
        response = client.get(reverse("assets:device_create"), {"request_id": self.req.pk})
        self.assertRedirects(response, reverse("assets:checkout_requests"))
        pending_ids = [c.pk for c in client.get(reverse("assets:checkout_requests")).context["pending"]]
        self.assertNotIn(self.req.pk, pending_ids)


class DepartmentAndCategoryUrlTests(CompanyScopingBase):
    def test_categories_url_lists_categories(self):
        response = self.login(self.admin_a).get("/assets/categories/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Categories")

    def test_departments_url_lists_departments(self):
        response = self.login(self.admin_a).get("/assets/departments/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Departments")


class CoreFeatureOwnershipAndValidationTests(CompanyScopingBase):
    def test_device_and_request_records_store_their_creator(self):
        self.login(self.admin_a).post(reverse("assets:device_create"), {
            "asset_tag": "A-CREATOR", "model_name": "ThinkPad X1",
            "status": Device.STATUS_AVAILABLE, "category": str(self.laptop.pk),
        })
        device = Device.objects.get(asset_tag="A-CREATOR")
        self.assertEqual(device.created_by, self.admin_a)

        self.login(self.emp_a).post(reverse("assets:my_checkout_request"), {
            "requested_device_name": "Dell Latitude", "purpose": "field work",
        })
        request = Checkout.objects.get(requested_device_name="Dell Latitude")
        self.assertEqual(request.created_by, self.emp_a)
        self.assertEqual(request.employee, self.emp_a)

    def test_device_with_checkout_history_cannot_be_deleted(self):
        Checkout.objects.create(
            company=self.company_a, employee=self.emp_a, device=self.dev_a,
            status=Checkout.STATUS_ACTIVE,
        )
        response = self.login(self.admin_a).post(reverse("assets:device_delete", args=[self.dev_a.pk]))
        self.assertRedirects(response, reverse("assets:device_list"))
        self.assertTrue(Device.objects.filter(pk=self.dev_a.pk).exists())

    def test_admin_cannot_submit_an_employee_checkout_request(self):
        response = self.login(self.admin_a).get(reverse("assets:my_checkout_request"))
        self.assertEqual(response.status_code, 403)

    def test_assignment_rejects_a_past_due_date(self):
        form = CheckoutAssignForm(company=self.company_a, data={
            "device": self.dev_a.pk,
            "employee": self.emp_a.pk,
            "due_date": (timezone.localdate() - timezone.timedelta(days=1)).isoformat(),
            "purpose": "testing",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("due_date", form.errors)