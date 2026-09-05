# Maestro

> Orquestrador de automações RPA construído em Django, do zero ao nível sênior — com segurança tratada como requisito desde a primeira linha de código, não como algo adicionado depois.

**Status atual:** 🟡 Em desenvolvimento — Nível 1 (Iniciante), fechando o front/back de robôs e execuções

---

## Sobre este projeto

Este é um **projeto de estudos**, construído como parte de uma trilha pessoal de aprendizado (lógica de programação → Python intermediário/avançado → RPA → async → mensageria → Django/FastAPI → MongoDB). O Maestro é o projeto integrador dessa trilha.

Apesar de ser um ambiente de estudos, ele é documentado e versionado com o mesmo rigor de um projeto profissional. Nada de "depois eu documento": cada decisão relevante, cada correção de bug e cada etapa concluída fica registrada aqui.

## O que é o Maestro

Um sistema web para cadastrar, executar, agendar e monitorar automações RPA (robôs). Pense nele como um painel de controle central: em vez de cada script RPA rodar solto na sua máquina, o Maestro dá visibilidade, controle de acesso, agendamento e histórico de execução pra esses robôs.

## Diagramas de arquitetura

![Organograma dos apps do Maestro](diagrams/maestro-organograma-apps.svg)

Os apps se organizam em três camadas: **Domínio** (`robots`, `executions`, `scheduler`), **Suporte** (`accounts`, `audit`, `notifications`) e **Interface** (`api`, `dashboard`). A interface consome o domínio, e o domínio se apoia no suporte para segurança e rastreabilidade. Os apps sem borda tracejada já têm código real; os demais são placeholders de fases futuras.

![Fluxo de execução no Maestro](diagrams/maestro-fluxo-execucao.svg)

Hoje, iniciar/parar uma execução só simula o estado no banco (botões manuais em `robots/views.py`). O plano é substituir essa simulação por um **agente escrito em Go**, rodando na máquina onde o robô realmente executa: ele recebe o comando via WebSocket do Django, dispara o script RPA em Python, e reporta status/log de volta. Ver seção "Ideias em avaliação" abaixo.

---

## Stack técnica

| Camada                    | Tecnologia                       | Status                                        |
| ------------------------- | -------------------------------- | --------------------------------------------- |
| Backend                   | Django 6.1                       | ✅ Em uso                                     |
| Gerenciador de pacotes    | `uv`                             | ✅ Em uso                                     |
| Banco de dados            | SQLite (dev)                     | ✅ Em uso — PostgreSQL planejado pra produção |
| Frontend                  | Django Templates + HTML/CSS puro | ✅ Em uso                                     |
| Execução assíncrona       | Celery + Redis                   | ⏳ Planejado (Nível 2)                        |
| API                       | Django REST Framework            | ⏳ Planejado (Nível 2)                        |
| Isolamento de execução    | Docker (containers efêmeros)     | ⏳ Planejado (Nível 3)                        |
| Agente de execução remota | Go + WebSocket                   | 💡 Ideia em avaliação (ver abaixo)            |

**Decisão registrada:** o frontend usa Django Templates puro (HTML/CSS, sem framework JS) por opção deliberada nesta fase de aprendizado. Uma migração futura para React + API (DRF) está cogitada para o Nível 2.

## Ideias em avaliação

### Agente em Go para execução remota

Hoje, os botões "iniciar"/"parar" na tela de robôs só alteram o estado da `Execucao` no banco — não existe execução real de script ainda (marcado com `# TODO` no código). A ideia é que, quando o projeto chegar no Nível 2/3, esse disparo passe a ser real através de um **agente escrito em Go** rodando na máquina onde o robô é executado:

- O Django continua centralizado, sem saber os detalhes de cada máquina
- O agente Go mantém uma conexão WebSocket viva com o Django, escuta comandos (iniciar/parar) e reporta status/log de volta
- O script RPA em si **continua em Python** — o agente só orquestra o processo, não reimplementa a automação
- Go foi escolhido pra esse papel específico por compilar num binário único (sem exigir Python configurado na máquina do robô só pra rodar o "mensageiro") e por lidar bem com conexões concorrentes de forma leve (goroutines)

