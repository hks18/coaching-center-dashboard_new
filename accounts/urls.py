from django.urls import path
from django.conf import settings

from .views import (
    signup_view,
    login_view,
    center_login_view,
    home_view,
    center_dashboard_view,
    admin_dashboard_view,
    admin_center_dashboard_view,
)

urlpatterns = [
    path("", signup_view, name="signup"),
    path("login/", login_view, name="login"),
    path("center-login/", center_login_view, name="center_login"),
    path("home/", home_view, name="home"),
    path("center-dashboard/", center_dashboard_view, name="center_dashboard"),
]

# Local-only admin dashboard routes (only when DEBUG = True)
if settings.DEBUG:
    urlpatterns += [
        path("admin-dashboard/", admin_dashboard_view, name="admin_dashboard"),
        path(
            "admin-dashboard/<str:center_code>/",
            admin_center_dashboard_view,
            name="admin_center_dashboard",
        ),
    ]
