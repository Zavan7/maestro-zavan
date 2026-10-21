"""Tipos compartilhados pelas views do Maestro.

English:
    Types shared by Maestro's views.
"""

from django.contrib.auth.models import User
from django.http import HttpRequest


class RequisicaoAutenticada(HttpRequest):
    """Requisição de uma view protegida por login.

    No ``HttpRequest``, ``request.user`` é ``User | AnonymousUser``. Atrás
    de ``@login_required`` (ou de ``@permission_required``) o usuário nunca
    é anônimo; este tipo diz isso ao verificador. Use só em views que de
    fato exigem login.

    English:
        Request of a login-protected view.

        In ``HttpRequest``, ``request.user`` is ``User | AnonymousUser``.
        Behind ``@login_required`` (or ``@permission_required``) the user is
        never anonymous; this type tells the checker so. Only use it in
        views that really require login.
    """

    user: User
