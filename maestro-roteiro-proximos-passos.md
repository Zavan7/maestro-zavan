# Maestro — Roteiro dos Próximos Passos

> Formato: cada etapa diz o que precisa de **Front**, o que precisa de **Back** (e se envolve banco de dados), e fecha com **Dicas** — os pontos onde normalmente se erra ou esquece algo de segurança. Siga na ordem; cada etapa assume que a anterior está funcionando.

---

## Etapa 0 — Reconstituir o ambiente na máquina nova (Ubuntu 26.04)

Antes de codar qualquer feature nova, seu projeto precisa voltar a rodar nessa máquina.

**Back (ambiente, sem tela nenhuma envolvida)**
- Instalar o `uv` na máquina nova
- Clonar o repositório do projeto (`git clone ...`) — se o `db.sqlite3` estava no `.gitignore` (deveria estar), o banco não veio junto, então:
  - `uv sync` pra reinstalar as dependências do `pyproject.toml`/`uv.lock`
  - Recriar o `.env` do zero (ele nunca deveria estar versionado) — se você não guardou os valores em outro lugar, vai precisar gerar um `SECRET_KEY` novo
  - `uv run manage.py migrate` pra recriar as tabelas
  - `uv run manage.py createsuperuser` de novo, já que o banco é novo

**Dicas**
- Esse é o momento perfeito pra confirmar que o `.gitignore` está fazendo o trabalho certo: se `db.sqlite3`, `.env` e `__pycache__` não aparecem no `git status` depois do clone, está tudo certo
- Reinstala também a extensão/configuração do VSCode que resolvia o bug do Prettier quebrando tags Django (`.vscode/settings.json` deveria ter vindo no repositório — confirma se ele está versionado; se não estava, recria)
- Rodar os testes (`uv run manage.py test`) logo depois de tudo reinstalado é a forma mais rápida de confirmar que o ambiente novo está saudável antes de seguir

---

## Etapa 1 — Fechar o débito técnico de segurança (antes de qualquer feature nova)

Esses itens já estavam pendentes antes das férias — fechar agora evita que "depois eu arrumo" vire "nunca arrumei".

**Back only, sem front**
- Corrigir a leitura de `DEBUG` no `settings.py`: hoje `os.getenv('DEBUG')` retorna string, e qualquer string não-vazia é `True` em Python. Pesquise como comparar a string lida com `"True"` (ou uma lib tipo `python-decouple`, que já resolve isso nativamente)
- Corrigir `MAILERS` → `EMAIL_BACKEND` (setting correta do Django)

**Dicas**
- Depois de corrigir o `DEBUG`, teste explicitamente: coloca `DEBUG=False` no `.env` e confirma que uma URL inexistente mostra a página 404 genérica do Django, não a página de debug detalhada. Se ainda aparecer a página detalhada, a correção não funcionou
- Esse é um bom momento pra criar o `.env.example` (mencionado no checklist do README) — um arquivo sem valores reais, só mostrando quais variáveis existem, pra facilitar reconstruir o ambiente da próxima vez (irônico, dado o que você acabou de passar na Etapa 0)

---

## Etapa 2 — `ModelForm` para robôs (substituindo o `request.POST` manual)

**Back — envolve banco de dados indiretamente (validação antes de salvar)**
- Criar `robots/forms.py` com uma classe `RoboForm(forms.ModelForm)`, apontando `model = Robo` e `fields = [...]`
- Trocar `robot_create` e `robot_edit` pra usar esse form em vez de ler `request.POST.get(...)` campo por campo
- Pesquisar a diferença entre `form.is_valid()` e simplesmente confiar que os dados vieram certos — esse é o ponto central da etapa

**Front — ajuste pequeno, não uma tela nova**
- Os templates `create.html` e `edit.html` provavelmente vão trocar os `<input>` manuais por `{{ form.campo }}` (parecido com o que fizemos na tela de login, lá no início)
- Vai precisar de um jeito de mostrar erros de validação (campo obrigatório vazio, nome duplicado, etc.) — pesquisa `{{ form.campo.errors }}`

**Dicas**
- Esse é o momento de decidir: quer usar `{{ form.as_p }}` (rápido, mas perde o controle fino de estilo que você já tem) ou continuar renderizando campo por campo manualmente (mais trabalho, mais controle)? Dado que você já tem uma identidade visual definida, provável que valha manter o controle manual
- `ModelForm` valida automaticamente `max_length` e tipos — teste mandando um nome gigante ou um campo vazio pra ver a validação pegando antes de chegar no banco

