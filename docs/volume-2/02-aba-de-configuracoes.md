# 02. Aba de configurações, permissões próprias e grupos por migração

## Contexto

O item "configurações" estava no menu como "em breve" desde o início. Os grupos de acesso eram criados à mão pelo shell, o que significava que um banco novo (outra máquina, produção, o banco de testes) nascia sem eles. E a gestão de quem pode o quê só era possível pelo admin do Django.

A ideia do Vitor: uma aba só para usuários com privilégio, começando pelas permissões. Discutimos o que mais caberia ali e ficaram quatro seções: usuários e acesso, status do sistema, retenção do histórico e limites padrão de execução (esta última só desenhada, com "em breve").

## O que foi feito

- App novo `config` (`uv run manage.py startapp config`, registrado no `INSTALLED_APPS`)
- `config/models.py`: `ConfiguracaoSistema` (registro único, retenção em dias, declara as permissões)
- `robots/models.py`: `class Meta` com a permissão `executar_robo`
- `robots/views.py`: `robot_start` e `robot_stop` passam a exigir `robots.executar_robo`
- `templates/robots/list.html`: botões iniciar e parar dentro de `{% if perms.robots.executar_robo %}`
- `config/migrations/0002_grupos_de_acesso.py`: migração de dados que cria os três grupos
- `config/views.py`: decorator `exige_acesso_a_configuracoes` e a view `config_home`
- `config/urls.py`, rota `/configuracoes/` no `maestro/urls.py`
- `templates/base.html`: item do menu dentro de `{% if perms.config %}`
- `templates/config/home.html` e `static/css/config.css`: página com uma seção por permissão
- `config/tests.py`: `ConfiguracaoSistemaTest` e `ConfigHomeTest`

## Decisões

| Decisão | Alternativa | Motivo |
|---|---|---|
| Uma permissão própria por seção | Só superusuário, ou o `is_staff` do admin | Dá para montar perfis (quem vê o status sem mexer em usuários) e testar com 403 como as outras regras |
| Permissões declaradas na `Meta` de `ConfiguracaoSistema` | Criar `Permission` à mão | É a forma padrão do Django; a migração cria as permissões |
| `default_permissions = ()` nesse model | Manter as quatro automáticas | Ninguém cria nem exclui "a configuração do sistema"; as automáticas seriam ruído |
| Registro único com `pk = 1` forçado no `save` e `atual()` com `get_or_create` | Um model com vários registros | Existe uma configuração do sistema, não várias |
| `has_module_perms("config")` e `{% if perms.config %}` para a aba | Listar as quatro permissões numa condição | Continua certo quando uma permissão nova entrar no app |
| Decorator próprio com `raise PermissionDenied` | `user_passes_test` | O `user_passes_test` manda para o login quem já está logado; queremos 403 |
| Grupos por migração de dados | Continuar pelo shell | Todo banco nasce com os grupos, inclusive o de testes |
| Pasta dos robôs só para leitura na aba | Editável pela tela | Uma conta invadida com essa permissão apontaria o Maestro para qualquer pasta; mesma lógica do agente em Go não aceitar caminho do servidor |
| Seção de limites desenhada, com campos `disabled` mostrando os valores reais | Esconder até existir | Mostra o que vem e o que vale hoje; mesmo recado visual do "em breve" do menu |

## A lacuna que a discussão revelou

Ao listar as permissões do projeto, apareceu uma brecha: iniciar e parar exigiam só login, então **um usuário sem grupo nenhum podia disparar robôs**. Não aparecia porque todo mundo tinha grupo. A aba de usuários ia torná-la visível (um usuário recém-criado já poderia iniciar robôs). Correção: a permissão `executar_robo`. Bom exemplo para o livro de como listar as permissões de um sistema revela o que ninguém tinha pensado.

## Erros e correções

- **`Permission.DoesNotExist` no shell.** O comando para dar `executar_robo` aos grupos falhou porque a permissão ainda não existia. Permissões próprias só são criadas **depois do `migrate`**, num sinal pós-migração. O `showmigrations` mostrou que a `0002` do `robots` nem tinha sido gerada.
- **A `class Meta` fora da classe.** O motivo de a migração não ter sido gerada: a `Meta` ficou sem o recuo, pertencendo ao módulo e não ao `Robo`. Mesma família dos erros de recuo do volume 1 (campo fora da classe, função dentro da classe). Resolvido reescrevendo o arquivo inteiro pelo terminal.
- **Migração de dados num banco novo.** Descoberto na validação, antes de chegar ao projeto: a migração que cria os grupos quebraria num banco vazio, porque roda antes de as permissões existirem. Solução: chamar `create_permissions` para cada app antes de usar as permissões.
- **O resumo de usuários no card errado.** O trecho novo foi colado na seção de retenção, no lugar do "Hoje: 90 dias". O teste `test_administrador_do_sistema_ve_as_secoes` passou mesmo assim, porque `assertContains` só verifica se o texto está na página, não onde. Lição: teste não substitui olhar a tela.
- **Setas cinza nos campos numéricos desabilitados.** Os botões de incremento do navegador. Resolvido com `appearance: textfield` e `::-webkit-inner-spin-button`.
- **O Prettier voltou.** O `base.html` apareceu com as tags do Django na margem e atributos quebrados em várias linhas: a configuração do VSCode se perdeu com a reinstalação da máquina.

## Acertos

- **A migração pode rodar sobre dados existentes.** `get_or_create` e `permissions.add` fizeram os grupos criados antes pelo shell serem encontrados e só completados, sem duplicar nem remover nada. Validado: rodar a migração duas vezes resulta em três grupos.
- **Testes com os grupos reais.** Como a migração roda no banco de testes, os testes da aba usam `Group.objects.get(name="Operador")` em vez de dar permissões soltas. Os testes passam a verificar o acesso exatamente como ele foi definido.
- **Um teste por visibilidade de seção**: um usuário só com `ver_status_sistema` vê o status e não vê usuários.

## Conceitos para o livro

- `Meta.permissions` e `default_permissions`
- O ciclo de vida das permissões: criadas no sinal `post_migrate`
- Migrações de dados: `RunPython`, `apps.get_model` (models históricos), dependências com `__latest__`, reverso com `noop`, idempotência
- `has_module_perms` e `perms.app` no template
- Escrever um decorator de view: `@wraps`, `PermissionDenied`, empilhar com `login_required`
- Padrão de registro único (singleton) num model
- Validadores de campo
- `repeat(auto-fit, minmax(...))` no CSS

## Pendências

- Status do sistema (Redis, worker, agendador)
- Retenção: edição do valor e a tarefa de limpeza
- Criar usuário pela tela
- Limites padrão editáveis (versão 1.1)
