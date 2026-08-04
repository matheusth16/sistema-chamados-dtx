"""Testes da funcionalidade de confirmação de resolução pelo solicitante.

Fase 2 — Postgres real: chamado persistido via Chamado.salvar() (db_session);
asserções de campos gravados recarregam o chamado com Chamado.get_by_id
em vez de inspecionar chamada a Firestore .update().
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado
from tests.factories import make_chamado

pytestmark = pytest.mark.usefixtures("db_session")


@pytest.fixture(autouse=True)
def _sem_thread_real_de_notificacao(monkeypatch):
    """Evita spawn de thread real nas notificações em background.

    A thread real chamaria Chamado.get_by_id, que abriria uma sessão concorrente
    sobre a MESMA conexão/savepoint do db_session de teste — corrompe o savepoint
    do teste principal (e pode vazar para o teste seguinte se a thread ainda
    estiver rodando na hora do teardown). Testes que querem exercitar o corpo da
    thread (ex.: test_api_coverage_gaps.py) sobrescrevem com seu próprio patch de
    threading.Thread dentro do escopo do teste.
    """
    monkeypatch.setattr("app.routes.api_chamados.threading.Thread", MagicMock())


def _criar_chamado(
    solicitante_id="sol_1", status="Concluído", confirmacao="pendente", reaberturas_count=0
):
    return make_chamado(
        solicitante_id=solicitante_id,
        status=status,
        confirmacao_solicitante=confirmacao,
        categoria="Manutenção",
        numero_chamado="CH-001",
        area="Planejamento",
        responsavel_id="sup_1",
        responsavel="Supervisor",
        solicitante_nome="Solicitante",
        reaberturas_solicitante_count=reaberturas_count,
    )


# ── Confirmar resolução ────────────────────────────────────────────────────────


def test_confirmar_resolucao_sucesso(client_logado_solicitante):
    """Solicitante confirma resolução: campo vira 'confirmado', status permanece 'Concluído'."""
    chamado = _criar_chamado()
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.confirmacao_solicitante == "confirmado"


def test_reabrir_chamado_sucesso(client_logado_solicitante):
    """Solicitante rejeita resolução: status volta para 'Aberto', motivo salvo no histórico."""
    chamado = _criar_chamado()
    with patch("app.routes.api_chamados.Historico") as mock_historico:
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema ainda persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["sucesso"] is True
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.status == "Aberto"
    assert atualizado.confirmacao_solicitante == "reaberto"
    # Histórico deve ter sido criado com o parâmetro correto (detalhe, não detalhes)
    mock_historico.assert_called_once()
    _, kwargs = mock_historico.call_args
    assert "detalhe" in kwargs, "Historico deve ser criado com 'detalhe=', não 'detalhes='"
    assert "detalhes" not in kwargs, "Typo 'detalhes' não deve ser usado"


def test_reabrir_sem_motivo_retorna_400(client_logado_solicitante):
    """Reabrir sem motivo retorna 400."""
    chamado = _criar_chamado()
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "reabrir", "motivo": ""},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


# ── Limite de reaberturas pelo solicitante (3x) ─────────────────────────────────


def test_reabrir_incrementa_contador(client_logado_solicitante):
    """Reabertura bem-sucedida incrementa reaberturas_solicitante_count."""
    chamado = _criar_chamado(reaberturas_count=1)
    with patch("app.routes.api_chamados.Historico"):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.reaberturas_solicitante_count == 2


def test_reabrir_no_limite_ainda_permite_terceira_vez(client_logado_solicitante):
    """Com 2 reaberturas anteriores, a 3ª ainda é permitida (limite = 3)."""
    chamado = _criar_chamado(reaberturas_count=2)
    with patch("app.routes.api_chamados.Historico"):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.reaberturas_solicitante_count == 3


def test_reabrir_apos_limite_atingido_bloqueado(client_logado_solicitante):
    """Após 3 reaberturas, a 4ª tentativa é bloqueada com 403."""
    chamado = _criar_chamado(reaberturas_count=3)
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "reabrir", "motivo": "Ainda com problema"},
        content_type="application/json",
    )
    assert r.status_code == 403
    assert r.get_json()["sucesso"] is False
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.status == "Concluído"


def test_reabrir_apos_limite_nao_dispara_notificacao(client_logado_solicitante):
    """Bloqueio por limite não deve disparar notificação de reabertura."""
    chamado = _criar_chamado(reaberturas_count=3)
    with patch("app.routes.api_chamados._enviar_notificacao_reabrir") as mock_notif:
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 403
    mock_notif.assert_not_called()


# ── Controle de acesso ─────────────────────────────────────────────────────────


def test_supervisor_nao_pode_confirmar_chamado_alheio(client_logado_supervisor):
    """Supervisor não pode confirmar chamado que não abriu (solicitante_id diferente)."""
    chamado = _criar_chamado(solicitante_id="sol_1")  # sup_1 != sol_1
    r = client_logado_supervisor.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 403


def test_supervisor_pode_confirmar_chamado_que_abriu(client_logado_supervisor):
    """Supervisor que é o solicitante do chamado pode confirmar a resolução."""
    chamado = _criar_chamado(solicitante_id="sup_1")  # mesmo ID do supervisor logado
    r = client_logado_supervisor.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["sucesso"] is True


def test_solicitante_nao_confirma_chamado_alheio(client_logado_solicitante):
    """Solicitante não pode confirmar chamado de outro usuário (403)."""
    chamado = _criar_chamado(solicitante_id="outro_usuario")
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 403


def test_chamado_sem_confirmacao_pendente_retorna_400(client_logado_solicitante):
    """Não é possível confirmar chamado que não está aguardando confirmação."""
    chamado = _criar_chamado(confirmacao=None)
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_solicitante_nao_confirma_nivel2_confirmado(client_logado_solicitante):
    """Regressão Nível 2: solicitante não pode confirmar chamado já 'confirmado' (400)."""
    chamado = _criar_chamado(confirmacao="confirmado")
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def test_acao_invalida_retorna_400(client_logado_solicitante):
    """Ação desconhecida retorna 400."""
    chamado = _criar_chamado()
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "deletar"},
        content_type="application/json",
    )
    assert r.status_code == 400


# ── E-mails ───────────────────────────────────────────────────────────────────


def test_reabrir_dispara_notificacao_supervisor(client_logado_solicitante):
    """Reabrir chamado chama _enviar_notificacao_reabrir com os dados corretos."""
    chamado = _criar_chamado()
    with (
        patch("app.routes.api_chamados.Historico"),
        patch("app.routes.api_chamados._enviar_notificacao_reabrir") as mock_notif,
    ):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_called_once()
    _, chamado_id_arg, data_arg, motivo_arg, _ = mock_notif.call_args[0]
    assert chamado_id_arg == str(chamado.id)
    assert motivo_arg == "Problema persiste"


def test_confirmar_dispara_notificacao_responsavel(client_logado_solicitante):
    """Confirmar resolução notifica o responsável designado do chamado."""
    chamado = _criar_chamado()
    with patch("app.routes.api_chamados._enviar_notificacao_confirmar") as mock_notif:
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_called_once()
    # Verifica que o helper recebeu o chamado_id correto
    _, chamado_id_arg, _data_arg, solicitante_nome_arg = mock_notif.call_args[0]
    assert chamado_id_arg == str(chamado.id)
    assert solicitante_nome_arg == "Solicitante Teste"


def test_confirmar_nao_dispara_notificacao_reabrir(client_logado_solicitante):
    """Confirmar resolução NÃO chama o helper de reabertura."""
    chamado = _criar_chamado()
    with (
        patch("app.routes.api_chamados._enviar_notificacao_reabrir") as mock_reabrir,
        patch("app.routes.api_chamados._enviar_notificacao_confirmar"),
    ):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_reabrir.assert_not_called()


def test_confirmar_nao_notifica_se_confirmacao_nao_persistiu(client_logado_solicitante):
    """Notificação de confirmação é ignorada se o chamado não estiver mais confirmado no banco."""
    chamado = _criar_chamado()

    with (
        patch("app.routes.api_chamados.threading.Thread", _thread_executa_sync),
        patch("app.services.notifications.notificar_responsavel_chamado_confirmado") as mock_notif,
        patch(
            "app.routes.api_chamados._dados_chamado_confirmado_valido",
            return_value=None,
        ),
    ):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "confirmar"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_not_called()


def test_reabrir_reseta_flags_lembrete(client_logado_solicitante):
    """Ao reabrir, flags de lembrete devem ser zeradas para o próximo ciclo de conclusão."""
    chamado = _criar_chamado()
    with patch("app.routes.api_chamados.Historico"):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Ainda com problema"},
            content_type="application/json",
        )
    assert r.status_code == 200
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.lembrete_confirmacao_1_enviado is False
    assert atualizado.lembrete_confirmacao_2_enviado is False


def test_reabrir_reseta_escalacao_resposta_nivel(client_logado_solicitante):
    """ADR-004: ao reabrir, escalacao_resposta_nivel deve ser zerado para reiniciar Escada A."""
    chamado = _criar_chamado()
    with patch("app.routes.api_chamados.Historico"):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Não resolvido"},
            content_type="application/json",
        )
    assert r.status_code == 200
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.escalacao_resposta_nivel == 0


def test_reabrir_reseta_flags_escada_b(client_logado_solicitante):
    """Fase 7: ao reabrir, campos Escada B devem ser zerados junto com Escada A."""
    chamado = _criar_chamado()
    with patch("app.routes.api_chamados.Historico"):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Não resolvido"},
            content_type="application/json",
        )
    assert r.status_code == 200
    atualizado = Chamado.get_by_id(chamado.id)
    assert atualizado.escalacao_resolucao_nivel == 0
    assert atualizado.alerta_supervisor_50_enviado is False
    assert atualizado.alerta_supervisor_80_enviado is False


def test_chamado_nao_concluido_nao_permite_confirmacao(client_logado_solicitante):
    """Regressão: status != 'Concluído' com confirmacao_solicitante='pendente' deve retornar 400.

    Garante que a guarda de status no endpoint impede que um chamado em 'Em Atendimento'
    com flag residual seja confirmado indevidamente.
    """
    chamado = _criar_chamado(status="Em Atendimento", confirmacao="pendente")
    r = client_logado_solicitante.post(
        f"/api/chamado/{chamado.id}/confirmar-resolucao",
        json={"acao": "confirmar"},
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["sucesso"] is False


def _thread_executa_sync(target, daemon=True):
    """Substituto de threading.Thread que executa o target na hora (para testes)."""

    class _T:
        def start(self):
            target()

    return _T()


def test_reabrir_nao_notifica_se_chamado_removido_antes_do_email(client_logado_solicitante):
    """Notificação de reabertura é ignorada se o chamado não existir mais no banco."""
    chamado = _criar_chamado()

    with (
        patch("app.routes.api_chamados.Historico"),
        patch("app.routes.api_chamados.threading.Thread", _thread_executa_sync),
        patch("app.services.notifications.notificar_supervisor_chamado_reaberto") as mock_notif,
        patch(
            "app.routes.api_chamados._dados_chamado_reaberto_valido",
            return_value=None,
        ),
    ):
        r = client_logado_solicitante.post(
            f"/api/chamado/{chamado.id}/confirmar-resolucao",
            json={"acao": "reabrir", "motivo": "Problema persiste"},
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_notif.assert_not_called()