Essa é uma frente de estudo paralela (aprender Go) que será aberta quando o Nível 2 começar — não faz sentido misturar agora, no meio dos fundamentos de Django.

## Identidade visual

Estética de **terminal/console**, pensada para remeter ao público técnico (devs, analistas de RPA):

- Cards com titlebar de três bolinhas (estilo macOS/VSCode)
- Fonte monoespaçada: `IBM Plex Mono`
- Fundo azul petróleo (`#17212f`) com gradiente radial sutil — nunca preto puro
- Cor de destaque única: azul royal (`#0114c1e9`)
- Logo: monograma **Z** em destaque, com o nome "maestro" sutil ao fundo (efeito de profundidade)

---

## Estrutura de apps

| App             | Camada    | Responsabilidade                                | Status                         |
| --------------- | --------- | ----------------------------------------------- | ------------------------------ |
| `accounts`      | Suporte   | Autenticação, usuários, home/dashboard          | ✅ Funcional                   |
| `robots`        | Domínio   | Cadastro, edição, exclusão, iniciar/parar robôs | ✅ Funcional (front+back)      |
| `executions`    | Domínio   | Histórico e detalhe de execuções, log           | ✅ Funcional (front+back)      |
| `scheduler`     | Domínio   | Agendamento recorrente                          | ⏳ Planejado (Nível 2)         |
| `audit`         | Suporte   | Auditoria/log de ações                          | ⏳ Planejado (Nível 3)         |
| `notifications` | Suporte   | Alertas de falha                                | ⏳ Planejado (Nível 3)         |
| `api`           | Interface | Endpoints REST                                  | ⏳ Planejado (Nível 2)         |
| `dashboard`     | Interface | Métricas consolidadas                           | 🟡 A home atual cobre o básico |

---

## Checklist de progresso

### Nível 1 — Iniciante

**Setup do projeto**

- [x] Ambiente virtual isolado (`uv`)
- [x] Secrets fora do código (`.env` + `python-dotenv`)
- [x] `SECRET_KEY` via variável de ambiente
- [ ] `DEBUG` lido corretamente do `.env` como booleano (débito técnico conhecido)
- [ ] `.env.example` documentando as variáveis esperadas
- [x] `.gitignore` cobrindo `.env`, `__pycache__`, `db.sqlite3`

**Apps e estrutura**

- [x] Apps `accounts`, `robots`, `executions` criados e registrados

**Autenticação (`accounts`)**

- [x] Login via `LoginView`, logout via POST protegido por CSRF
- [x] `LOGIN_URL`, `LOGIN_REDIRECT_URL`, `LOGOUT_REDIRECT_URL` configurados
- [x] Home/dashboard com contagem de robôs por status e últimas 5 execuções

**Frontend base**

- [x] `templates/` e `static/` configurados
- [x] `base.css` com variáveis de tema e componentes compartilhados (sidebar, tabela, badges, page-header)
- [x] `base.html` com sidebar lateral (logo, navegação, item ativo destacado)
- [x] Identidade visual (terminal/console) aplicada em login, home, robôs e execuções

**App `robots`**

- [x] Model `Robo` com testes (criação, status padrão, `get_status_display`, `__str__`, regra `PROTECT`)
- [x] Listagem conectada ao banco com `Prefetch` (evita N+1), última execução e descrição expansível
- [x] Cadastro de robô (`create.html` + view) — **sem `ModelForm` ainda**, lê `request.POST` direto
- [x] Edição de robô (`edit.html` + `robot_edit`)
- [x] Exclusão de robô com confirmação (`exclusion_confirm.html` + `robot_exclusion`), tratando `ProtectedError`
- [x] Botões "iniciar"/"parar" execução (simulados — sem execução real ainda)
- [ ] `forms.py` com validação via `ModelForm`

**App `executions`**

- [x] Model `Execucao` com testes (criação, status padrão, `__str__`, regras `PROTECT` e `SET_NULL`)
- [x] Listagem global de execuções (`/execucoes/`), ordenada por mais recente
- [x] Tela de detalhe de execução, exibindo o `log` completo em `<pre>`
- [ ] Testes das views de `robots` e `executions` (hoje só os models têm testes)

