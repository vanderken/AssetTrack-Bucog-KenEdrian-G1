from django.urls import path
from . import views

app_name = "assets"

urlpatterns = [
    path("devices/", views.device_list, name="device_list"),
    path("devices/add/", views.device_create, name="device_create"),
    path("devices/<int:pk>/edit/", views.device_edit, name="device_edit"),
    path("devices/<int:pk>/delete/", views.device_delete, name="device_delete"),
    path("departments/", views.department_list, name="department_list"),
    path("departments/add/", views.department_create, name="department_create"),
    path("departments/<int:pk>/edit/", views.department_edit, name="department_edit"),
    path("departments/<int:pk>/delete/", views.department_delete, name="department_delete"),
    path("categories/", views.category_list, name="category_list"),
    path("categories/add/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("checkouts/requests/", views.checkout_requests, name="checkout_requests"),
    path("checkouts/requests/<int:pk>/approve/", views.checkout_approve, name="checkout_approve"),
    path("checkouts/requests/<int:pk>/reject/", views.checkout_reject, name="checkout_reject"),
    path("checkouts/assign/", views.checkout_assign, name="checkout_assign"),
    path("checkouts/active/", views.active_checkouts, name="active_checkouts"),
    path("checkouts/<int:pk>/return/", views.checkout_return, name="checkout_return"),
    path("checkouts/request/new/", views.my_checkout_request, name="my_checkout_request"),
    path("maintenance/", views.maintenance_list, name="maintenance_list"),
    path("maintenance/<int:pk>/resolve/", views.maintenance_resolve, name="maintenance_resolve"),
    path("reports/", views.reports_view, name="reports"),
    path("settings/", views.system_settings_view, name="system_settings"),
]
