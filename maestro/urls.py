from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import TemplateView

from accounts import views as accounts_views

urlpatterns = [
    path("", TemplateView.as_view(template_name="portfolio/index.html"), name="portfolio"),
    path("painel/", accounts_views.home, name="home"),
    path("admin/", admin.site.urls),
    path("robots/", include("robots.urls")),
    path("execucoes/", include("executions.urls")),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="accounts/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]