from django.urls import path
from executions import views

urlpatterns = [
    path('', views.execution_list, name='execution_list'),
    path('<int:pk>/', views.execution_detail, name='execution_detail'),
]