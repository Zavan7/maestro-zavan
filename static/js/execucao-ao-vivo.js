// Log ao vivo da tela de detalhe de execução.
//
// A página já vem com o log gravado no banco e o número da última linha
// (data-ultima-linha). Pelo WebSocket chegam lotes de linhas numeradas:
// números que a página já tem são ignorados, e um salto na numeração
// (linhas que saíram entre a gravação no banco e a conexão) vira uma
// linha "…". No aviso de fim, a página recarrega para mostrar o status e
// a duração finais. Se a conexão cair antes do fim, a página volta a
// recarregar a cada 5 segundos, como antes do log ao vivo.
//
// Live log for the execution detail page.
//
// The page arrives with the log saved in the database and the number of
// the last line (data-ultima-linha). Numbered batches of lines arrive
// over the WebSocket: numbers the page already has are skipped, and a gap
// in the numbering (lines written between the database save and the
// connection) becomes a "…" line. On the end notice, the page reloads to
// show the final status and duration. If the connection drops before the
// end, the page goes back to reloading every 5 seconds, as before the
// live log.
(function () {
  "use strict";

  const RECARGA_SEM_CONEXAO_MS = 5000;
  const MARGEM_DO_FIM_PX = 24;
  const PADRAO_DE_ERRO = /ERROR|Traceback/;

  const lista = document.getElementById("log");
  const estado = document.getElementById("log-estado");
  if (!lista || !lista.dataset.wsUrl) {
    return;
  }

  let ultimaLinha = Number(lista.dataset.ultimaLinha) || 0;
  let terminou = false;

  function estaNoFim() {
    return (
      lista.scrollHeight - lista.scrollTop - lista.clientHeight <
      MARGEM_DO_FIM_PX
    );
  }

  function novoItem(numero, texto) {
    const item = document.createElement("li");
    item.value = numero;
    item.textContent = texto; // nunca innerHTML: o log vem do robô
    if (PADRAO_DE_ERRO.test(texto)) {
      item.classList.add("log-erro");
    }
    return item;
  }

  function acrescentar(linhas) {
    const acompanharFim = estaNoFim();
    const vazio = lista.querySelector(".log-vazio");
    if (vazio) {
      vazio.remove();
    }
    for (const linha of linhas) {
      if (linha.numero <= ultimaLinha) {
        continue;
      }
      if (linha.numero > ultimaLinha + 1) {
        const salto = novoItem(linha.numero - 1, "…");
        salto.classList.add("log-salto");
        lista.appendChild(salto);
      }
      lista.appendChild(novoItem(linha.numero, linha.texto));
      ultimaLinha = linha.numero;
    }
    if (acompanharFim) {
      lista.scrollTop = lista.scrollHeight;
    }
  }

  function semConexao() {
    if (terminou) {
      return;
    }
    if (estado) {
      estado.textContent = "reconectando…";
    }
    window.setTimeout(function () {
      window.location.reload();
    }, RECARGA_SEM_CONEXAO_MS);
  }

  const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(
    protocolo + "//" + window.location.host + lista.dataset.wsUrl
  );

  socket.addEventListener("message", function (evento) {
    const mensagem = JSON.parse(evento.data);
    if (mensagem.tipo === "linhas") {
      acrescentar(mensagem.linhas);
    } else if (mensagem.tipo === "fim") {
      terminou = true;
      socket.close();
      window.location.reload();
    }
  });
  socket.addEventListener("close", semConexao);

  lista.scrollTop = lista.scrollHeight;
})();
