from django.urls import path

from config import views

urlpatterns = [
    path("", views.config_home, name="config_home"),
    path("usuarios/", views.config_users, name="config_users"),
    path("usuarios/<int:pk>/grupo/", views.config_user_group, name="config_user_group"),
    path("usuarios/<int:pk>/alternar/", views.config_user_toggle, name="config_user_toggle"),
]
