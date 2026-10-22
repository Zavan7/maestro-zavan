# Changelog

Todas as mudanças relevantes do Maestro ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e a numeração segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Segurança

Correções da varredura de segurança. As marcadas com **(quebra)** mudam o comportamento de quem já usa o Maestro.

- **(quebra)** Os robôs só recebem variáveis de ambiente de uma lista de permitidas (PATH, HOME, idioma, fuso, proxy, certificados, as das ferramentas de dependências) e as que começam com `ROBO_`; antes recebiam tudo menos o token, e um robô do worker lia o `SECRET_KEY`. Credenciais de robôs passam a usar o prefixo `ROBO_`. Vale para o worker, o agente em Go e o de referência
- O worker e os agentes (Go e referência) se marcam como não depuráveis (`PR_SET_DUMPABLE`), para um robô do mesmo usuário não ler o `MAESTRO_TOKEN` em `/proc/<pid>/environ`
- `ROBOS_USUARIO` (worker) e `AGENTE_USUARIO_ROBOS` (agente): rodam os robôs com outro usuário do sistema, sem grupos extras
- **(quebra)** Ver execuções e logs exige a permissão `executions.view_execucao`, nas telas e no WebSocket (fecha com 4403); a migração dá a permissão aos três grupos. Antes qualquer usuário logado, mesmo sem grupo, lia os logs
- Quem gerencia usuários só concede grupos cujas permissões já tem: o Administrador do sistema não cria mais contas Administrador RPA para si. A regra vale na tela, no formulário de criação e no serviço
- Um `grupo` que não é número na troca de grupo vira mensagem, e não erro 500
- Login bloqueado por 15 minutos depois de 5 senhas erradas para o mesmo usuário e IP (django-axes), com tela própria
- O WebSocket do agente confere a cada mensagem se o agente continua ativo e com o mesmo token; revogado, a conexão cai (4401) mesmo que o aviso pelo Redis se perca
- HTTPS em produção: cookies `Secure`, redirecionamento para https e HSTS, controlados por `USAR_HTTPS`, `HSTS_SEGUNDOS`, `ATRAS_DE_PROXY_HTTPS` e `CSRF_TRUSTED_ORIGINS`
- **(quebra)** O agente em Go recusa `ws://` para um host que não seja local (o token iria sem criptografia); `AGENTE_PERMITIR_WS_SEM_TLS=1` libera, como no Docker
- O agente em Go limita a 64 KB cada mensagem recebida do Maestro
- **(quebra)** O nome do ambiente de cada robô ganha um sufixo do hash do caminho (`coleta-d6c252e7`), para `coleta/notas` e `coleta__notas` não dividirem o mesmo venv; os ambientes são recriados na primeira execução
- Docker: a porta 8000 do `web` só abre em `127.0.0.1`

### Documentação

- Tutorial no README, do zero ao primeiro robô: subir com Docker, escrever e cadastrar o robô, rodar com log ao vivo, agendar, dar acesso à equipe, instalar o agente em outra máquina e resolver os problemas mais comuns
- README atualizado com o agente em Go, o Docker e o django-axes na stack e na estrutura do projeto

### Adicionado

