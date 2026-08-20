"""Mensagens da Conversa (solicitante ↔ responsável) pra polling em tempo real
na tela de detalhe do chamado — ver visualizar_chamado.html e
app/routes/api_chamados.py::api_mensagens_novas_chamado.

Sem isso, uma mensagem nova só aparecia depois de a página ser recarregada
manualmente, mesmo pra quem tinha acabado de enviá-la (pedido do usuário,
2026-08-18)."""

from app.models_historico import Historico
from app.services.traducao_conteudo_service import traduzir_varios

ACOES_CONVERSA = ("resposta_solicitante", "resposta_responsavel")


def historico_fora_da_conversa(chamado_id: str, apos_id: int = 0) -> bool:
    """True se há Historico deste chamado gravado depois de apos_id que NÃO
    é mensagem da Conversa (status, anexo, decisão de previsão, transferência/
    escalonamento etc.) — sinaliza a tela de detalhe pra avisar "chamado
    atualizado" sem duplicar o polling já existente das mensagens (item 2 do
    plano de tempo real, generaliza o padrão de mensagens_novas acima)."""
    historico = Historico.get_by_chamado_id(chamado_id)
    return any(h.acao not in ACOES_CONVERSA and (h.id or 0) > apos_id for h in historico)


def mensagens_novas(chamado_id: str, apos_id: int = 0, idioma_destino: str = "en") -> list[dict]:
    """Mensagens da conversa gravadas depois de `apos_id` (exclusivo), da mais
    antiga pra mais nova (ordem de exibição). Historico.id é o cursor — evita
    ambiguidade de timestamps duplicados/iguais entre requisições de polling.

    Traduz `texto` em lote pro idioma_destino da sessão de quem está fazendo
    polling (LibreTranslate — ver traducao_conteudo_service); tipicamente
    0-2 mensagens novas por poll, então o lote é sempre pequeno. Fora de
    contexto Flask ou com a tradução desligada, texto_traduzido fica False."""
    historico = Historico.get_by_chamado_id(chamado_id)
    mensagens = [h for h in historico if h.acao in ACOES_CONVERSA and (h.id or 0) > apos_id]
    mensagens.reverse()  # Historico.get_by_chamado_id vem mais recente primeiro

    traducoes = traduzir_varios([h.valor_novo for h in mensagens], idioma_destino)

    return [
        {
            "id": h.id,
            "usuario_nome": h.usuario_nome,
            "eh_solicitante": h.acao == "resposta_solicitante",
            "texto": traducoes.get(h.valor_novo, {}).get("texto", h.valor_novo),
            "texto_traduzido": traducoes.get(h.valor_novo, {}).get("traduzido", False),
            "texto_original": traducoes.get(h.valor_novo, {}).get("original"),
            "data_iso": h.data_acao.isoformat() if h.data_acao else "",
            "data_formatada": h.data_acao_formatada(),
        }
        for h in mensagens
    ]
