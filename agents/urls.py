"""Rotas do app de agentes, dentro da aba de configurações.

English:
    Routes for the agents app, inside the settings tab.
"""

from django.urls import path

from agents import views

urlpatterns = [
    path("", views.agent_list, name="agent_list"),
    path("novo/", views.agent_create, name="agent_create"),
    path("<int:pk>/token/", views.agent_new_token, name="agent_new_token"),
    path("<int:pk>/alternar/", views.agent_toggle, name="agent_toggle"),
]
