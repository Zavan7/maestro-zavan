from django.urls import path
from robots import views

urlpatterns = [
    path('', views.robot_list, name='robot_list'),
    path('novo/', views.robot_create, name='robot_create'),
]