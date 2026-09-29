from django.urls import path

from scheduler import views

urlpatterns = [
    path("", views.schedule_list, name="schedule_list"),
    path("novo/", views.schedule_create, name="schedule_create"),
    path("<int:pk>/editar/", views.schedule_edit, name="schedule_edit"),
    path("<int:pk>/alternar/", views.schedule_toggle, name="schedule_toggle"),
    path("<int:pk>/excluir/", views.schedule_delete, name="schedule_delete"),
]