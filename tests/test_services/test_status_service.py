"""Testes do serviço centralizado de atualização de status (status_service).

Fase 2 (Marco 7): a persistência roda contra Postgres real (db_session) via
Chamado.atualizar_campos() — substitui o antigo mock de execute_with_retry/
db.collection("chamados").document(id).update(...). Testes que antes
inspecionavam o dict passado a execute_with_retry agora verificam o estado
real persistido via Chamado.get_by_id(chamado_id)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado
from app.services.status_service import _notificar_solicitante, atualizar_status_chamado

pytestmark = pytest.mark.usefixtures("db_session")

_ID_INEXISTENTE = 999999999


def _criar_chamado_real(status: str = "Aberto", **overrides) -> int:
    defaults = {
        "categoria": "Manutencao",
        "tipo_solicitacao": "Manutencao",
        "descricao": "Descrição de teste",
        "responsavel": "Responsável Teste",
        "solicitante_id": "sol1",
        "solicitante_nome": "Solicitante Teste",
        "status": status,
    }
    defaults.update(overrides)
    chamado = Chamado(**defaults)
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


def test_atualizar_status_chamado_nao_encontrado_retorna_erro():
    """Quando o chamado não existe no banco, retorna sucesso=False e erro 'Chamado não encontrado'."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Em Atendimento",
        usuario_id="u1",
        usuario_nome="Test",
    )
    assert resultado["sucesso"] is False
    assert resultado["erro"] == "Ticket not found"


def test_atualizar_status_chamado_com_data_chamado_atualiza_e_retorna_sucesso():
    """Com data_chamado informado, não busca no banco antes; atualiza e retorna sucesso."""
    chamado_id = _criar_chamado_real(status="Em Atendimento")
    with (
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
    assert resultado["sucesso"] is True
    assert resultado["novo_status"] == "Concluído"
    assert "mensagem" in resultado
    mock_hist.assert_called_once()
    mock_gamif.avaliar_resolucao_chamado.assert_called_once_with(
        "u1",
        {
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "numero_chamado": "CHM-001",
            "categoria": "Manutenção",
        },
    )
    assert Chamado.get_by_id(chamado_id).status == "Concluído"


def test_conclusao_reseta_flags_lembrete():
    """Ao ir para Concluído, flags de lembrete devem ser zeradas para novo ciclo de envio."""
    chamado_id = _criar_chamado_real(
        status="Em Atendimento",
        lembrete_confirmacao_1_enviado=True,
        lembrete_confirmacao_2_enviado=True,
    )
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "lembrete_confirmacao_1_enviado": True,
                "lembrete_confirmacao_2_enviado": True,
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    assert resultado["sucesso"] is True
    chamado_atualizado = Chamado.get_by_id(chamado_id)
    assert chamado_atualizado.lembrete_confirmacao_1_enviado is False
    assert chamado_atualizado.lembrete_confirmacao_2_enviado is False


def test_atualizar_status_chamado_mesmo_status_nao_chama_gamificacao():
    """Quando o status não muda (ex.: já era Concluído), não chama gamificação."""
    chamado_id = _criar_chamado_real(status="Concluído")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
    assert resultado["sucesso"] is True
    mock_gamif.avaliar_resolucao_chamado.assert_not_called()
    mock_gamif.avaliar_atendimento_inicial.assert_not_called()


def test_atualizar_status_invalido_retorna_erro():
    """Status inválido retorna sucesso=False com mensagem de erro."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="StatusInexistente",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={"status": "Aberto"},
    )
    assert resultado["sucesso"] is False
    assert "inválido" in resultado["erro"].lower() or "StatusInexistente" in resultado["erro"]


def test_atualizar_cancelado_sem_motivo_retorna_erro():
    """Cancelado sem motivo retorna sucesso=False."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Cancelado",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={"status": "Aberto"},
        motivo_cancelamento="",
    )
    assert resultado["sucesso"] is False
    assert "reason" in resultado["erro"].lower() or "cancel" in resultado["erro"].lower()


def test_atualizar_cancelado_com_motivo_retorna_sucesso():
    """Cancelado com motivo atualiza status e registra histórico do motivo."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Cancelado",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
            motivo_cancelamento="Não é mais necessário",
        )
    assert resultado["sucesso"] is True
    # Deve ter registrado histórico duas vezes: status + motivo
    assert mock_hist.call_count == 2
    assert Chamado.get_by_id(chamado_id).status == "Cancelado"


def test_atualizar_em_atendimento_chama_gamificacao_inicial():
    """Em Atendimento chama GamificationService.avaliar_atendimento_inicial."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService") as mock_gamif,
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True
    mock_gamif.avaliar_atendimento_inicial.assert_called_once_with("u1")


