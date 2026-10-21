"""Rotas do app de configurações.

English:
    Routes for the settings app.
"""

from django.urls import path

from config import views

urlpatterns = [
    path("", views.config_home, name="config_home"),
    path("retencao/", views.config_retention, name="config_retention"),
    path("limites/", views.config_limits, name="config_limits"),
    path("usuarios/", views.config_users, name="config_users"),
    path(
        "usuarios/novo/", views.config_user_create, name="config_user_create"
    ),
    path(
        "usuarios/<int:pk>/grupo/",
        views.config_user_group,
        name="config_user_group",
    ),
    path(
        "usuarios/<int:pk>/alternar/",
        views.config_user_toggle,
        name="config_user_toggle",
    ),
]
