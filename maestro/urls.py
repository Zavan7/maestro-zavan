"""Rotas raiz do Maestro.

Este é o "índice" de URLs do projeto: a página pública da ZV Labs na
raiz (``/``), o painel, o login e o logout ficam aqui; as rotas de cada
app (robôs, execuções, agendamentos e configurações) são incluídas com
``include``, deixando cada app dono das próprias URLs.

English:
    Maestro's root routes.

    This is the project's URL "table of contents": the public ZV Labs
    page at the root (``/``), the dashboard, login and logout live
    here; each app's routes (robots, executions, schedules and
    settings) are pulled in with ``include``, so each app owns its own
    URLs.
"""

from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from django.views.generic import TemplateView

from accounts import views as accounts_views

urlpatterns = [
    path(
        "",
        TemplateView.as_view(template_name="portfolio/index.html"),
        name="portfolio",
    ),
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
    path("agendamentos/", include("scheduler.urls")),
    path("configuracoes/agentes/", include("agents.urls")),
    path("configuracoes/", include("config.urls")),
]