def test_saindo_de_concluido_para_aberto_reseta_confirmacao_solicitante():
    """Regressão: Concluído → Aberto (reabertura) limpa confirmacao_solicitante=None."""
    admin_mock = MagicMock()
    admin_mock.perfil = "admin"
    admin_mock.is_admin_or_above = True
    chamado_id = _criar_chamado_real(status="Concluído", confirmacao_solicitante="pendente")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service.Usuario.get_by_id", return_value=admin_mock),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "pendente",
                "solicitante_id": "s1",
            },
        )

    assert resultado["sucesso"] is True
    assert Chamado.get_by_id(chamado_id).confirmacao_solicitante is None


def test_concluido_para_em_atendimento_transicao_invalida():
    """Concluído → Em Atendimento deve ser transição inválida (TRANSICOES_VALIDAS)."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Em Atendimento",
        usuario_id="u1",
        usuario_nome="Test",
        data_chamado={
            "status": "Concluído",
            "confirmacao_solicitante": "pendente",
            "solicitante_id": "s1",
        },
    )
    assert resultado["sucesso"] is False
    assert "inválida" in resultado.get("erro", "").lower() or "Concluído" in resultado.get(
        "erro", ""
    )


def test_reabertura_admin_grava_historico_com_motivo():
    """Concluído → Aberto com motivo_reabertura grava entrada de reabertura no histórico."""
    admin_mock = MagicMock()
    admin_mock.perfil = "admin"
    admin_mock.is_admin_or_above = True
    chamado_id = _criar_chamado_real(status="Concluído", confirmacao_solicitante="confirmado")
    with (
        patch("app.services.status_service.Historico") as mock_hist,
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service.Usuario.get_by_id", return_value=admin_mock),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="admin1",
            usuario_nome="Admin",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "confirmado",
                "solicitante_id": "s1",
            },
            motivo_reabertura="Problema recorrente identificado",
        )
    assert resultado["sucesso"] is True
    # histórico: alteracao_status + reabertura (2 chamadas)
    assert mock_hist.call_count >= 2
    acoes = [call.kwargs.get("acao") for call in mock_hist.call_args_list]
    assert "reabertura" in acoes


def test_atualizar_status_excecao_retorna_falso():
    """Falha ao persistir (atualizar_campos retorna False) retorna sucesso=False."""
    chamado_id = _criar_chamado_real(status="Em Atendimento")
    with patch("app.models.Chamado.atualizar_campos", return_value=False):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Em Atendimento"},
        )
    assert resultado["sucesso"] is False
    assert "erro" in resultado


def test_busca_chamado_no_banco_quando_data_nao_fornecida():
    """Quando data_chamado=None, busca o chamado real via Chamado.get_by_id."""
    chamado_id = _criar_chamado_real(
        status="Aberto", solicitante_id="s1", numero_chamado="CHM-001", categoria="TI"
    )
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
        )
    assert resultado["sucesso"] is True
    assert Chamado.get_by_id(chamado_id).status == "Concluído"


def test_threading_notificacao_lanca_thread_com_app_context(app):
    """Dentro de app_context, a notificação inicia um Thread daemon e executa o closure."""
    chamado_id = _criar_chamado_real(status="Aberto")
    notif_closure_calls = []

    def fake_thread(target, daemon=True):
        notif_closure_calls.append(target)
        mock = MagicMock()
        mock.start = lambda: None
        return mock

    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.threading.Thread", side_effect=fake_thread),
        app.app_context(),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )

    assert len(notif_closure_calls) == 1
    # Execute the closure to cover lines inside _notif()
    with patch("app.services.status_service._notificar_solicitante"):
        notif_closure_calls[0]()


def test_notificar_solicitante_com_sid_envia_notificacao_e_webpush(app):
    """_notificar_solicitante com solicitante_id chama notificar_solicitante_status e webpush."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status") as mock_notif,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
        patch("app.services.notifications_inapp.criar_notificacao_solicitante"),
    ):
        app.config["APP_BASE_URL"] = "https://example.test"
        _notificar_solicitante(
            "ch1",
            {"solicitante_id": "s1", "numero_chamado": "CHM-001", "categoria": "TI"},
            "Em Atendimento",
        )
    mock_notif.assert_called_once()
    mock_webpush.assert_called_once()


