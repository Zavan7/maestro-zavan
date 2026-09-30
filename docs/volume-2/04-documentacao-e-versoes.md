# 04. CHANGELOG, README e o que eles ensinam sobre versões

## Contexto

No fim da sessão, README e CHANGELOG foram atualizados com o agendamento e a aba de configurações.

## Erros e correções

- **As novidades dentro da versão já lançada.** O CHANGELOG chegou com a seção do topo renomeada para "[Nada ainda]" e o conteúdo original da 1.0.0 substituído pelo do agendamento, que veio depois do lançamento. Se ficasse assim, o CHANGELOG diria que a 1.0.0 teve agendamento, e a tag `v1.0.0` no Git diria o contrário. Correção: a 1.0.0 restaurada como foi lançada, e tudo que veio depois em "Não lançado".
- **Uma explicação errada corrigida.** Durante o desenvolvimento, o motivo dado para o `list()` na view de robôs foi que o template reavaliaria a consulta e perderia os atributos. Ao escrever o volume 1, ficou claro que não é isso: um QuerySet avaliado guarda os resultados em cache. O `list()` protege contra operações que criam um QuerySet novo (`.filter()`, `.order_by()` acrescentados depois) e é necessário para o `sort()`. A correção foi para o livro e para a skill. Vale como tema: revisar as próprias explicações quando se escreve sobre elas.

## Decisões

- O CHANGELOG ganhou as seções "Alterado" e "Segurança", além de "Adicionado" e "Corrigido": iniciar e parar passarem a exigir permissão é uma **alteração de comportamento** que precisa ficar visível para quem atualiza.
- O débito técnico do README perdeu três itens resolvidos (`DEBUG`, `EMAIL_BACKEND`, grupos pelo shell) e ganhou dois honestos (retenção guardada mas sem limpeza; criação de usuários pelo admin).
- Sem tag nesta rodada: "Não lançado" ainda vai crescer com o resto da aba.

## Conceitos para o livro

- A seção de uma versão lançada nunca muda depois da tag
- As categorias do Keep a Changelog e quando usar cada uma
- Débito técnico como documento vivo: entra o que é real, sai o que foi resolvido