- Executor próprio (`robots/executor.py`), sem Django nem Celery: acompanha o processo, lê a saída linha a linha e confere tempo e pedido de parada a cada segundo
- Tempo máximo e novas tentativas (0 a 5) por robô, e duração esperada opcional
- Cada nova tentativa é uma execução própria, com o número da tentativa na lista e no detalhe
- Status `cancelada` para execuções paradas pelo usuário
- Limites padrão de execução (tempo máximo e tamanho do log) editáveis na aba de configurações
- Estado "parando" na lista de robôs enquanto a parada pedida não termina
- Log ao vivo na tela de detalhe: as linhas chegam por WebSocket (Django Channels, servido pelo Daphne) conforme o robô as escreve, com a numeração contínua mesmo quando o começo do log foi cortado
- O log de uma execução em andamento é gravado no banco a cada 0,5 s, então quem abre a página no meio já vê o que saiu
- Agentes: cadastro na aba de configurações (permissão `gerenciar_agentes`), com token mostrado uma única vez e guardado como hash, troca de token, desativação e registro de cada alteração
- Robôs podem rodar num agente: o disparo manda `iniciar` ao agente, o "parar" manda `parar`, e o agente devolve o log ao vivo e como terminou, pelo WebSocket `ws/agente/`
- Protocolo do agente documentado em `docs/agente/protocolo.md` e agente de referência em Python (`tools/agente_referencia.py`) para testar sem o agente em Go
- Status do sistema mostra quantos agentes estão online
- Agente em Go executa os robôs: `iniciar` resolve o robô dentro da pasta aprovada (barrando `../`, caminho absoluto e link simbólico para fora), roda o robô no ambiente do gerenciador de dependências dele, manda o log em lotes de 0,5 s dentro dos limites do protocolo e o `fim` com motivo e código de saída
- Agente em Go para os robôs: `parar` e tempo esgotado mandam SIGTERM ao grupo de processos e SIGKILL 5 s depois; filhos que sobram são encerrados; ao desligar, o agente encerra os robôs em andamento
- Agente em Go guarda numa fila o que não conseguiu enviar e reenvia ao reconectar, na mesma ordem e sem repetir o que já saiu
- O robô não herda o `MAESTRO_TOKEN` nem o ambiente virtual de quem o roda (`VIRTUAL_ENV`, `UV_PROJECT_ENVIRONMENT` e a pasta `bin` do venv no `PATH`), no worker e no agente
- Docker: `docker compose up -d --build` sobe Redis, Maestro (Daphne), worker com agendador e agente em Go; o token do agente fica em `agente.env`, separado do `.env`, e `instalar-navegadores` baixa os navegadores do Playwright de cada robô
- `AGENTE_PASTA_VENVS` no agente: cada robô ganha um venv fora da própria pasta, para o container não usar nem sobrescrever o `.venv` do host
- Testes do agente em Go (`go test ./...`): configuração, resolução do robô, executor, execuções e conexão contra um Maestro falso
- Cada robô roda no ambiente do próprio gerenciador de dependências, detectado pela pasta dele: uv, poetry, pdm, pipenv ou `requirements.txt` com pip, com as dependências sincronizadas antes de cada execução e a saída do preparo no log, em linhas `[ambiente]`; vale para o worker e para o agente em Go, com a mesma regra
- Motivos de fim `ambiente_invalido` (a ferramenta do robô não está instalada; falha sem nova tentativa) e `preparo_falhou` (a instalação das dependências falhou ou passou de 15 minutos; falha com nova tentativa)
- `ROBOS_PASTA_VENVS` no worker, como o `AGENTE_PASTA_VENVS` do agente: o ambiente de cada robô fica fora da pasta dele
- Subcomando `agente ambiente <pasta do robô> -- <args>`, que prepara o ambiente do robô e roda o Python dele; o `instalar-navegadores` passa a usá-lo e funciona com qualquer gerenciador
- Imagens Docker do worker e do agente com poetry, pdm e pipenv (além do uv), em versões fixas; volume `worker-robos` para os ambientes dos robôs do worker

### Alterado

- Interface revisada: um sistema de botões só (primário, contorno, iniciar, parar, perigo e link), ações das tabelas alinhadas numa linha, campos `select` e `textarea` com o mesmo estilo dos `input`, foco visível em tudo, tabelas com rolagem horizontal em telas estreitas e sidebar que vira barra no topo no celular
- Cabeçalho com prompt `usuario@maestro:~/caminho$`, ícones no menu, botões "+ novo" no topo das listas e "voltar"/"cancelar" em todos os formulários; "cadastrar robô" sai do menu e vai para o topo da tela de robôs
- Movimento discreto (status "rodando", log "ao vivo" e agente online pulsando, mensagens e páginas surgindo), desligado com `prefers-reduced-motion`
- Lista de execuções com número e duração; detalhe com os dados num cartão, o agente do robô e o log numa janela de terminal
- O painel inicial mostra os agentes ativos de verdade (online ou há quanto tempo offline, e quantos robôs cada um tem)
- O botão "parar" encerra o processo de verdade: marca `parada_solicitada`, e o executor manda SIGTERM ao grupo de processos e SIGKILL 5 segundos depois, alcançando navegadores e outros filhos
- Processos filhos que sobram depois de um robô terminar são encerrados
- Os scripts rodam com `python -u`, para cada linha do log chegar assim que é escrita
- A tela de edição de robô usa os campos do formulário e passa a mostrar os erros de validação
- A limpeza do histórico também apaga execuções canceladas antigas
- A tela de detalhe deixa de recarregar a cada 5 segundos; isso só volta a acontecer se o WebSocket não conectar
- O `runserver` passa a ser o do Daphne, que atende HTTP e WebSocket
- O SQLite roda em modo WAL, com `timeout` de 20 s, para o worker gravar o log enquanto a tela lê
- As regras de status final e nova tentativa saem da tarefa do worker para `robots/conclusao.py`, usadas igualmente pelo worker e pelos agentes