def test_notificar_solicitante_sem_sid_nao_envia_webpush(app):
    """_notificar_solicitante sem solicitante_id chama notificar_solicitante_status mas não webpush."""
    with (
        app.app_context(),
        patch("app.services.status_service.notificar_solicitante_status") as mock_notif,
        patch("app.services.webpush_service.enviar_webpush_usuario") as mock_webpush,
    ):
        _notificar_solicitante(
            "ch1",
            {"solicitante_id": None, "numero_chamado": "CHM-001", "categoria": "TI"},
            "Em Atendimento",
        )
    mock_notif.assert_called_once()
    mock_webpush.assert_not_called()


def test_notificar_solicitante_excecao_nao_propaga(app):
    """_notificar_solicitante captura exceções internas sem propagar."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch(
            "app.services.status_service.notificar_solicitante_status",
            side_effect=Exception("smtp error"),
        ),
        patch("app.services.status_service.notificar_solicitante_confirmacao_pendente"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante"),
    ):
        _notificar_solicitante("ch1", {"solicitante_id": "s1"}, "Concluído")


# ── F-63: Validação de transição de status ─────────────────────────────────────


def test_atualizar_status_transicao_concluido_para_aberto_valida():
    """Concluído → Aberto é transição válida (reabertura administrativa)."""
    admin_mock = MagicMock()
    admin_mock.perfil = "admin"
    admin_mock.is_admin_or_above = True
    chamado_id = _criar_chamado_real(status="Concluído")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service.Usuario.get_by_id", return_value=admin_mock),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Concluído", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


def test_fallback_runtime_error_chama_ambas_notificacoes():
    """Lacuna E: except RuntimeError dispara _notificar_solicitante E _notificar_observadores_status."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service._notificar_solicitante") as mock_sol,
        patch("app.services.status_service._notificar_observadores_status") as mock_obs,
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True
    mock_sol.assert_called_once()
    mock_obs.assert_called_once()


def test_atualizar_status_mesmo_status_nao_rejeita_transicao():
    """F-63: Transição de um status para ele mesmo deve ser permitida."""
    chamado_id = _criar_chamado_real(status="Concluído")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Concluído", "solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


def test_atualizar_status_sem_status_anterior_nao_rejeita():
    """F-63: Sem status_anterior (campo ausente), transição não é bloqueada."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"solicitante_id": "s1"},
        )
    assert resultado["sucesso"] is True


def test_transicoes_validas_permite_fluxo_normal():
    """F-63: fluxo principal deve ser permitido; Concluído → Em Atendimento é inválido."""
    admin_mock = MagicMock()
    admin_mock.perfil = "admin"
    admin_mock.is_admin_or_above = True
    for status_ant, status_novo in [
        ("Aberto", "Em Atendimento"),
        ("Em Atendimento", "Concluído"),
        ("Concluído", "Aberto"),
        ("Aberto", "Cancelado"),
    ]:
        chamado_id = _criar_chamado_real(status=status_ant)
        with (
            patch("app.services.status_service.Historico"),
            patch("app.services.status_service._notificar_solicitante"),
            patch("app.services.status_service.GamificationService"),
            patch("app.services.status_service.Usuario.get_by_id", return_value=admin_mock),
        ):
            r = atualizar_status_chamado(
                chamado_id=chamado_id,
                novo_status=status_novo,
                usuario_id="u1",
                usuario_nome="Test",
                data_chamado={"status": status_ant, "solicitante_id": "s1"},
                motivo_cancelamento="motivo" if status_novo == "Cancelado" else None,
            )
        assert r["sucesso"] is True, f"Transição {status_ant} → {status_novo} deveria ser permitida"


# ---------------------------------------------------------------------------
# Lacuna 5 — Defesa em profundidade: freeze no service
# ---------------------------------------------------------------------------


def test_defesa_profundidade_supervisor_nivel2_cancelar_bloqueado():
    """Lacuna 5: supervisor não pode cancelar chamado confirmado (Nível 2) mesmo via service direto."""
    sup = MagicMock()
    sup.perfil = "supervisor"
    sup.is_admin_or_above = False

    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Cancelado",
        usuario_id="u1",
        usuario_nome="Supervisor",
        data_chamado={
            "status": "Concluído",
            "confirmacao_solicitante": "confirmado",
            "solicitante_id": "s1",
        },
        motivo_cancelamento="Motivo teste",
        usuario=sup,
    )
    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403


def test_defesa_profundidade_admin_nivel2_cancelar_bloqueado():
    """Lacuna 5: admin não pode cancelar chamado confirmado (Nível 2) — apenas reabrir."""
    admin = MagicMock()
    admin.perfil = "admin"
    admin.is_admin_or_above = True

    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Cancelado",
        usuario_id="admin1",
        usuario_nome="Admin",
        data_chamado={
            "status": "Concluído",
            "confirmacao_solicitante": "confirmado",
            "solicitante_id": "s1",
        },
        motivo_cancelamento="Motivo teste",
        usuario=admin,
    )
    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403


def test_defesa_profundidade_admin_nivel2_reabrir_permitido():
    """Lacuna 5: admin pode reabrir chamado confirmado (Nível 2) via service direto."""
    admin = MagicMock()
    admin.perfil = "admin"
    admin.is_admin_or_above = True
    chamado_id = _criar_chamado_real(status="Concluído", confirmacao_solicitante="confirmado")

    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="admin1",
            usuario_nome="Admin",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "confirmado",
                "solicitante_id": "s1",
            },
            motivo_reabertura="Problema recorrente",
            usuario=admin,
        )
    assert resultado["sucesso"] is True


def test_defesa_profundidade_usuario_none_nao_bloqueia_sem_db():
    """Lacuna 5: quando usuario=None e Usuario.get_by_id falha, validação é ignorada graciosamente."""
    chamado_id = _criar_chamado_real(status="Concluído", confirmacao_solicitante="pendente")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.Usuario.get_by_id",
            side_effect=Exception("no db"),
        ),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Aberto",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Concluído",
                "confirmacao_solicitante": "pendente",
                "solicitante_id": "s1",
            },
        )
    assert resultado["sucesso"] is True


# ---------------------------------------------------------------------------
# Fase 2 — Claim ao Em Atendimento + data_em_atendimento
# ---------------------------------------------------------------------------


def test_claim_atribui_owner_ao_em_atendimento():
    """Aberto sem owner → Em Atendimento atribui responsavel_id ao usuário logado."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 0,
            },
        )
    assert resultado["sucesso"] is True
    chamado_atualizado = Chamado.get_by_id(chamado_id)
    assert chamado_atualizado.responsavel_id == "id_julia"
    assert chamado_atualizado.data_em_atendimento is not None


