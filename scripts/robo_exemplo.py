"""Robô de exemplo usado para testar o Maestro de ponta a ponta.

Simula três etapas de trabalho, com uma pausa de 2 segundos em cada,
e registra o progresso com ``logging``. Tudo o que ele imprime é
capturado pelo worker e aparece no log da execução.

English:
    Sample robot used to test Maestro end to end.

    It simulates three work steps, with a 2-second pause in each, and
    records progress with ``logging``. Everything it prints is captured
    by the worker and shows up in the execution log.
"""
import logging
import time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger("robo_exemplo")


def main():
    """Executa as etapas do robô de exemplo.

    Termina normalmente (código de saída 0), então o Maestro marca a
    execução como sucesso.

    English:
        Runs the sample robot's steps.

        It ends normally (exit code 0), so Maestro marks the execution as
        successful.
    """
    log.info("Iniciando robô de exemplo")
    for etapa in range(1, 4):
        log.info("Processando etapa %s de 3", etapa)
        time.sleep(2)
    log.info("Robô finalizado com sucesso")


if __name__ == "__main__":
    main()
