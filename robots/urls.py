"""Rotas do app de robôs.

Cada rota tem um ``name``, usado nos templates com ``{% url %}`` e nas
views com ``redirect``. Assim, se a URL mudar, nada mais precisa mudar.

English:
    Routes for the robots app.

    Every route has a ``name``, used in templates with ``{% url %}``
    and in views with ``redirect``. That way, if the URL changes,
    nothing else has to change.
"""
from django.urls import path

from robots import views

urlpatterns = [
    path("", views.robot_list, name="robot_list"),
    path("novo/", views.robot_create, name="robot_create"),
    path("<int:pk>/editar/", views.robot_edit, name="robot_edit"),
    path("<int:pk>/excluir/", views.robot_exclusion, name="robot_exclusion"),
    path("<int:pk>/iniciar/", views.robot_start, name="robot_start"),
    path("<int:pk>/parar/", views.robot_stop, name="robot_stop"),
]
