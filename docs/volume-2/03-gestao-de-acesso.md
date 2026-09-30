# 03. Gestão de usuários e registro de alterações

## Contexto

A primeira seção de verdade da aba de configurações. É a parte mais sensível do sistema: quem mexe em quem pode o quê. Foi dividida em duas partes de propósito: primeiro as regras, com testes; depois as telas. As regras ficaram provadas antes de existir qualquer botão que as usasse.

## O que foi feito

**Parte A: as regras**

- `config/models.py`: model `RegistroAcesso` (autor, alvo, ação, detalhe, data)
- `config/services.py` (novo): `AlteracaoRecusada`, `_verificar_se_pode_alterar`, `pode_alterar`, `trocar_grupo`, `alternar_ativo`
- `config/tests.py`: `ServicosDeAcessoTest`

**Parte B: as telas**

- `config/views.py`: `config_users`, `config_user_group`, `config_user_toggle`; resumo de usuários na `config_home`
- `config/urls.py`: três rotas novas em `/configuracoes/usuarios/`
- `templates/config/usuarios.html`: tabela de usuários e lista de alterações recentes
- `static/css/config.css`: formulário de grupo, linha inativa, etiqueta de superusuário, registro
- `config/tests.py`: `ConfigUsersViewsTest`

## Decisões

| Decisão | Alternativa | Motivo |
|---|---|---|
| Regras num serviço, como o `disparar_execucao` | Regras nas views | Mesmo padrão do projeto; a tela e as ações nunca discordam |
| Ninguém altera o próprio acesso | Permitir, com aviso | Fecha duas brechas de uma vez: autopromoção e o último administrador se trancando para fora |
| Superusuário só alterado por superusuário | Tratar como qualquer usuário | Impede que quem tem a permissão da aba desative quem tem poder total |
| Nenhuma função toca `is_superuser` ou `is_staff` | Um campo "administrador" na tela | Não existe caminho, pela interface, para virar superusuário |
| Um grupo por usuário (`groups.set([grupo])`) | Vários grupos | Numa tela de gestão, vários grupos vira "pode o quê, afinal?" |
| Desativar, nunca excluir | Excluir usuários | Preserva robôs, execuções e registros; o `PROTECT` do responsável nem deixaria na maioria dos casos |
| `RegistroAcesso` com `default_permissions = ()` | Registro editável no admin | Auditoria que pode ser editada não é auditoria |
| `detalhe` com texto pronto (`"analista: Operador → Administrador RPA"`) | Só as chaves estrangeiras | Continua legível mesmo se o vínculo com o usuário se perder (`SET_NULL`) |
| `@transaction.atomic` nas funções de serviço | Gravar alteração e registro separados | Não existe troca sem registro, nem registro de troca que falhou |
| `pode_alterar` reaproveitando a verificação | Repetir as regras no template | A tela decide o que mostrar com as mesmas regras que as ações aplicam |
| Grupo vindo do POST passa por `get_object_or_404` | Confiar no id | Id inventado no HTML responde 404 |

## Erros e correções

- Nenhum erro de código: as duas partes foram validadas antes de ir para o projeto.
- **O resumo no card errado** (registrado na nota 02) aconteceu ao aplicar a parte B.

## Acertos

- **Dividir em regras e telas.** Os testes da parte A provaram as travas sem nenhuma interface: `trocar_grupo(admin, admin, None)` levanta `AlteracaoRecusada`, e o teste confere também que nada mudou e nada foi registrado.
- **Usuário desativado não entra**: testado com `self.client.login(...)` devolvendo `False`. A sessão aberta de um usuário desativado deixa de valer na próxima requisição, porque o Django recusa usuários inativos ao recarregar a sessão.
- **Mensagem escapada no teste**: `assertContains(response, "Grupo de &#x27;analista&#x27; alterado.")`, porque o teste compara com o HTML, onde o apóstrofo chega escapado. Bom exemplo concreto do escape automático.
- **Ações só por POST, testado**: um `GET` na rota de desativar não altera nada.

## Conceitos para o livro

- Escalada de privilégio e as travas que a impedem
- Auditoria: por que o registro não pode ser editável e por que guardar texto pronto
- `@transaction.atomic` como decorator
- `groups.set`, `groups.clear`, `prefetch_related("groups")`
- `is_active` e o comportamento da sessão
- `get_user_model()` nas views
- Reutilizar uma verificação que levanta exceção como pergunta booleana

## Pendências

- Criar usuário pela tela (precisa de cuidado com a senha: definição inicial ou convite)
- Paginação da lista de usuários e do registro, quando crescerem