---

## Etapa 3 — Testes das views (`robots` e `executions`)

**Back only — validação, sem tela**
- Testar `robot_list`, `robot_create`, `robot_edit`, `robot_exclusion`, `robot_start`, `robot_stop` — acesso logado vs deslogado, e o caminho de erro (tentar excluir robô com execução associada, via view, não só via model)
- Testar `execution_list` e `execution_detail` — incluindo o caso de `pk` inexistente (deve dar 404)

**Dicas**
- Use `self.client.login(...)` e `self.client.get(...)/post(...)` do `django.test.TestCase` — é diferente de testar o model direto, porque aqui você está simulando uma requisição HTTP de verdade
- Lembra da pegadinha do `refresh_from_db()` que você aprendeu nos testes de model? Ela pode aparecer de novo aqui: depois de um POST que edita um robô, se você quiser conferir o valor salvo, também precisa recarregar o objeto do banco antes de comparar
- Teste também que uma view protegida por `@login_required` redireciona (302) pro login quando ninguém está autenticado, em vez de simplesmente dar erro

---

## Etapa 4 — Groups e Permissions (Nível 2, autorização de verdade)

**Back — mexe direto no banco (grupos são registros)**
- Decidir quais grupos fazem sentido: por exemplo, "Operador" (só inicia/para execuções), "Administrador" (cadastra/edita/exclui robôs)
- Criar os grupos via Admin (ou uma migration de dados, se quiser algo reproduzível) e atribuir permissões
- Trocar `@login_required` por `@permission_required('robots.add_robo')` (ou equivalente) nas views que deveriam ser restritas

**Front**
- Esconder botões que o usuário não tem permissão de usar (ex: "excluir" só aparece pra quem tem a permissão) — mas lembra: isso é só cosmético, a proteção de verdade é no back
- Talvez uma indicação visual de qual grupo o usuário logado pertence

**Dicas**
- Nunca confie em esconder o botão no template como controle de acesso — teste digitando a URL diretamente (`/robots/5/excluir/`) logado com um usuário sem permissão, e confirme que a view recusa, não só que o botão sumiu
- `@permission_required` sozinho, por padrão, redireciona pro login em vez de dar 403 — pesquisa o parâmetro `raise_exception=True` se você quiser um comportamento diferente (403 direto pra quem já está logado mas sem permissão)

---

## Etapa 5 — Celery + Redis (execução assíncrona de verdade)

Essa é a etapa que substitui a simulação de `robot_start`/`robot_stop` por execução real.

**Back — muda a arquitetura, envolve banco de dados e um serviço novo (Redis)**
- Instalar e configurar Celery no projeto, com Redis como broker
- Criar uma `task` Celery que efetivamente dispara o script (via `subprocess`, lista de argumentos, nunca `shell=True`)
- A view `robot_start` passa a chamar `.delay()` da task, em vez de só criar o registro `Execucao` direto
- Pensar em como capturar stdout/stderr do processo e salvar no campo `log` da execução

**Front**
- Provavelmente nenhuma tela nova — mas o status na listagem/detalhe agora reflete algo acontecendo de verdade em background, então vale considerar algum tipo de atualização (mesmo que seja só "recarregue a página" por enquanto — WebSocket/polling fica pra depois)

**Dicas**
- Rode o worker do Celery separado do `runserver` (`celery -A maestro worker`) — é um processo à parte, muita gente esquece disso e fica sem entender por que a task "não roda"
- Limite o tamanho do log capturado — um script com saída infinita ou muito grande pode encher o disco (isso já estava no seu roteiro original de segurança)
- Nunca deixe o caminho do script vir direto de input do usuário sem validação — valide/whitelist contra o que está cadastrado no banco

---

## Etapa 6 — Agendamento recorrente (`django-celery-beat`)

**Back — nova tabela no banco (o próprio `django-celery-beat` cria as suas)**
- Instalar `django-celery-beat`, rodar as migrations dele
- Criar um model ou usar o que a lib já fornece pra guardar "esse robô roda toda segunda às 8h", por exemplo
- Validar a expressão cron antes de salvar (evitar entrada que quebre o parser)

**Front — tela nova**
- Formulário de agendamento: qual robô, qual frequência
- Ativar o item "agendamentos" no sidebar, que hoje está como "em breve"