### Corrigido

- Status "manutenção" e "pendente" ficavam quase invisíveis na tela de robôs, porque o `robots.css` repetia os badges com a cor de preenchimento
- As classes `page-subtitle` e `section-title` eram usadas sem estar definidas
- `ROBOS_SCRIPTS_DIR=` vazio no `.env` fazia o worker procurar os scripts na pasta de onde foi iniciado
- As mensagens de erro de formulário só tinham estilo na tela de login

## [1.1.0] - 2026-10-21

### Adicionado

- Agendamento recorrente de robôs por horário e dias da semana, com pausar e retomar
- Estados visuais nas listas de robôs e agendamentos: rodando, agendado, pausado e parado
- Origem das execuções (manual ou agendamento) e etiqueta "agendado" no histórico
- Duração da execução na tela de detalhe
- Aba de configurações, visível apenas para quem tem alguma permissão de configuração
- Gestão de usuários e acesso: troca de grupo, desativação e reativação, com registro de todas as alterações
- Grupo "Administrador do sistema"
- Prévia da seção de limites padrão de execução, ainda sem edição
- Status do sistema na aba de configurações: Redis, worker e agendador (pelo pulso gravado a cada minuto)
- Edição da retenção do histórico e limpeza diária automática das execuções finalizadas mais antigas que o prazo
- Criação de usuários pela aba de configurações, com grupo e registro na auditoria
- Testes do agendamento, do disparo de execuções e da aba de configurações, incluindo status do sistema, retenção e criação de usuários

### Alterado

- Iniciar e parar robôs passa a exigir a permissão `executar_robo`; antes bastava estar logado
- Os grupos de acesso passam a ser criados por uma migração de dados, sem comandos manuais
- Quem não está logado e abre uma página da aba de configurações vai para o login, em vez de receber 403
- Removido o `main.py` que sobrou da criação do projeto e não era usado

### Corrigido

- O botão "parar" ignorava execuções pendentes: uma execução presa na fila (worker parado) travava o robô até alguém mexer no banco. Agora ela é cancelada, com o motivo no log
- O worker rodava a execução mesmo que ela já não estivesse pendente; agora ele a reivindica com um `UPDATE` condicional e ignora as canceladas ou repetidas
- Os testes falhavam num clone novo sem `.env` (`SECRET_KEY` vazia); em desenvolvimento e nos testes passa a valer uma chave fixa, e fora disso a falta da chave impede o Maestro de subir, com o motivo
- O arquivo de exemplo de ambiente se chamava `.env.exemple` e não tinha `CELERY_BROKER_URL` nem `ROBOS_SCRIPTS_DIR`; agora é `.env.example`, completo
- A tela de cadastro de robô exibia o formulário de edição
- O CSS da tela de detalhe de execução não era carregado
- O cabeçalho das páginas ficava sem estilo nas telas que não carregavam o CSS de robôs

### Segurança

- Um usuário sem grupo não consegue mais iniciar ou parar robôs
- Ninguém altera o próprio acesso pela aba de configurações, e superusuários só podem ser alterados por outro superusuário

### Limitações conhecidas

- Para uma execução rodando, o botão "parar" marca a execução como finalizada, mas não encerra o processo
- Os robôs rodam com as dependências do ambiente do Maestro

## [1.0.0] - 2026-09-28

### Adicionado

- Página pública da ZV Labs na raiz, com acesso ao Maestro
- Login e logout com o sistema de autenticação do Django
- Painel com distribuição dos robôs por status, atividade dos últimos 14 dias e console de execuções recentes
- Cadastro, edição e exclusão de robôs com validação por `ModelForm`
- Execução real de robôs em segundo plano com Celery e Redis, restrita à pasta de scripts aprovados
- Histórico de execuções e tela de detalhe com log numerado e destaque de erros
- Grupos de acesso Operador e Administrador RPA, com permissões verificadas nas views
- Mensagens de confirmação e de erro em todas as ações
- Testes de models e views para robôs, execuções e logout

### Corrigido

- `DEBUG` lido do `.env` como texto, o que o mantinha sempre ligado
- Configuração de e-mail usando uma chave que o Django não reconhece
- `ROBOS_SCRIPTS_DIR` passa a ser lido do `.env`, como documentado

### Limitações conhecidas

- O botão "parar" marca a execução como finalizada, mas não encerra o processo
- Os robôs rodam com as dependências do ambiente do Maestro