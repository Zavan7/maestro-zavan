# Changelog

Todas as mudanças relevantes do Maestro ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e a numeração segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

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