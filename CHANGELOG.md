# Changelog

Todas as mudanças relevantes do Maestro ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e a numeração segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado

- Agendamento recorrente de robôs por horário e dias da semana, com pausar e retomar
- Estados visuais nas listas de robôs e agendamentos: rodando, agendado, pausado e parado
- Origem das execuções (manual ou agendamento) e etiqueta "agendado" no histórico
- Duração da execução na tela de detalhe
- Aba de configurações, visível apenas para quem tem alguma permissão de configuração
- Gestão de usuários e acesso: troca de grupo, desativação e reativação, com registro de todas as alterações
- Grupo "Administrador do sistema"
- Prévia da seção de limites padrão de execução, ainda sem edição
- Testes do agendamento, do disparo de execuções e da aba de configurações

### Alterado

- Iniciar e parar robôs passa a exigir a permissão `executar_robo`; antes bastava estar logado
- Os grupos de acesso passam a ser criados por uma migração de dados, sem comandos manuais

### Corrigido

- A tela de cadastro de robô exibia o formulário de edição
- O CSS da tela de detalhe de execução não era carregado
- O cabeçalho das páginas ficava sem estilo nas telas que não carregavam o CSS de robôs

### Segurança

- Um usuário sem grupo não consegue mais iniciar ou parar robôs
- Ninguém altera o próprio acesso pela aba de configurações, e superusuários só podem ser alterados por outro superusuário

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