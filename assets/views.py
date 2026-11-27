from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Prefetch
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from urllib.parse import urlencode

from accounts.decorators import role_required
from accounts.models import User
from .forms import (
    DeviceForm, CheckoutRequestForm,
    CheckoutAssignForm, MaintenanceLogForm, DepartmentForm, SystemSettingsForm,
)
from .models import Device, Category, Checkout, Department, MaintenanceLog, SystemSettings


def get_admin_company(request):
    return request.user.company or request.user.administered_companies.first()


@role_required(User.ROLE_ADMIN)
def device_list(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before managing devices.")
        return redirect("accounts:company_manage")

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    category_id = request.GET.get("category", "").strip()

    active_checkouts_prefetch = Prefetch(
        "checkouts",
        queryset=Checkout.objects.filter(status=Checkout.STATUS_ACTIVE).select_related("employee"),
        to_attr="prefetched_active_checkouts",
    )

    devices = Device.objects.filter(company=admin_company).select_related("category").prefetch_related(active_checkouts_prefetch)

    if query:
        devices = devices.filter(
            Q(serial_number__icontains=query) | Q(asset_tag__icontains=query) | Q(model_name__icontains=query)
        )
    if status:
        devices = devices.filter(status=status)
    if category_id:
        devices = devices.filter(category_id=category_id)

    categories = Category.objects.all().order_by("name")

    context = {
        "company": admin_company,
        "devices": devices,
        "query": query,
        "status": status,
        "selected_category": category_id,
        "categories": categories,
        "status_choices": Device.STATUS_CHOICES,
    }
    return render(request, "assets/device_list.html", context)


@role_required(User.ROLE_ADMIN)
def device_create(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before adding devices.")
        return redirect("accounts:company_manage")

    settings_obj = SystemSettings.get_solo()
    request_id = request.GET.get("request_id") or request.POST.get("request_id")
    fulfilling_request = None
    if request_id:
        fulfilling_request = Checkout.objects.filter(
            pk=request_id,
            company=admin_company,
            status=Checkout.STATUS_PENDING,
        ).select_related("employee", "requested_category").first()
        if not fulfilling_request:
            messages.error(request, "That checkout request is not available in your company.")
            return redirect("assets:checkout_requests")

    if request.method == "POST":
        form = DeviceForm(request.POST, settings_obj=settings_obj)
        if form.is_valid():
            device = form.save(commit=False)
            device.company = admin_company
            device.created_by = request.user
            if fulfilling_request:
                device.status = Device.STATUS_BORROWED
                device.save()
                fulfilling_request.device = device
                fulfilling_request.status = Checkout.STATUS_ACTIVE
                fulfilling_request.approved_by = request.user
                fulfilling_request.checked_out_at = timezone.now()
                if not fulfilling_request.due_date:
                    fulfilling_request.due_date = timezone.localdate() + timezone.timedelta(days=settings_obj.overdue_days)
                fulfilling_request.save()
                emp_name = fulfilling_request.employee.get_full_name() or fulfilling_request.employee.username
                messages.success(request, f"Device '{device.asset_tag}' created and assigned to {emp_name}.")
                return redirect("assets:checkout_requests")
            else:
                device.save()
                messages.success(request, f"Device '{device.asset_tag}' successfully added to company inventory.")
                return redirect("assets:device_list")
        messages.error(request, "Please fix the errors below.")
    else:
        initial = {}
        if fulfilling_request:
            if fulfilling_request.requested_device_name:
                initial["model_name"] = fulfilling_request.requested_device_name
            if fulfilling_request.requested_category_id:
                initial["category"] = str(fulfilling_request.requested_category_id)
        elif request.GET.get("model_name"):
            initial["model_name"] = request.GET.get("model_name")
            if request.GET.get("category"):
                initial["category"] = request.GET.get("category")
        form = DeviceForm(initial=initial, settings_obj=settings_obj)

    context = {
        "form": form,
        "mode": "Add",
        "company": admin_company,
        "fulfilling_request": fulfilling_request,
    }
    return render(request, "assets/device_form.html", context)


@role_required(User.ROLE_ADMIN)
def device_edit(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before editing devices.")
        return redirect("accounts:company_manage")

    device = get_object_or_404(Device, pk=pk, company=admin_company)
    settings_obj = SystemSettings.get_solo()
    if request.method == "POST":
        form = DeviceForm(request.POST, instance=device, settings_obj=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"Device '{device.asset_tag}' updated.")
            return redirect("assets:device_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = DeviceForm(instance=device, settings_obj=settings_obj)
    return render(request, "assets/device_form.html", {"form": form, "mode": "Edit", "device": device, "company": admin_company})


@role_required(User.ROLE_ADMIN)
def device_delete(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before removing devices.")
        return redirect("accounts:company_manage")

    device = get_object_or_404(Device, pk=pk, company=admin_company)
    if device.checkouts.exists():
        messages.error(
            request,
            f"Device '{device.asset_tag}' has checkout history and cannot be deleted. "
            "Retire it through the maintenance or status workflow instead.",
        )
        return redirect("assets:device_list")
    if request.method == "POST":
        tag = device.asset_tag
        device.delete()
        messages.success(request, f"Device '{tag}' removed from inventory.")
        return redirect("assets:device_list")
    return render(request, "assets/device_confirm_delete.html", {"device": device})


@role_required(User.ROLE_ADMIN)
def category_redirect(request):
    messages.info(request, "Categories are managed directly when adding or editing devices.")
    return redirect("assets:device_create")


@role_required(User.ROLE_ADMIN)
def department_list(request):
    return render(request, "assets/department_list.html", {
        "departments": Department.objects.all(),
    })


@role_required(User.ROLE_ADMIN)
def department_create(request):
    if request.method == "POST":
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            messages.success(request, f"Department '{department.name}' added.")
            return redirect("assets:department_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = DepartmentForm()
    return render(request, "assets/department_form.html", {"form": form, "mode": "Add"})


@role_required(User.ROLE_ADMIN)
def department_edit(request, pk):
    department = get_object_or_404(Department, pk=pk)
    if request.method == "POST":
        form = DepartmentForm(request.POST, instance=department)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{department.name}' updated.")
            return redirect("assets:department_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = DepartmentForm(instance=department)
    return render(request, "assets/department_form.html", {
        "form": form, "mode": "Edit", "department": department,
    })


@role_required(User.ROLE_ADMIN)
def department_delete(request, pk):
    department = get_object_or_404(Department, pk=pk)
    member_count = department.members.count()
    if request.method == "POST":
        name = department.name
        department.delete()
        messages.success(
            request,
            f"Department '{name}' removed. {member_count} member(s) are now unassigned.",
        )
        return redirect("assets:department_list")
    return render(request, "assets/department_confirm_delete.html", {
        "department": department, "member_count": member_count,
    })


@role_required(User.ROLE_ADMIN)
def checkout_requests(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before reviewing requests.")
        return redirect("accounts:company_manage")

    pending = Checkout.objects.filter(company=admin_company, status=Checkout.STATUS_PENDING).select_related("device", "employee", "requested_category")
    return render(request, "assets/checkout_requests.html", {"pending": pending, "company": admin_company})


@role_required(User.ROLE_ADMIN)
def checkout_approve(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before approving requests.")
        return redirect("accounts:company_manage")

    checkout = get_object_or_404(Checkout, pk=pk, company=admin_company, status=Checkout.STATUS_PENDING)
    if checkout.device is None:
        params = {"request_id": checkout.pk}
        if checkout.requested_device_name:
            params["model_name"] = checkout.requested_device_name
        if checkout.requested_category_id:
            params["category"] = checkout.requested_category_id
        return redirect(f"{reverse('assets:device_create')}?{urlencode(params)}")

    if request.method == "POST":
        if checkout.device.status != Device.STATUS_AVAILABLE:
            messages.error(
                request,
                f"Device '{checkout.device.asset_tag}' is no longer available (currently {checkout.device.get_status_display()})."
            )
            return redirect("assets:checkout_requests")
        settings_obj = SystemSettings.get_solo()
        checkout.status = Checkout.STATUS_ACTIVE
        checkout.approved_by = request.user
        checkout.checked_out_at = timezone.now()
        if not checkout.due_date:
            checkout.due_date = timezone.localdate() + timezone.timedelta(days=settings_obj.overdue_days)
        checkout.save()
        checkout.device.status = Device.STATUS_BORROWED
        checkout.device.save()
        borrower_name = checkout.employee.get_full_name() or checkout.employee.username
        messages.success(request, f"Checkout approved for {borrower_name}.")
    return redirect("assets:checkout_requests")


@role_required(User.ROLE_ADMIN)
def checkout_reject(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    checkout = get_object_or_404(Checkout, pk=pk, company=admin_company, status=Checkout.STATUS_PENDING)
    if request.method == "POST":
        checkout.status = Checkout.STATUS_REJECTED
        checkout.save()
        target_name = checkout.device.asset_tag if checkout.device else (checkout.requested_device_name or "Custom device")
        messages.success(request, f"Request for '{target_name}' rejected.")
    return redirect("assets:checkout_requests")


@role_required(User.ROLE_ADMIN)
def checkout_assign(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company before assigning devices.")
        return redirect("accounts:company_manage")

    if not Device.objects.filter(company=admin_company, status=Device.STATUS_AVAILABLE).exists():
        messages.warning(request, "No available devices in your company to assign. Please add a device first.")
        return redirect("assets:device_create")

    settings_obj = SystemSettings.get_solo()
    if request.method == "POST":
        form = CheckoutAssignForm(request.POST, company=admin_company)
        if form.is_valid():
            checkout = form.save(commit=False)
            checkout.company = admin_company
            checkout.created_by = request.user
            checkout.status = Checkout.STATUS_ACTIVE
            checkout.approved_by = request.user
            checkout.checked_out_at = timezone.now()
            if not checkout.due_date:
                checkout.due_date = timezone.localdate() + timezone.timedelta(days=settings_obj.overdue_days)
            checkout.save()
            checkout.device.status = Device.STATUS_BORROWED
            checkout.device.save()
            borrower_name = checkout.employee.get_full_name() or checkout.employee.username
            messages.success(request, f"Device '{checkout.device.asset_tag}' assigned to {borrower_name}.")
            return redirect("assets:active_checkouts")
        messages.error(request, "Please fix the errors below.")
    else:
        initial = {
            "due_date": timezone.localdate() + timezone.timedelta(days=settings_obj.overdue_days),
        }
        device_id = request.GET.get("device")
        if device_id:
            device_obj = Device.objects.filter(pk=device_id, company=admin_company, status=Device.STATUS_AVAILABLE).first()
            if device_obj:
                initial["device"] = device_obj.pk
        form = CheckoutAssignForm(company=admin_company, initial=initial)
    return render(request, "assets/checkout_assign.html", {"form": form})


@role_required(User.ROLE_ADMIN)
def active_checkouts(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    checkouts = Checkout.objects.filter(company=admin_company, status=Checkout.STATUS_ACTIVE).select_related("device", "employee")
    return render(request, "assets/active_checkouts.html", {
        "checkouts": checkouts,
        "company": admin_company,
        "return_condition_choices": Checkout.CONDITION_CHOICES,
    })


@role_required(User.ROLE_ADMIN)
def checkout_return(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    checkout = get_object_or_404(Checkout, pk=pk, company=admin_company, status=Checkout.STATUS_ACTIVE)
    if request.method == "POST":
        condition = request.POST.get("return_condition", Checkout.CONDITION_GOOD)
        condition_labels = dict(Checkout.CONDITION_CHOICES)
        if condition not in condition_labels:
            messages.error(request, "Please select a valid condition for the returned device.")
            return redirect("assets:active_checkouts")

        checkout.status = Checkout.STATUS_RETURNED
        checkout.returned_at = timezone.now()
        checkout.return_condition = condition
        checkout.save()
        if checkout.device:
            needs_repair = condition in (Checkout.CONDITION_DAMAGED, Checkout.CONDITION_NEEDS_REPAIR)
            checkout.device.status = Device.STATUS_REPAIR if needs_repair else Device.STATUS_AVAILABLE
            checkout.device.save()
            status_note = "marked as Under Repair" if needs_repair else "now available"
            messages.success(
                request,
                f"Device '{checkout.device.asset_tag}' returned in {condition_labels[condition].lower()} "
                f"condition and is {status_note}.",
            )
        else:
            messages.success(request, "Checkout marked as returned.")

    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url == "device_list":
        return redirect("assets:device_list")
    return redirect("assets:active_checkouts")


@role_required(User.ROLE_EMPLOYEE)
def my_checkout_request(request):
    if not request.user.company:
        messages.warning(request, "You must join a company before requesting devices.")
        return redirect("accounts:employee_join_company")

    settings_obj = SystemSettings.get_solo()
    if not settings_obj.self_checkout_allowed:
        raise PermissionDenied

    if request.method == "POST":
        form = CheckoutRequestForm(request.POST, company=request.user.company)
        if form.is_valid():
            checkout = form.save(commit=False)
            checkout.employee = request.user
            checkout.created_by = request.user
            checkout.company = request.user.company
            checkout.status = Checkout.STATUS_PENDING
            checkout.save()
            target_desc = checkout.device.asset_tag if checkout.device else (checkout.requested_device_name or "custom device")
            messages.success(request, f"Device request for '{target_desc}' submitted successfully. Awaiting IT admin approval.")
            return redirect("accounts:employee_dashboard")
        messages.error(request, "Please fix the errors below.")
    else:
        form = CheckoutRequestForm(company=request.user.company)
    return render(request, "assets/checkout_request_form.html", {"form": form})


@role_required(User.ROLE_ADMIN)
def maintenance_list(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    logs = MaintenanceLog.objects.filter(device__company=admin_company).select_related("device", "reported_by").order_by("-reported_at")
    if request.method == "POST":
        form = MaintenanceLogForm(request.POST, request.FILES, company=admin_company)
        if form.is_valid():
            log = form.save(commit=False)
            log.reported_by = request.user
            log.save()

            if log.device.status == Device.STATUS_BORROWED:
                active_co = Checkout.objects.filter(device=log.device, status=Checkout.STATUS_ACTIVE).first()
                if active_co:
                    active_co.status = Checkout.STATUS_RETURNED
                    active_co.returned_at = timezone.now()
                    active_co.save()

            log.device.status = Device.STATUS_REPAIR
            log.device.save()
            messages.success(request, f"Maintenance log recorded. Device '{log.device.asset_tag}' marked as Under Repair.")
            return redirect("assets:maintenance_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = MaintenanceLogForm(company=admin_company)
    return render(request, "assets/maintenance_list.html", {"logs": logs, "form": form})


@role_required(User.ROLE_ADMIN)
def maintenance_resolve(request, pk):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    log = get_object_or_404(MaintenanceLog, pk=pk, device__company=admin_company)
    if request.method == "POST":
        log.is_resolved = True
        log.resolved_at = timezone.now()
        log.save()
        log.device.status = Device.STATUS_AVAILABLE
        log.device.save()
        messages.success(request, f"Maintenance resolved. Device '{log.device.asset_tag}' returned to Available pool.")
    return redirect("assets:maintenance_list")


@role_required(User.ROLE_ADMIN)
def reports_view(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    devices = Device.objects.filter(company=admin_company).select_related("category")
    categories = Category.objects.all().order_by("name")

    category_summary = []
    for cat in categories:
        cat_devices = [d for d in devices if d.category_id == cat.id]
        if cat_devices:
            category_summary.append({
                "category": cat.name,
                "total": len(cat_devices),
                "available": sum(1 for d in cat_devices if d.status == Device.STATUS_AVAILABLE),
                "borrowed": sum(1 for d in cat_devices if d.status == Device.STATUS_BORROWED),
                "repair": sum(1 for d in cat_devices if d.status == Device.STATUS_REPAIR),
            })

    active_checkouts_qs = Checkout.objects.filter(company=admin_company, status=Checkout.STATUS_ACTIVE).select_related("device", "employee")
    overdue_list = [c for c in active_checkouts_qs if c.is_overdue]

    context = {
        "company": admin_company,
        "total_devices": devices.count(),
        "available_devices": sum(1 for d in devices if d.status == Device.STATUS_AVAILABLE),
        "borrowed_devices": sum(1 for d in devices if d.status == Device.STATUS_BORROWED),
        "under_repair": sum(1 for d in devices if d.status == Device.STATUS_REPAIR),
        "active_checkouts": active_checkouts_qs.count(),
        "overdue": overdue_list,
        "damaged": MaintenanceLog.objects.filter(device__company=admin_company, is_resolved=False).count(),
        "category_summary": category_summary,
        "devices": devices,
    }
    return render(request, "assets/reports.html", context)


@role_required(User.ROLE_ADMIN)
def system_settings_view(request):
    admin_company = get_admin_company(request)
    if not admin_company:
        messages.warning(request, "You must set up or be affiliated with a company.")
        return redirect("accounts:company_manage")

    settings_obj = SystemSettings.get_solo()
    if request.method == "POST":
        form = SystemSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "System settings saved successfully.")
            return redirect("assets:system_settings")
        messages.error(request, "Please fix the errors below.")
    else:
        form = SystemSettingsForm(instance=settings_obj)
    return render(request, "assets/system_settings.html", {"form": form})