def test_claim_nao_sobrescreve_owner_existente():
    """Aberto já com owner → Em Atendimento NÃO muda responsavel_id."""
    chamado_id = _criar_chamado_real(status="Aberto", responsavel_id="id_julia")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_matheus",
            usuario_nome="Matheus",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": "id_julia",
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 0,
            },
        )
    # responsavel_id não deve ser sobrescrito
    assert Chamado.get_by_id(chamado_id).responsavel_id != "id_matheus"


def test_escalonamento_nivel_nao_e_resetado_ao_assumir():
    """escalacao_nivel não deve ser resetado (nem incrementado) só por virar
    Em Atendimento — motor de escalonamento unificado continua de onde
    estava, só a cadência do próximo tick pode antecipar (ver
    test_claim_antecipa_proximo_tick_quando_escalando)."""
    chamado_id = _criar_chamado_real(status="Aberto", escalacao_nivel=2)
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 2,
            },
        )
    assert Chamado.get_by_id(chamado_id).escalacao_nivel == 2


def test_claim_antecipa_proximo_tick_quando_escalando():
    """Chamado escalando na cadência 'não assumido' (2h) — ao ser assumido, o
    próximo tick é antecipado pra cadência 'assumido' (1h) a partir de agora,
    sem esperar o tick de 2h originalmente agendado, sem resetar o nível."""
    chamado_id = _criar_chamado_real(status="Aberto", categoria="Manutenção", escalacao_nivel=1)
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 1,
            },
        )
    atualizado = Chamado.get_by_id(chamado_id)
    assert atualizado.escalacao_nivel == 1  # não reseta
    assert atualizado.escalacao_proximo_tick_em is not None
    delta = atualizado.escalacao_proximo_tick_em.replace(tzinfo=None) - datetime.now()
    assert timedelta(minutes=55) < delta < timedelta(minutes=65)  # ~60min, não 120min


def test_claim_nao_antecipa_tick_quando_nivel_zero():
    """Chamado ainda no nível 0 (nunca escalou) — claim não mexe em
    escalacao_proximo_tick_em, porque o alvo do nível 0 é sempre recalculado
    ao vivo pelo motor (ver calcular_deadline_inicial), não precisa de
    antecipação manual."""
    chamado_id = _criar_chamado_real(status="Aberto", categoria="Manutenção", escalacao_nivel=0)
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 0,
            },
        )
    assert Chamado.get_by_id(chamado_id).escalacao_proximo_tick_em is None


