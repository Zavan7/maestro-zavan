"""Consumer do WebSocket que leva o log ao vivo até o navegador.

English:
    WebSocket consumer that carries the live log to the browser.
"""

from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from executions.ao_vivo import LinhaDoLog, nome_do_grupo, numerar_log
from executions.models import Execucao

FECHAMENTO_SEM_LOGIN = 4401
FECHAMENTO_NAO_ENCONTRADA = 4404


class ExecucaoConsumer(AsyncJsonWebsocketConsumer):
    """Acompanha uma execução: repassa as linhas e o aviso de fim.

    Cada aba aberta na tela de detalhe vira uma conexão, que entra no
    grupo ``execucao_<id>``. Quem publica (o worker, e depois o agente)
    manda eventos para o grupo, e o Channels entrega a cada conexão
    chamando o método com o nome do ``type`` do evento: ``log.linhas``
    chama ``log_linhas``.

    A conexão só é aceita para usuário logado (a sessão vem do
    ``AuthMiddlewareStack``) e para execução que existe, com os mesmos
    códigos de erro em toda recusa (4401 e 4404). O navegador não manda
    nada: o que chegar dele é ignorado.

    English:
        Watches an execution: relays the lines and the end notice.

        Each tab open on the detail page becomes a connection, which
        joins the ``execucao_<id>`` group. Publishers (the worker, and
        later the agent) send events to the group, and Channels delivers
        them to each connection by calling the method named after the
        event's ``type``: ``log.linhas`` calls ``log_linhas``.

        The connection is only accepted for a logged-in user (the session
        comes from ``AuthMiddlewareStack``) and for an existing execution,
        with the same error codes on every refusal (4401 and 4404). The
        browser sends nothing: anything it sends is ignored.
    """

    grupo: str | None = None

    async def connect(self) -> None:
        """Valida o acesso, entra no grupo e manda o que já existe.

        A ordem importa: primeiro entra no grupo, depois lê o log do
        banco. Quem roda o robô grava cada lote no banco antes de
        publicá-lo, então toda linha ou já está nessa leitura ou ainda vai
        chegar pelo grupo. O navegador ignora os números que já tem.

        Se a execução já estava finalizada, manda o ``fim`` na hora: assim
        a página que ficou para trás recarrega.

        English:
            Checks access, joins the group and sends what already exists.

            Order matters: first join the group, then read the log from
            the database. Whoever runs the robot saves each batch to the
            database before publishing it, so every line is either in that
            read or still to arrive through the group. The browser skips
            numbers it already has.

            If the execution was already finished, it sends ``fim`` right
            away: that way a page left behind reloads.
        """
        usuario = self.scope.get("user")
        if usuario is None or not usuario.is_authenticated:
            await self.close(code=FECHAMENTO_SEM_LOGIN)
            return

        execucao_id = int(self.scope["url_route"]["kwargs"]["pk"])
        if not await self._execucao_existe(execucao_id):
            await self.close(code=FECHAMENTO_NAO_ENCONTRADA)
            return

        self.grupo = nome_do_grupo(execucao_id)
        await self.channel_layer.group_add(self.grupo, self.channel_name)
        await self.accept()

        status, linhas = await self._situacao(execucao_id)
        if linhas:
            await self.send_json({"tipo": "linhas", "linhas": linhas})
        if status not in (Execucao.Status.PENDENTE, Execucao.Status.RODANDO):
            await self.send_json({"tipo": "fim", "status": status})

    async def disconnect(self, code: int) -> None:
        """Sai do grupo ao fechar a conexão.

        Args:
            code: código de fechamento do WebSocket.

        English:
            Leaves the group when the connection closes.

            Args:
                code: WebSocket close code.
        """
        if self.grupo is not None:
            await self.channel_layer.group_discard(
                self.grupo, self.channel_name
            )

    async def receive_json(self, content: object, **kwargs: Any) -> None:
        """Ignora mensagens do navegador: o canal só vai num sentido.

        Args:
            content: mensagem recebida, descartada.
            **kwargs: argumentos extras do Channels, não usados.

        English:
            Ignores browser messages: the channel only goes one way.

            Args:
                content: received message, discarded.
                **kwargs: extra Channels arguments, unused.
        """

    async def log_linhas(self, evento: dict[str, Any]) -> None:
        """Repassa um lote de linhas ao navegador.

        Args:
            evento: evento do grupo, com a lista ``linhas``.

        English:
            Relays a batch of lines to the browser.

            Args:
                evento: group event, with the ``linhas`` list.
        """
        await self.send_json({"tipo": "linhas", "linhas": evento["linhas"]})

    async def log_fim(self, evento: dict[str, Any]) -> None:
        """Repassa o aviso de fim ao navegador.

        Args:
            evento: evento do grupo, com o ``status`` final.

        English:
            Relays the end notice to the browser.

            Args:
                evento: group event, with the final ``status``.
        """
        await self.send_json({"tipo": "fim", "status": evento["status"]})

    @database_sync_to_async
    def _execucao_existe(self, execucao_id: int) -> bool:
        """Indica se a execução existe.

        O ORM do Django é síncrono; ``database_sync_to_async`` roda a
        consulta numa thread, sem travar o laço assíncrono.

        Args:
            execucao_id: id da execução.

        Returns:
            ``True`` se a execução existe.

        English:
            Tells whether the execution exists.

            Django's ORM is sync; ``database_sync_to_async`` runs the
            query in a thread, without blocking the async loop.

            Args:
                execucao_id: execution id.

            Returns:
                ``True`` if the execution exists.
        """
        return Execucao.objects.filter(pk=execucao_id).exists()

    @database_sync_to_async
    def _situacao(self, execucao_id: int) -> tuple[str, list[LinhaDoLog]]:
        """Lê o status e o log numerado da execução.

        Args:
            execucao_id: id da execução.

        Returns:
            O status atual e as linhas guardadas, numeradas.

        English:
            Reads the execution's status and numbered log.

            Args:
                execucao_id: execution id.

            Returns:
                The current status and the stored lines, numbered.
        """
        status, log, total = Execucao.objects.values_list(
            "status", "log", "total_linhas"
        ).get(pk=execucao_id)
        return status, numerar_log(log, total)