**Dicas**
- Cron expressions são fáceis de errar digitando na mão — considere campos separados (dia da semana, hora) em vez de um campo de texto livre com a expressão crua, pelo menos na primeira versão
- Teste um agendamento pra rodar em 1-2 minutos no futuro, não em produção real, só pra confirmar que o disparo automático está funcionando antes de confiar em agendamentos de longo prazo

---

## Etapa 7 — API REST (Django REST Framework)

**Back — nova camada, reaproveitando os models existentes**
- Instalar DRF, criar serializers pra `Robo` e `Execucao`
- Criar viewsets/endpoints, protegidos por autenticação (token ou JWT — pesquisa `djangorestframework-simplejwt`)
- Configurar throttling (limite de requisições) desde o início, não depois

**Front — nenhuma tela nova ainda**
- Essa etapa é só backend; o consumo da API (React, ou outro cliente) fica pra depois, se você decidir seguir com a migração de frontend que ficou cogitada lá no início

**Dicas**
- Nunca exponha um endpoint sem autenticação, "só pra testar rápido" — esse tipo de exceção temporária tende a ir pra produção sem ninguém perceber
- Teste a API com um usuário sem permissão nenhuma tentando acessar dados de outro — é o mesmo princípio de "nunca confiar só na interface" da Etapa 4, agora aplicado à API

---

## Etapa 8 — Isolamento de execução via Docker (Nível 3)

**Back — muda a etapa 5 de arquitetura, mexe com infraestrutura**
- Em vez do `subprocess` rodar direto na máquina do worker Celery, cada execução dispara um container efêmero (usando o Docker SDK for Python)
- Limitar CPU/memória/timeout do container
- Rede do container restrita, sem acesso livre à internet salvo whitelist

**Dicas**
- Essa etapa costuma ser a mais subestimada em tempo — reserve mais tempo do que imagina, porque envolve aprender Docker SDK além de Django
- Teste um cenário de "container que nunca termina" de propósito, pra confirmar que o timeout realmente mata o processo, antes de confiar nisso com um robô real

---

## Etapa 9 — O agente em Go (a ideia que você registrou antes das férias)

**Back — projeto separado, comunicando com o Maestro via WebSocket**
- Esse é o ponto de abrir a frente de estudo em Go, com escopo pequeno: um binário que conecta por WebSocket no Django, escuta comandos, dispara o script Python, reporta status/log de volta
- No lado Django, você vai precisar de um servidor WebSocket — pesquisa Django Channels, que é a forma padrão de fazer isso

**Front**
- Nenhuma tela nova imediatamente — o impacto aparece na experiência (execuções remotas realmente rodando), não em uma interface nova

**Dicas**
- Comece o agente Go rodando na mesma máquina que o Django, só pra validar a comunicação, antes de tentar rodar numa máquina remota de verdade
- Pense em autenticação do agente desde o início (como o Django sabe que é realmente o seu agente conectando, e não qualquer um?) — isso é seguraça básica de um sistema distribuído

---

## Etapa 10 — Observabilidade, auditoria e compliance (Nível 3/4)

**Back — mexe em várias camadas ao mesmo tempo**
- Logging estruturado (JSON), integração com Sentry pra erros
- Auditoria: quem fez o quê, quando — pode usar `django-simple-history` ou uma tabela própria
- Revisão de headers de segurança (`SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, etc.)
- `django-csp` configurado

**Front**
- Uma tela de auditoria (quem alterou o quê) pode fazer sentido aqui, dependendo do quanto você quer aprofundar essa parte

**Dicas**
- Não tente fazer tudo de uma vez — esse é literalmente o Nível 3/4 do seu próprio roteiro original, pensado pra vir depois de tudo que já rodou de verdade em produção (ou pelo menos, testado como se fosse)
- Reveja o checklist do seu próprio README antes de começar cada uma dessas — ele já tem a ordem de prioridade que vocês (você e eu, nas sessões anteriores) definiram com calma

---

## Como usar esse roteiro no dia a dia

- Sempre que terminar uma etapa, mova o card correspondente no seu Trello de "Backlog" pra "Em andamento" e depois "Concluído" — o board já está estruturado pra isso
- Atualize o checklist do `README.md` junto — ele é a fonte de verdade do que está pronto, e vale mais a pena mantê-lo fiel do que perfeito
- Se travar em alguma etapa, o padrão que funcionou bem até aqui: leia a mensagem de erro completa, identifique exatamente onde ela aconteceu, e pesquise o conceito específico antes de tentar resolver no escuro
