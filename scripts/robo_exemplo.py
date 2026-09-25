import logging
import time

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger("robo_exemplo")


def main():
    log.info("Iniciando robô de exemplo")
    for etapa in range(1, 4):
        log.info("Processando etapa %s de 3", etapa)
        time.sleep(2)
    log.info("Robô finalizado com sucesso")


if __name__ == "__main__":
    main()