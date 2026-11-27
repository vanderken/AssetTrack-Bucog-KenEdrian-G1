from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from .decorators import role_required
from .forms import RegistrationForm, ProfileForm, CompanyForm, CompanyJoinForm
from .models import User, Company, CompanyMembershipRequest
from assets.models import Device, Checkout, MaintenanceLog, SystemSettings


def get_admin_company(user):
    return user.company or user.administered_companies.first()


def csrf_failure_view(request, reason=""):
    fresh_token = get_token(request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", ""):
        return JsonResponse({
            "success": False,
            "csrf_failed": True,
            "csrf_token": fresh_token,
            "message": "Security token updated. Please retry your action.",
        }, status=403)
    messages.warning(request, "Your security session was updated. Please try your action again.")
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect("accounts:dashboard_redirect")


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AssetTrackLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].widget.attrs["class"] = "form-control"
        form.fields["password"].widget.attrs["class"] = "form-control"
        return form

    def form_invalid(self, form):
        messages.error(self.request, "Invalid username or password.")
        return super().form_invalid(form)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard_redirect")
    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data["email"]
            user.role = form.cleaned_data["role"]
            user.save()
            messages.success(request, "Account created successfully. You can now log in.")
            return redirect("accounts:login")
        messages.error(request, "Please fix the errors below.")
    else:
        form = RegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:login")


@login_required
def dashboard_redirect(request):
    if request.user.role == User.ROLE_ADMIN:
        return redirect("accounts:admin_dashboard")
    return redirect("accounts:employee_dashboard")


@role_required(User.ROLE_ADMIN)
def admin_dashboard(request):
    settings_obj = SystemSettings.get_solo()
    company = get_admin_company(request.user)
    context = {
        "company": company,
        "total_devices": Device.objects.filter(company=company).count() if company else 0,
        "available_devices": Device.objects.filter(company=company, status=Device.STATUS_AVAILABLE).count() if company else 0,
        "borrowed_devices": Device.objects.filter(company=company, status=Device.STATUS_BORROWED).count() if company else 0,
        "under_repair": Device.objects.filter(company=company, status=Device.STATUS_REPAIR).count() if company else 0,
        "pending_requests": Checkout.objects.filter(company=company, status=Checkout.STATUS_PENDING).count() if company else 0,
        "overdue_checkouts": [c for c in Checkout.objects.filter(company=company, status=Checkout.STATUS_ACTIVE) if c.is_overdue] if company else [],
        "damaged_count": MaintenanceLog.objects.filter(device__company=company, is_resolved=False).count() if company else 0,
        "settings": settings_obj,
    }
    return render(request, "accounts/admin_dashboard.html", context)


@role_required(User.ROLE_EMPLOYEE)
def employee_dashboard(request):
    if request.user.company_id:
        my_checkouts = Checkout.objects.filter(employee=request.user, company=request.user.company)
    else:
        my_checkouts = Checkout.objects.none()
    my_checkouts = my_checkouts.select_related("device", "requested_category").order_by("-requested_at")
    available_devices = Device.objects.filter(company=request.user.company, status=Device.STATUS_AVAILABLE) if request.user.company else Device.objects.none()
    context = {
        "company": request.user.company,
        "my_active": my_checkouts.filter(status=Checkout.STATUS_ACTIVE),
        "my_pending": my_checkouts.filter(status=Checkout.STATUS_PENDING),
        "my_history": my_checkouts.exclude(status__in=[Checkout.STATUS_ACTIVE, Checkout.STATUS_PENDING])[:10],
        "available_devices": available_devices,
        "settings": SystemSettings.get_solo(),
    }
    return render(request, "accounts/employee_dashboard.html", context)


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html", {"profile_user": request.user})


@login_required
def profile_edit_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
        messages.error(request, "Please fix the errors below.")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile_edit.html", {"form": form})