def test_claim_aog_nao_antecipa_tick_ja_usa_cadencia_assumido():
    """AOG já usa a cadência 'assumido' nas duas fases — claim não precisa
    antecipar escalacao_proximo_tick_em."""
    chamado_id = _criar_chamado_real(status="Aberto", categoria="AOG", escalacao_nivel=1)
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "AOG",
                "escalacao_nivel": 1,
            },
        )
    assert Chamado.get_by_id(chamado_id).escalacao_proximo_tick_em is None


def test_claim_atualiza_responsavel_nome():
    """Lacuna 5: claim (Aberto→Em Atendimento sem owner) deve gravar 'responsavel'."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia Ferreira",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 0,
            },
        )
    assert Chamado.get_by_id(chamado_id).responsavel == "Júlia Ferreira"


# ── Fase 4: bloqueio de conclusão com participantes pendentes ─────────────────


def test_owner_nao_conclui_com_participantes_pendentes():
    """Fase 4: atualizar_status Concluído falha quando há participantes pendentes."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Concluído",
        usuario_id="id_julia",
        usuario_nome="Julia",
        data_chamado={
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "participantes": [
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        },
    )
    assert resultado["sucesso"] is False
    assert "participant" in resultado["erro"].lower()


def test_owner_nao_conclui_com_participante_em_atendimento():
    """Fase 4: participante em_atendimento também bloqueia conclusão global."""
    resultado = atualizar_status_chamado(
        chamado_id=_ID_INEXISTENTE,
        novo_status="Concluído",
        usuario_id="id_julia",
        usuario_nome="Julia",
        data_chamado={
            "status": "Em Atendimento",
            "solicitante_id": "sol1",
            "participantes": [
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "em_atendimento",
                    "concluido_em": None,
                }
            ],
        },
    )
    assert resultado["sucesso"] is False


def test_owner_conclui_quando_todos_participantes_concluidos():
    """Fase 4: permite Concluído quando todos participantes têm status='concluido'."""
    chamado_id = _criar_chamado_real(status="Em Atendimento")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="id_julia",
            usuario_nome="Julia",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [
                    {
                        "supervisor_id": "id_pedro",
                        "area": "L",
                        "status": "concluido",
                        "concluido_em": "x",
                    }
                ],
            },
        )
    assert resultado["sucesso"] is True


def test_concluir_global_sem_participantes_continua_funcionando():
    """Fase 4 regressão: lista vazia de participantes não bloqueia conclusão."""
    chamado_id = _criar_chamado_real(status="Em Atendimento")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        resultado = atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    assert resultado["sucesso"] is True


def test_concluido_grava_confirmacao_solicitante_pendente():
    """Fase 4 regressão: ao Concluído (sem participantes pendentes), grava confirmacao_solicitante='pendente'."""
    chamado_id = _criar_chamado_real(status="Em Atendimento")
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Concluído",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={
                "status": "Em Atendimento",
                "solicitante_id": "sol1",
                "participantes": [],
            },
        )
    assert Chamado.get_by_id(chamado_id).confirmacao_solicitante == "pendente"


def test_claim_reseta_alertas_resolucao_mas_mantem_nivel_escalonamento():
    """Ao Aberto → Em Atendimento (claim): alerta_supervisor_50/80 são
    resetados (novo ciclo de aviso de resolução), mas escalacao_nivel NÃO —
    o motor de escalonamento unificado continua de onde estava."""
    chamado_id = _criar_chamado_real(
        status="Aberto",
        escalacao_nivel=2,
        alerta_supervisor_50_enviado=True,
        alerta_supervisor_80_enviado=True,
    )
    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=["id_julia"],
        ),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_julia",
            usuario_nome="Júlia",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
                "escalacao_nivel": 2,
                "alerta_supervisor_50_enviado": True,
                "alerta_supervisor_80_enviado": True,
            },
        )
    chamado_atualizado = Chamado.get_by_id(chamado_id)
    assert chamado_atualizado.escalacao_nivel == 2
    assert chamado_atualizado.alerta_supervisor_50_enviado is False
    assert chamado_atualizado.alerta_supervisor_80_enviado is False


