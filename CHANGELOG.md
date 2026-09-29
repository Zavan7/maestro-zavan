# Changelog

Todas as mudanças relevantes do Maestro ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e a numeração segue o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Nada ainda]

Nada ainda. As próximas funcionalidades estão na coluna "Updates futuros" do Trello.

## [1.0.0] - 2026-09-28

### Adicionado

- Agendamento recorrente de robôs por horário e dias da semana, com pausar e retomar
- Estados visuais nas listas de robôs e agendamentos: rodando, agendado, pausado e parado
- Origem das execuções (manual ou agendamento) e tag "agendado" no histórico
- Duração da execução na tela de detalhe

### Corrigido

- A tela de cadastro de robô exibia o formulário de edição
- O CSS da tela de detalhe de execução não era carregado

### Limitações conhecidas

- O botão "parar" marca a execução como finalizada, mas não encerra o processo
- Os robôs rodam com as dependências do ambiente do Maestro