@ensure_csrf_cookie
@role_required(User.ROLE_ADMIN)
def company_manage_view(request):
    company = get_admin_company(request.user)
    if request.method == "POST":
        form = CompanyForm(request.POST, instance=company)
        if form.is_valid():
            company = form.save(commit=False)
            if not company.admin_id:
                company.admin = request.user
            company.save()
            if not request.user.company_id:
                request.user.company = company
                request.user.save(update_fields=["company"])
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": "Company details saved successfully."})
            messages.success(request, "Company details saved successfully.")
            return redirect("accounts:company_manage")
        else:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                errors = [str(e) for err_list in form.errors.values() for e in err_list]
                return JsonResponse({"success": False, "message": " ".join(errors)}, status=400)
            messages.error(request, "Please fix the errors below.")
    else:
        form = CompanyForm(instance=company)

    join_requests = []
    leave_requests = []
    members = []
    if company:
        join_requests = CompanyMembershipRequest.objects.filter(
            company=company,
            request_type=CompanyMembershipRequest.TYPE_JOIN,
            status=CompanyMembershipRequest.STATUS_PENDING,
        ).select_related("user")
        leave_requests = CompanyMembershipRequest.objects.filter(
            company=company,
            request_type=CompanyMembershipRequest.TYPE_LEAVE,
            status=CompanyMembershipRequest.STATUS_PENDING,
        ).select_related("user")
        members = company.members.exclude(pk=request.user.pk).order_by("first_name", "last_name", "username")

    context = {
        "company": company,
        "form": form,
        "join_requests": join_requests,
        "leave_requests": leave_requests,
        "members": members,
    }
    return render(request, "accounts/company_manage.html", context)


@role_required(User.ROLE_ADMIN)
def company_regenerate_code(request):
    if request.method == "POST":
        company = get_admin_company(request.user)
        if not company:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": "Please save company details first."}, status=400)
            messages.error(request, "Please save company details first.")
            return redirect("accounts:company_manage")
        new_code = company.regenerate_code()
        msg = f"New company code generated: {new_code}"
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "code": new_code, "message": msg})
        messages.success(request, msg)
    return redirect("accounts:company_manage")


@role_required(User.ROLE_ADMIN)
def company_request_review(request, pk, action):
    if request.method == "POST":
        company = get_admin_company(request.user)
        if not company:
            messages.error(request, "Please save company details first.")
            return redirect("accounts:company_manage")
        membership_req = get_object_or_404(
            CompanyMembershipRequest, pk=pk, company=company,
            status=CompanyMembershipRequest.STATUS_PENDING,
        )
        emp = membership_req.user
        user_name = emp.get_full_name() or emp.username
        req_type = membership_req.request_type
        member_data = {
            "id": emp.pk,
            "full_name": emp.get_full_name() or emp.username,
            "username": emp.username,
            "email": emp.email or "",
            "role_display": emp.get_role_display(),
        }
        if (
            action == "accept"
            and req_type == CompanyMembershipRequest.TYPE_JOIN
            and emp.company_id
            and emp.company_id != company.id
        ):
            membership_req.status = CompanyMembershipRequest.STATUS_REJECTED
            membership_req.save(update_fields=["status", "updated_at"])
            msg = f"{user_name} already belongs to another company, so this request was rejected."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:company_manage")
        if action == "accept":
            membership_req.status = CompanyMembershipRequest.STATUS_APPROVED
            if req_type == CompanyMembershipRequest.TYPE_JOIN:
                emp.company = company
                emp.save(update_fields=["company"])
                msg = f"Accepted {user_name} into {company.name}."
            else:
                emp.company = None
                emp.save(update_fields=["company"])
                msg = f"Approved leave request for {user_name}."
            membership_req.save(update_fields=["status", "updated_at"])
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": msg,
                    "action": action,
                    "pk": pk,
                    "request_type": req_type,
                    "member": member_data,
                })
            messages.success(request, msg)
        elif action == "reject":
            membership_req.status = CompanyMembershipRequest.STATUS_REJECTED
            membership_req.save(update_fields=["status", "updated_at"])
            msg = f"Rejected {req_type} request for {user_name}."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "success": True,
                    "message": msg,
                    "action": action,
                    "pk": pk,
                    "request_type": req_type,
                    "member": member_data,
                })
            messages.success(request, msg)
    return redirect("accounts:company_manage")


@role_required(User.ROLE_ADMIN)
def company_add_member(request):
    if request.method == "POST":
        company = get_admin_company(request.user)
        if not company:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": "Please save company details first."}, status=400)
            messages.error(request, "Please save company details first.")
            return redirect("accounts:company_manage")
        identifier = request.POST.get("identifier", "").strip()
        if not identifier:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": "Please provide a username or email."}, status=400)
            messages.error(request, "Please provide a username or email.")
            return redirect("accounts:company_manage")
        target_user = User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier)).first()
        if not target_user:
            msg = f"User '{identifier}' not found."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=404)
            messages.error(request, msg)
            return redirect("accounts:company_manage")
        if target_user.role != User.ROLE_EMPLOYEE:
            msg = "Only employee accounts can be added to your company."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:company_manage")
        if target_user.company_id and target_user.company_id != company.id:
            msg = f"{target_user.username} already belongs to another company."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:company_manage")
        if target_user.company_id == company.id:
            msg = f"{target_user.username} is already a member of {company.name}."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.warning(request, msg)
            return redirect("accounts:company_manage")
        target_user.company = company
        target_user.save(update_fields=["company"])
        CompanyMembershipRequest.objects.filter(
            company=company,
            user=target_user,
            request_type=CompanyMembershipRequest.TYPE_JOIN,
            status=CompanyMembershipRequest.STATUS_PENDING,
        ).update(status=CompanyMembershipRequest.STATUS_APPROVED)
        member_data = {
            "id": target_user.pk,
            "full_name": target_user.get_full_name() or target_user.username,
            "username": target_user.username,
            "email": target_user.email or "",
            "role_display": target_user.get_role_display(),
        }
        msg = f"Added {target_user.get_full_name() or target_user.username} to {company.name}."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": msg, "member": member_data})
        messages.success(request, msg)
    return redirect("accounts:company_manage")