**Testes**

- [x] Testes unitários dos models `Robo` e `Execucao`
- [ ] Testes das views (acesso logado/deslogado, permissões, fluxo de edição/exclusão)
- [ ] Teste manual do fluxo completo ponta a ponta

### Nível 2 — Intermediário (não iniciado)

- [ ] Groups e Permissions do Django configurados
- [ ] Celery + Redis integrados
- [ ] Execução isolada via `subprocess` (lista de argumentos, nunca `shell=True`)
- [ ] `django-celery-beat` para agendamento recorrente
- [ ] Rate limiting no login (`django-axes` ou similar)
- [ ] Log de auditoria básico
- [ ] API REST inicial (DRF) com autenticação por token/JWT
- [ ] 💡 Frente de estudo: agente em Go para execução remota via WebSocket (ver "Ideias em avaliação")

### Nível 3 — Avançado (não iniciado)

- [ ] Execução em containers Docker efêmeros
- [ ] Gestão de segredos real (cofre/criptografia em repouso)
- [ ] Headers de segurança (`SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, etc.)
- [ ] `django-csp` configurado
- [ ] Scan de dependências (`pip-audit`/`safety`) no fluxo de trabalho
- [ ] Observabilidade (logging estruturado, alertas)

### Nível 4 — Sênior (não iniciado)

- [ ] Threat modeling formal (STRIDE)
- [ ] Revisão LGPD (retenção de logs, criptografia ponta a ponta)
- [ ] CI/CD com testes, lint e scan de segurança
- [ ] Infra como código (Terraform)
- [ ] Plano de disaster recovery testado

---

## Débito técnico conhecido

| Item                                    | Descrição                                                                                                                    | Prioridade               |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| `DEBUG` no settings                     | `os.getenv('DEBUG')` retorna string, não booleano — `DEBUG` fica sempre `True` na prática, mesmo com `DEBUG=False` no `.env` | 🔴 Alta (segurança)      |
| `EMAIL_BACKEND`                         | Setting `MAILERS` no `settings.py` não existe no Django; precisa virar `EMAIL_BACKEND` (string)                              | 🟡 Média                 |
| Cadastro/edição de robô sem `ModelForm` | Views leem `request.POST` diretamente, sem validação de tipo/tamanho                                                         | 🟡 Média                 |
| Iniciar/parar execução é simulado       | Não dispara processo real; aguardando Nível 2/3 (Celery) ou o agente Go                                                      | 🟢 Esperado nesta fase   |
| Formatter do editor                     | VSCode formatando `.html` como HTML genérico, quebrando tags Django — mitigado com `.vscode/settings.json`                   | 🟢 Baixa (já contornado) |

---

## Convenções do projeto

- **Commits**: mensagens em português, descrevendo o quê e o porquê
- **Templates**: uma tag Django por linha, nunca condensar `{% %}` em uma linha só (já causou bugs de parsing por formatação automática)
- **CSS**: variáveis de tema centralizadas em `base.css`; componentes usados em mais de uma tela também moram lá (tabela, badges, page-header); cada tela específica tem seu próprio CSS enxuto
- **Segurança**: nenhuma feature é considerada "pronta" sem revisão básica (permissões, CSRF, validação de entrada, tratamento de `ProtectedError`)
- **Ações que mudam estado** (excluir, iniciar, parar, logout) sempre via POST, nunca GET

---

## Como rodar localmente

```bash
# Instalar dependências
uv sync

# Rodar migrations
uv run manage.py migrate

# Criar superusuário (se ainda não tiver um)
uv run manage.py createsuperuser

# Subir o servidor
uv run manage.py runserver
```

Acesse `http://localhost:8000/login/` para entrar.

---

## Por que este projeto existe

O Maestro é um projeto longo e ambicioso, fruto de 2 anos de estudos em programação, especialmente em Python e RPA. Mas entendo a necessidade de ampliar os conhecimentos em várias áreas da programação, e esse projeto vem pra cobrir essa lacuna, onde posso dar vida ao RPA, ampliando e documentando todo o conhecimento adquirido até aqui.

---

**Vitor Zavan**
_zavan · rpa_
