from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import LoginForm


urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html", authentication_form=LoginForm), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("register/customer/", views.register_customer, name="register_customer"),
    path("register/engineer/", views.register_engineer, name="register_engineer"),
    path("dashboard/", views.dashboard_redirect, name="dashboard_redirect"),
    path("dashboard/customer/", views.customer_dashboard, name="customer_dashboard"),
    path("dashboard/customer/profile/", views.customer_profile, name="customer_profile"),
    path("dashboard/engineer/", views.engineer_dashboard, name="engineer_dashboard"),
    path("dashboard/engineer/availability/", views.update_availability, name="update_availability"),
    path("dashboard/admin/", views.operations_dashboard, name="operations_dashboard"),
    path("dashboard/admin/engineers/<int:pk>/review/", views.engineer_verification_review, name="engineer_verification_review"),
    path("dashboard/admin/engineers/<int:pk>/id/", views.download_engineer_id, name="download_engineer_id"),
    path("requests/new/", views.request_help, name="request_help"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/attachment/", views.request_attachment, name="request_attachment"),
    path("requests/<int:pk>/assign/", views.assign_request, name="assign_request"),
    path("requests/<int:pk>/status/", views.update_job_status, name="update_job_status"),
    path("workshop-records/", views.workshop_records, name="workshop_records"),
    path("workshop-records/new/", views.add_workshop_record, name="add_workshop_record"),
    path("mercedes-ecu-records/", views.ecu_records, name="ecu_records"),
    path("mercedes-ecu-records/new/", views.add_ecu_record, name="add_ecu_record"),
    path("mercedes-ecu-records/<int:pk>/download/", views.download_ecu_file, name="download_ecu_file"),
    path("diagnostic-files/", views.diagnostic_file_library, name="diagnostic_file_library"),
    path("diagnostic-files/new/", views.add_diagnostic_file, name="add_diagnostic_file"),
    path("diagnostic-files/<int:pk>/", views.diagnostic_file_detail, name="diagnostic_file_detail"),
    path("diagnostic-files/<int:pk>/download/", views.download_diagnostic_file, name="download_diagnostic_file"),
    path("parts-lookup/", views.parts_lookup, name="parts_lookup"),
    path("parts-catalogue/", views.parts_catalogue, name="parts_catalogue"),
    path("parts-catalogue/new/", views.add_required_part, name="add_required_part"),
    path("vin-decoder/", views.vin_decoder, name="vin_decoder"),
]
