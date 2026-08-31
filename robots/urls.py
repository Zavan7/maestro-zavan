from django.urls import path
from robots import views

urlpatterns = [
    path('', views.robot_list, name='robot_list'),
]