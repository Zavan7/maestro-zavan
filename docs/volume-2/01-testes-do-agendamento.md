# 01. Testes do agendamento e do disparo

## Contexto

O agendamento entrou em produção sem testes (o volume 1 deixou os testes como exercício, no capítulo 14). O card no Trello ficou em "Em revisão" até eles existirem. A regra do projeto: nenhuma funcionalidade está pronta sem testes dos caminhos negativos.

## O que foi feito

- `scheduler/tests.py` (novo): `AgendamentoModelTest`, `VerificarAgendamentosTest`, `ScheduleViewsTest`, 19 testes
- `robots/tests.py`: classe `DisparoTest`, 5 testes do serviço `disparar_execucao`
- Ajustes de CSS antes dos testes: `.page-header` movido para o `base.css`; `a.link-btn` sem sublinhado

## Decisões

| Decisão | Alternativa | Motivo |
|---|---|---|
| Relógio fixo com `mock.patch.object(tasks.timezone, "localtime", ...)` | Parâmetro `agora` na tarefa | Mantém a tarefa intacta; o parâmetro seria igualmente válido e o livro deve mostrar os dois caminhos |
| Datas fixas numa segunda-feira (28/09/2026) | Datas relativas a "hoje" | Um teste que depende da hora real passa de manhã e falha à tarde |
| Função auxiliar `dias(*marcados)` | Sete argumentos por teste | Legibilidade; `dias("sexta")` diz a intenção |
| Testar o serviço direto, sem `Client` | Só testar pela view | As regras moram no serviço; view e agendador herdam a garantia |
| `full_clean()` para testar o `clean()` | `save()` | O Django não valida no `save()`; testar com `save()` passaria por engano |

## Erros e correções

- Nenhum erro de código nos testes em si: foram escritos e validados antes de serem passados adiante. Vale registrar como **acerto de processo**: rodar a suíte num projeto de validação antes de entregar o código evitou idas e vindas.

## Acertos

- **Os quatro casos de borda de `proxima_ocorrencia`**: ainda hoje; horário que já passou; dia desmarcado; mesmo dia da semana seguinte (o caso que justifica o laço de 8 dias, não 7).
- **O teste da ordem do `on_commit`**: com a tarefa trocada por `mock.patch("robots.services.executar_robo")`, `captureOnCommitCallbacks(execute=True)` executa os callbacks na saída do bloco. Dentro do bloco, `assert_not_called()`; fora, `assert_called_once_with(execucao.id)`. Prova que a execução existe no banco antes de o worker saber dela.
- **`assertLogs("scheduler.tasks", level="WARNING")`**: confirma a recusa no log e esconde o aviso da saída dos testes.
- **Recusa sem efeito colateral**: o teste da trava confere também que nada mudou nem foi registrado.
- **O teste do `SET_NULL` no agendamento**: excluir um agendamento mantém as execuções no histórico, só sem o vínculo.

## Conceitos para o livro

- `unittest.mock`: `patch`, `patch.object`, `return_value`, objetos falsos que registram chamadas (`assert_called_once_with`)
- `TestCase.captureOnCommitCallbacks` e por que o `on_commit` não dispara nos testes
- `assertLogs`
- Diferença entre `save()` e `full_clean()`
- Testes de casos de borda com datas

## Pendências

Nenhuma nesta entrega.