@role_required(User.ROLE_ADMIN)
def company_remove_member(request, pk):
    if request.method == "POST":
        company = get_admin_company(request.user)
        if not company:
            messages.error(request, "Please save company details first.")
            return redirect("accounts:company_manage")
        target_user = get_object_or_404(User, pk=pk, company=company)
        if target_user.pk == request.user.pk:
            msg = "Administrators cannot remove themselves from their company."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("accounts:company_manage")
        target_user.company = None
        target_user.save(update_fields=["company"])
        user_name = target_user.get_full_name() or target_user.username
        msg = f"Removed {user_name} from {company.name}."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True, "message": msg, "member_id": pk})
        messages.success(request, msg)
    return redirect("accounts:company_manage")


@ensure_csrf_cookie
@login_required
def employee_join_company(request):
    if request.user.role == User.ROLE_ADMIN:
        return redirect("accounts:company_manage")

    pending_join = CompanyMembershipRequest.objects.filter(
        user=request.user,
        request_type=CompanyMembershipRequest.TYPE_JOIN,
        status=CompanyMembershipRequest.STATUS_PENDING,
    ).select_related("company").first()

    pending_leave = CompanyMembershipRequest.objects.filter(
        user=request.user,
        request_type=CompanyMembershipRequest.TYPE_LEAVE,
        status=CompanyMembershipRequest.STATUS_PENDING,
    ).select_related("company").first()

    if request.method == "POST" and request.user.company_id:
        err_msg = "You already belong to a company. Request to leave it before joining another."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "message": err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect("accounts:employee_join_company")

    if request.method == "POST":
        form = CompanyJoinForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["company_code"].strip().upper()
            target_company = Company.objects.filter(code__iexact=code).first()
            if not target_company:
                err_msg = "Invalid company code. Please confirm the code with your company administrator."
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"success": False, "message": err_msg}, status=400)
                messages.error(request, err_msg)
            elif pending_join:
                warn_msg = (
                    f"You already have a pending join request for {pending_join.company.name}. "
                    "Wait for it to be decided before requesting another company."
                )
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"success": False, "message": warn_msg}, status=400)
                messages.warning(request, warn_msg)
            else:
                CompanyMembershipRequest.objects.create(
                    company=target_company,
                    user=request.user,
                    request_type=CompanyMembershipRequest.TYPE_JOIN,
                    status=CompanyMembershipRequest.STATUS_PENDING,
                )
                succ_msg = f"Request to join '{target_company.name}' submitted. Awaiting administrator approval."
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({"success": True, "message": succ_msg})
                messages.success(request, succ_msg)
                return redirect("accounts:employee_join_company")
        else:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": "Please enter a valid company code."}, status=400)
    else:
        form = CompanyJoinForm()

    context = {
        "company": request.user.company,
        "form": form,
        "pending_join": pending_join,
        "pending_leave": pending_leave,
    }
    return render(request, "accounts/employee_company.html", context)


@login_required
def employee_leave_company(request):
    if request.method == "POST":
        if not request.user.company:
            return redirect("accounts:employee_join_company")
        existing_leave = CompanyMembershipRequest.objects.filter(
            company=request.user.company,
            user=request.user,
            request_type=CompanyMembershipRequest.TYPE_LEAVE,
            status=CompanyMembershipRequest.STATUS_PENDING,
        ).first()
        if not existing_leave:
            CompanyMembershipRequest.objects.create(
                company=request.user.company,
                user=request.user,
                request_type=CompanyMembershipRequest.TYPE_LEAVE,
                status=CompanyMembershipRequest.STATUS_PENDING,
            )
            msg = "Leave request submitted. Awaiting administrator approval."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": True, "message": msg})
            messages.success(request, msg)
        else:
            msg = "You already have a pending leave request."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.info(request, msg)
    return redirect("accounts:employee_join_company")