def test_claim_data_em_atendimento_usa_config_sla_timezone():
    """Lacuna 6: claim deve usar Config.SLA_TIMEZONE, não timezone hardcoded.

    O Postgres normaliza timestamptz pro timezone da sessão ao ler de volta
    (não preserva o tzinfo original de insert) — por isso a asserção compara
    o instante absoluto (UTC), não o tzname literal."""
    chamado_id = _criar_chamado_real(status="Aberto")
    with (
        patch("app.services.status_service.Config") as mock_config,
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service.GamificationService"),
        patch(
            "app.services.status_service.calcular_supervisor_ids_com_acesso",
            return_value=[],
        ),
    ):
        mock_config.SLA_TIMEZONE = "UTC"
        antes = datetime.now(UTC)
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="id_user",
            usuario_nome="User",
            data_chamado={
                "status": "Aberto",
                "responsavel_id": None,
                "area": "Engenharia",
                "participantes": [],
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "Manutenção",
            },
        )
        depois = datetime.now(UTC)
    dt = Chamado.get_by_id(chamado_id).data_em_atendimento
    assert dt is not None
    assert antes <= dt.astimezone(UTC) <= depois


# ── Notificação in-app ao solicitante ─────────────────────────────────────────


def test_notificar_solicitante_em_atendimento_cria_notificacao_inapp(app):
    """_notificar_solicitante para 'Em Atendimento' chama criar_notificacao_solicitante com tipo correto."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )

    mock_inapp.assert_called_once()
    call_kwargs = mock_inapp.call_args.kwargs
    assert call_kwargs["tipo"] == "status_em_atendimento"
    assert call_kwargs["solicitante_id"] == "sol1"


def test_notificar_solicitante_concluido_cria_notificacao_inapp(app):
    """_notificar_solicitante para 'Concluído' chama criar_notificacao_solicitante com tipo correto."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_confirmacao_pendente"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Concluído",
        )

    mock_inapp.assert_called_once()
    call_kwargs = mock_inapp.call_args.kwargs
    assert call_kwargs["tipo"] == "status_concluido_confirmar"
    assert call_kwargs["solicitante_id"] == "sol1"


def test_notificar_solicitante_inapp_falha_nao_propaga(app):
    """Falha ao criar notificação in-app não propaga exceção (log warning apenas)."""
    with (
        app.app_context(),
        patch("app.services.status_service.Usuario.get_by_id", return_value=MagicMock()),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch(
            "app.services.notifications_inapp.criar_notificacao_solicitante",
            side_effect=Exception("banco fora do ar"),
        ),
    ):
        # Não deve lançar exceção
        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": "sol1",
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )


def test_notificar_solicitante_sem_sid_nao_cria_inapp(app):
    """_notificar_solicitante sem solicitante_id NÃO chama criar_notificacao_solicitante."""
    with (
        app.app_context(),
        patch("app.services.status_service.notificar_solicitante_status"),
        patch("app.services.webpush_service.enviar_webpush_usuario"),
        patch("app.services.notifications_inapp.criar_notificacao_solicitante") as mock_inapp,
    ):
        _notificar_solicitante(
            "ch1",
            {
                "solicitante_id": None,
                "numero_chamado": "CHM-001",
                "categoria": "TI",
            },
            "Em Atendimento",
        )

    mock_inapp.assert_not_called()


# ---------------------------------------------------------------------------
# Lacuna 3 — Fan-out de status para observadores
# ---------------------------------------------------------------------------


def test_notificacao_observers_disparada_em_background(app):
    """atualizar_status_chamado inclui _notificar_observadores_status na closure do thread."""
    chamado_id = _criar_chamado_real(status="Aberto")
    notif_closures = []

    def fake_thread(target, daemon=True):
        notif_closures.append(target)
        m = MagicMock()
        m.start = lambda: None
        return m

    with (
        patch("app.services.status_service.Historico"),
        patch("app.services.status_service.GamificationService"),
        patch("app.services.status_service.threading.Thread", side_effect=fake_thread),
        app.app_context(),
    ):
        atualizar_status_chamado(
            chamado_id=chamado_id,
            novo_status="Em Atendimento",
            usuario_id="u1",
            usuario_nome="Test",
            data_chamado={"status": "Aberto", "solicitante_id": "s1"},
        )

    assert len(notif_closures) == 1
    # Execute the closure — verifies _notificar_observadores_status is invoked inside it
    with (
        patch("app.services.status_service._notificar_solicitante"),
        patch("app.services.status_service._notificar_observadores_status") as mock_obs,
    ):
        notif_closures[0]()

    mock_obs.assert_called_once()
