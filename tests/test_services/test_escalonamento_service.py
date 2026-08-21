"""Testes de escalonamento_service: transferir_area, escalonar_colega,
incluir_participantes, concluir_minha_parte.

Previsão de atendimento saiu daqui — ver test_previsao_atendimento_service.py
(app/services/previsao_atendimento_service.py), que substitui a antiga
definir_previsao_atendimento por um fluxo de solicitação + aprovação do
gestor_setor.

Fase 2 (Marco 7): persistência real contra Postgres (fixture db_session) via
Chamado.salvar()/get_by_id()/atualizar_campos() — substitui o antigo mock de
db.collection("chamados").document(id).update(...) capturado num dict.
Historico/Usuario continuam mockados (Historico ainda é Firestore — Marco 8;
Usuario.get_supervisores_por_area é lookup independente do chamado em si).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")

_ID_INEXISTENTE = 999999999

# ── helpers de mock ───────────────────────────────────────────────────────────


def _usuario(uid, nome, perfil="supervisor", areas=None, nivel_gestao=None):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.perfil = perfil
    u.areas = areas or []
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.nivel_gestao = nivel_gestao
    return u


JULIA = _usuario("id_julia", "Julia Silva", areas=["Engenharia"])
MATHEUS_DEST = _usuario("id_matheus", "Matheus Costa", areas=["Planejamento"])
ADMIN = _usuario("id_admin", "Admin User", "admin")
NAO_OWNER = _usuario("id_nao_owner", "Outro Supervisor", areas=["Outra Area"])
# Ações de Escalonamento — decisão de escopo 2026-08-20: gestor_setor pode agir
# em chamado do time da própria área mesmo sem ser owner; gerente_producao
# (company-wide) continua 100% read-only.
GESTOR_SETOR_ENGENHARIA = _usuario(
    "id_gestor_setor",
    "Gestor Setor Engenharia",
    perfil="solicitante",
    areas=["Engenharia"],
    nivel_gestao="gestor_setor",
)
GESTOR_SETOR_OUTRA_AREA = _usuario(
    "id_gestor_setor_outra",
    "Gestor Setor Outra Área",
    perfil="solicitante",
    areas=["Outra Area"],
    nivel_gestao="gestor_setor",
)
GERENTE_PRODUCAO = _usuario(
    "id_gerente_producao",
    "Gerente Produção",
    perfil="solicitante",
    areas=[],
    nivel_gestao="gerente_producao",
)


def _criar_chamado_real(
    area="Engenharia",
    responsavel_id="id_julia",
    responsavel="Julia Silva",
    participantes=None,
    status="Em Atendimento",
    categoria="Manutencao",
) -> int:
    chamado = Chamado(
        categoria=categoria,
        tipo_solicitacao="Corretiva",
        descricao="Descrição teste",
        responsavel=responsavel,
        responsavel_id=responsavel_id,
        area=area,
        status=status,
        participantes=participantes or [],
    )
    chamado_id = chamado.salvar()
    assert chamado_id is not None
    return chamado_id


def _sup_mock(uid, nome, areas=None):
    s = MagicMock()
    s.id = uid
    s.nome = nome
    s.areas = areas or []
    return s


# ── Task 3.1: transferir_area ─────────────────────────────────────────────────


class TestTransferirArea:
    """Testes da função transferir_area."""

    def test_transferir_area_muda_area_e_owner(self):
        """Transferência muda area e responsavel_id no Postgres."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area(
                chamado_id, "Planejamento", "id_matheus", "Precisa de PPCP", JULIA
            )

        assert resultado["sucesso"] is True
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.area == "Planejamento"
        assert atualizado.responsavel_id == "id_matheus"

    def test_transferir_area_ex_owner_perde_acesso(self):
        """Após transferência, ex-owner (julia, área Engenharia) não pode mais ver o chamado."""
        from app.services.escalonamento_service import transferir_area
        from app.services.permissions import usuario_pode_ver_chamado

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", JULIA)

        chamado_atualizado = Chamado.get_by_id(chamado_id)
        julia_user = _usuario("id_julia", "Julia", areas=["Engenharia"])
        assert usuario_pode_ver_chamado(julia_user, chamado_atualizado) is False

    def test_transferir_area_novo_owner_ganha_acesso(self):
        """Após transferência, novo owner (matheus, área Planejamento) passa a ver o chamado."""
        from app.services.escalonamento_service import transferir_area
        from app.services.permissions import usuario_pode_ver_chamado

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", JULIA)

        chamado_atualizado = Chamado.get_by_id(chamado_id)
        matheus_user = _usuario("id_matheus", "Matheus", areas=["Planejamento"])
        assert usuario_pode_ver_chamado(matheus_user, chamado_atualizado) is True

    def test_transferir_area_reseta_confirmacao_de_leitura(self):
        """Transferir área muda o responsável — a marcação de "visualizado"
        é por responsável ATUAL, não pode sobreviver à troca (achado a
        pedido do usuário, 2026-08-18: sem isso o solicitante via
        "visualizado" com o timestamp de quem já não é mais o responsável)."""
        from datetime import UTC, datetime

        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        Chamado.get_by_id(chamado_id).atualizar_campos(
            visualizado_pelo_responsavel_em=datetime.now(UTC)
        )
        assert Chamado.get_by_id(chamado_id).visualizado_pelo_responsavel_em is not None
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", JULIA)

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).visualizado_pelo_responsavel_em is None

    def test_anti_orfao_supervisor_id_obrigatorio(self):
        """supervisor_id=None deve levantar ValueError (invariante anti-órfão)."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="supervisor_id obrigatório"):
            transferir_area(_ID_INEXISTENTE, "Planejamento", None, "motivo", JULIA)

    def test_transferir_area_registra_historico(self):
        """Transferência deve registrar histórico com acao='transferencia_area'."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            mock_hist_cls.return_value = hist_instancia
            transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo válido", JULIA)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "transferencia_area"
        assert kwargs.get("campo_alterado") == "area"
        assert kwargs.get("valor_anterior") == "Engenharia"
        assert kwargs.get("valor_novo") == "Planejamento"
        assert "Planejamento" in (kwargs.get("detalhe") or "")
        hist_instancia.save.assert_called_once()

    def test_transferir_area_recalcula_supervisor_ids_com_acesso(self):
        """supervisor_ids_com_acesso deve ser recalculado após transferência."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            mock_calc.return_value = ["id_matheus"]
            transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", JULIA)

        mock_calc.assert_called_once_with("Planejamento", "id_matheus", [])
        assert Chamado.get_by_id(chamado_id).supervisor_ids_com_acesso == ["id_matheus"]

    def test_transferir_area_nao_owner_retorna_erro(self):
        """Supervisor que não é owner não pode transferir — retorna sucesso=False."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", NAO_OWNER)

        assert resultado["sucesso"] is False
        assert "permission" in resultado["erro"].lower() or "access" in resultado["erro"].lower()

    def test_transferir_area_gestor_setor_da_area_pode_transferir_mesmo_sem_ser_owner(self):
        """Ações de Escalonamento (2026-08-20): gestor_setor da própria área pode
        transferir chamado do time mesmo sem ser owner."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area(
                chamado_id, "Planejamento", "id_matheus", "motivo", GESTOR_SETOR_ENGENHARIA
            )

        assert resultado["sucesso"] is True

    def test_transferir_area_gestor_setor_fora_da_area_continua_bloqueado(self):
        """gestor_setor de outra área não pode transferir chamado que não é do seu time."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = transferir_area(
            chamado_id, "Planejamento", "id_matheus", "motivo", GESTOR_SETOR_OUTRA_AREA
        )

        assert resultado["sucesso"] is False

    def test_transferir_area_gerente_producao_continua_bloqueado(self):
        """gerente_producao (company-wide) continua 100% read-only — não entra
        na exceção de gestor_setor."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = transferir_area(
            chamado_id, "Planejamento", "id_matheus", "motivo", GERENTE_PRODUCAO
        )

        assert resultado["sucesso"] is False

    def test_transferir_area_motivo_vazio_lanca_erro(self):
        """Motivo vazio (após strip) deve levantar ValueError."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="motivo"):
            transferir_area(_ID_INEXISTENTE, "Planejamento", "id_matheus", "   ", JULIA)

    def test_transferir_area_area_vazia_lanca_erro(self):
        """Área vazia deve levantar ValueError."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="área"):
            transferir_area(_ID_INEXISTENTE, "", "id_matheus", "motivo", JULIA)

    def test_transferir_area_chamado_nao_encontrado(self):
        """Chamado inexistente retorna sucesso=False."""
        from app.services.escalonamento_service import transferir_area

        resultado = transferir_area(_ID_INEXISTENTE, "Planejamento", "id_matheus", "motivo", JULIA)

        assert resultado["sucesso"] is False
        assert "not found" in resultado["erro"].lower()

    def test_transferir_area_supervisor_destino_invalido(self):
        """Supervisor destino que não pertence à área destino retorna erro."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        with patch("app.services.escalonamento_service.Usuario") as mock_usuario:
            # Lista vazia — supervisor_id não está na área destino
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = transferir_area(
                chamado_id, "Planejamento", "id_desconhecido", "motivo", JULIA
            )

        assert resultado["sucesso"] is False
        assert "supervisor" in resultado["erro"].lower() or "área" in resultado["erro"].lower()

    def test_transferir_area_admin_pode_transferir(self):
        """Admin pode transferir mesmo sem ser o owner do chamado."""
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area(chamado_id, "Planejamento", "id_matheus", "motivo", ADMIN)

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).area == "Planejamento"

    def test_transferir_area_com_usuario_real_nao_fecha_sessao_compartilhada(self):
        """Regressão (achado ao vivo em produção, 2026-08-21): Usuario.get_supervisores_por_area
        abre sua própria SessionLocal() de dentro do Chamado.editar_com_lock já aberto — como
        SessionLocal é scoped_session (thread-local), sair do bloco interno fechava a sessão
        compartilhada e o editar_com_lock quebrava com
        `InvalidRequestError: Can't operate on closed transaction` ao sincronizar
        participantes/observadores → 500 sempre. Este teste NÃO mocka Usuario — precisa
        exercitar a query real (`Usuario.get_supervisores_por_area`) pra reproduzir."""
        from app.models_usuario import Usuario
        from app.services.escalonamento_service import transferir_area

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        Usuario(
            id="id_matheus_real",
            email="matheus.real@dtx.aero",
            nome="Matheus Costa",
            perfil="supervisor",
            areas=["Planejamento"],
        ).save()

        with patch("app.services.escalonamento_service.Historico"):
            resultado = transferir_area(
                chamado_id, "Planejamento", "id_matheus_real", "motivo real", JULIA
            )

        assert resultado["sucesso"] is True
        atualizado = Chamado.get_by_id(chamado_id)
        assert atualizado.area == "Planejamento"
        assert atualizado.responsavel_id == "id_matheus_real"


# ── Task 3.2: escalonar_colega ────────────────────────────────────────────────


class TestEscalonarColega:
    """Testes da função escalonar_colega."""

    def test_escalonar_colega_troca_responsavel(self):
        """Escalonamento troca responsavel_id mantendo a área."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            resultado = escalonar_colega(
                chamado_id, "id_matheus", "Matheus tem especialidade X", JULIA
            )

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).responsavel_id == "id_matheus"

    def test_escalonar_colega_reseta_confirmacao_de_leitura(self):
        """Escalonar pra colega troca o responsável — a marcação de
        "visualizado" é por responsável ATUAL, não pode sobreviver à troca
        (achado a pedido do usuário, 2026-08-18)."""
        from datetime import UTC, datetime

        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        Chamado.get_by_id(chamado_id).atualizar_campos(
            visualizado_pelo_responsavel_em=datetime.now(UTC)
        )
        assert Chamado.get_by_id(chamado_id).visualizado_pelo_responsavel_em is not None
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            resultado = escalonar_colega(chamado_id, "id_matheus", "motivo", JULIA)

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).visualizado_pelo_responsavel_em is None

    def test_escalonar_colega_area_permanece(self):
        """Escalonamento de colega não altera a área do chamado."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            escalonar_colega(chamado_id, "id_matheus", "motivo", JULIA)

        assert Chamado.get_by_id(chamado_id).area == "Engenharia"

    def test_escalonar_colega_registra_historico(self):
        """Escalonamento deve registrar histórico com acao='escalonamento_colega'."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            mock_hist_cls.return_value = hist_instancia
            escalonar_colega(chamado_id, "id_matheus", "motivo", JULIA)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "escalonamento_colega"
        assert kwargs.get("campo_alterado") == "responsavel_id"
        hist_instancia.save.assert_called_once()

    def test_escalonar_colega_motivo_obrigatorio(self):
        """Motivo vazio deve levantar ValueError."""
        from app.services.escalonamento_service import escalonar_colega

        with pytest.raises(ValueError, match="motivo"):
            escalonar_colega(_ID_INEXISTENTE, "id_matheus", "", JULIA)

    def test_escalonar_colega_recalcula_supervisor_ids_com_acesso(self):
        """supervisor_ids_com_acesso deve ser recalculado após escalonamento."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            mock_calc.return_value = ["id_matheus"]
            escalonar_colega(chamado_id, "id_matheus", "motivo", JULIA)

        mock_calc.assert_called_once_with("Engenharia", "id_matheus", [])
        assert Chamado.get_by_id(chamado_id).supervisor_ids_com_acesso == ["id_matheus"]

    def test_escalonar_colega_colega_outra_area_invalido(self):
        """Supervisor destino de área diferente retorna erro."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        with patch("app.services.escalonamento_service.Usuario") as mock_usuario:
            # Colega não está na área (lista vazia)
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = escalonar_colega(chamado_id, "id_outro_area", "motivo", JULIA)

        assert resultado["sucesso"] is False
        assert "área" in resultado["erro"].lower() or "supervisor" in resultado["erro"].lower()

    def test_escalonar_colega_destino_diferente_do_atual(self):
        """Destino igual ao owner atual retorna erro."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = escalonar_colega(chamado_id, "id_julia", "motivo", JULIA)

        assert resultado["sucesso"] is False
        assert (
            "target" in resultado["erro"].lower()
            or "same" in resultado["erro"].lower()
            or "current" in resultado["erro"].lower()
        )

    def test_escalonar_colega_nao_owner_retorna_erro(self):
        """Supervisor que não é owner não pode escalonar."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = escalonar_colega(chamado_id, "id_matheus", "motivo", NAO_OWNER)

        assert resultado["sucesso"] is False

    def test_escalonar_colega_gestor_setor_da_area_pode_escalonar_mesmo_sem_ser_owner(self):
        """Ações de Escalonamento (2026-08-20): gestor_setor da própria área pode
        escalonar chamado do time mesmo sem ser owner."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch("app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            resultado = escalonar_colega(
                chamado_id, "id_matheus", "motivo", GESTOR_SETOR_ENGENHARIA
            )

        assert resultado["sucesso"] is True

    def test_escalonar_colega_gerente_producao_continua_bloqueado(self):
        """gerente_producao (company-wide) continua 100% read-only."""
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")

        resultado = escalonar_colega(chamado_id, "id_matheus", "motivo", GERENTE_PRODUCAO)

        assert resultado["sucesso"] is False

    def test_escalonar_colega_supervisor_id_obrigatorio(self):
        """supervisor_id=None deve levantar ValueError."""
        from app.services.escalonamento_service import escalonar_colega

        with pytest.raises(ValueError, match="supervisor_id"):
            escalonar_colega(_ID_INEXISTENTE, None, "motivo", JULIA)

    def test_escalonar_colega_com_usuario_real_nao_fecha_sessao_compartilhada(self):
        """Regressão (achado ao vivo em produção, 2026-08-21) — ver docstring
        equivalente em TestTransferirArea. Este teste NÃO mocka Usuario."""
        from app.models_usuario import Usuario
        from app.services.escalonamento_service import escalonar_colega

        chamado_id = _criar_chamado_real(area="Engenharia", responsavel_id="id_julia")
        Usuario(
            id="id_matheus_real",
            email="matheus.real@dtx.aero",
            nome="Matheus Costa",
            perfil="supervisor",
            areas=["Engenharia"],
        ).save()

        with patch("app.services.escalonamento_service.Historico"):
            resultado = escalonar_colega(chamado_id, "id_matheus_real", "motivo real", JULIA)

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).responsavel_id == "id_matheus_real"


# ── Task 4.2: incluir_participantes e concluir_minha_parte ───────────────────

PEDRO = _usuario("id_pedro", "Pedro Alves", areas=["Logistica"])
FERNANDA = _usuario("id_fernanda", "Fernanda Lima", areas=["Engenharia"])
SOLICITANTE = _usuario("id_sol", "Sol User", "solicitante", areas=[])


class TestEditarComLockConcorrencia:
    """Regressão (auditoria 2026-08-05): salvar() fazia delete-all+reinsert de
    participantes/observadores sem lock — duas mutações concorrentes no mesmo
    chamado (ex: incluir_participantes e concluir_minha_parte) podiam sobrescrever
    uma à outra silenciosamente. editar_com_lock() trava a linha do chamado
    (SELECT ... FOR UPDATE) durante toda a janela leitura→escrita."""

    def test_editar_com_lock_emite_select_for_update(self, db_session):
        from sqlalchemy import event

        chamado_id = _criar_chamado_real()
        statements = []
        connection = db_session.get_bind()

        def _capturar(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(connection, "before_cursor_execute", _capturar)
        try:
            with Chamado.editar_com_lock(chamado_id) as chamado:
                assert chamado is not None
                assert chamado.id == chamado_id
        finally:
            event.remove(connection, "before_cursor_execute", _capturar)

        selects_chamados = [
            s for s in statements if "FROM chamados" in s and "chamados_participantes" not in s
        ]
        assert selects_chamados, "esperava pelo menos um SELECT em chamados"
        assert any("FOR UPDATE" in s.upper() for s in selects_chamados), (
            "editar_com_lock deve travar a linha com SELECT ... FOR UPDATE"
        )

    def test_editar_com_lock_chamado_inexistente_retorna_none(self):
        with Chamado.editar_com_lock(_ID_INEXISTENTE) as chamado:
            assert chamado is None

    def test_editar_com_lock_persiste_mutacao_de_participantes(self):
        chamado_id = _criar_chamado_real(
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ]
        )
        with Chamado.editar_com_lock(chamado_id) as chamado:
            chamado.participantes = [
                *chamado.participantes,
                {
                    "supervisor_id": "id_fernanda",
                    "area": "Engenharia",
                    "status": "pendente",
                    "concluido_em": None,
                },
            ]

        recarregado = Chamado.get_by_id(chamado_id)
        ids = {p["supervisor_id"] for p in recarregado.participantes}
        assert ids == {"id_pedro", "id_fernanda"}

    def test_editar_com_lock_nao_persiste_mutacao_se_excecao(self):
        chamado_id = _criar_chamado_real(
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ]
        )
        with pytest.raises(RuntimeError), Chamado.editar_com_lock(chamado_id) as chamado:
            chamado.participantes = []
            raise RuntimeError("simula falha no meio da operação")

        recarregado = Chamado.get_by_id(chamado_id)
        assert len(recarregado.participantes) == 1


class TestIncluirParticipantes:
    """Testes da função incluir_participantes."""

    def test_incluir_participantes_adiciona(self):
        """Adiciona participante novo à lista."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        assert resultado["sucesso"] is True
        participantes = Chamado.get_by_id(chamado_id).participantes
        assert any(p["supervisor_id"] == "id_pedro" for p in participantes)

    def test_incluir_participantes_status_pendente(self):
        """Participante incluído recebe status='pendente'."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        participantes = Chamado.get_by_id(chamado_id).participantes
        novo_p = next(p for p in participantes if p["supervisor_id"] == "id_pedro")
        assert novo_p["status"] == "pendente"
        assert novo_p["concluido_em"] is None

    def test_incluir_participantes_recalcula_supervisor_ids_com_acesso(self):
        """Após incluir participante, supervisor_ids_com_acesso é recalculado."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            mock_calc.return_value = ["id_julia", "id_pedro"]
            incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        mock_calc.assert_called_once()
        assert Chamado.get_by_id(chamado_id).supervisor_ids_com_acesso == [
            "id_julia",
            "id_pedro",
        ]

    def test_incluir_participantes_nao_duplica_supervisor(self):
        """Não inclui supervisor_id já presente em participantes."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        # Todos duplicados → erro semântico (nenhum novo adicionado)
        assert resultado["sucesso"] is False
        assert "no new participants" in resultado["erro"].lower()

    def test_incluir_participantes_apenas_owner_ou_admin(self):
        """Supervisor que não é owner não pode incluir participantes."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])

        resultado = incluir_participantes(
            chamado_id,
            [{"supervisor_id": "id_pedro", "area": "Logistica"}],
            NAO_OWNER,
        )

        assert resultado["sucesso"] is False
        assert "permission" in resultado["erro"].lower()

    def test_incluir_participantes_gestor_setor_da_area_pode_incluir_mesmo_sem_ser_owner(self):
        """Ações de Escalonamento (2026-08-20): gestor_setor da própria área pode
        incluir participantes em chamado do time mesmo sem ser owner."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(
            area="Engenharia", responsavel_id="id_julia", participantes=[]
        )
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                GESTOR_SETOR_ENGENHARIA,
            )

        assert resultado["sucesso"] is True

    def test_incluir_participantes_gerente_producao_continua_bloqueado(self):
        """gerente_producao (company-wide) continua 100% read-only."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(
            area="Engenharia", responsavel_id="id_julia", participantes=[]
        )

        resultado = incluir_participantes(
            chamado_id,
            [{"supervisor_id": "id_pedro", "area": "Logistica"}],
            GERENTE_PRODUCAO,
        )

        assert resultado["sucesso"] is False

    def test_incluir_participantes_lista_vazia_retorna_erro(self):
        """Lista vazia de participantes retorna erro."""
        from app.services.escalonamento_service import incluir_participantes

        resultado = incluir_participantes(_ID_INEXISTENTE, [], JULIA)

        assert resultado["sucesso"] is False

    def test_incluir_participantes_nao_inclui_owner(self):
        """Owner não pode ser adicionado como participante."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_julia = _sup_mock("id_julia", "Julia Silva", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_julia]
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_julia", "area": "Engenharia"}],
                JULIA,
            )

        assert resultado["sucesso"] is False
        assert "owner" in resultado["erro"].lower() or "responsável" in resultado["erro"].lower()

    def test_incluir_participantes_admin_pode_incluir(self):
        """Admin pode incluir participantes mesmo sem ser owner."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                ADMIN,
            )

        assert resultado["sucesso"] is True

    def test_incluir_participantes_supervisor_invalido_na_area(self):
        """supervisor_id que não pertence à área informada retorna erro."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
        ):
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_desconhecido", "area": "Logistica"}],
                JULIA,
            )

        assert resultado["sucesso"] is False

    def test_incluir_participantes_registra_historico(self):
        """incluir_participantes registra histórico com acao='inclusao_participantes'."""
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            mock_hist_cls.return_value = hist_instancia
            incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "inclusao_participantes"
        hist_instancia.save.assert_called_once()

    def test_incluir_participantes_com_usuario_real_nao_fecha_sessao_compartilhada(self):
        """Regressão (achado ao vivo em produção, 2026-08-21) — ver docstring
        equivalente em TestTransferirArea. Este teste NÃO mocka Usuario."""
        from app.models_usuario import Usuario
        from app.services.escalonamento_service import incluir_participantes

        chamado_id = _criar_chamado_real(responsavel_id="id_julia", participantes=[])
        Usuario(
            id="id_pedro_real",
            email="pedro.real@dtx.aero",
            nome="Pedro Alves",
            perfil="supervisor",
            areas=["Logistica"],
        ).save()

        with patch("app.services.escalonamento_service.Historico"):
            resultado = incluir_participantes(
                chamado_id,
                [{"supervisor_id": "id_pedro_real", "area": "Logistica"}],
                JULIA,
            )

        assert resultado["sucesso"] is True
        participantes = Chamado.get_by_id(chamado_id).participantes
        assert any(p["supervisor_id"] == "id_pedro_real" for p in participantes)


class TestConcluirMinhaParte:
    """Testes da função concluir_minha_parte."""

    def test_concluir_minha_parte_muda_status(self):
        """concluir_minha_parte atualiza status do participante para 'concluido'."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )

        with patch("app.services.escalonamento_service.Historico"):
            resultado = concluir_minha_parte(chamado_id, PEDRO)

        assert resultado["sucesso"] is True
        participantes = Chamado.get_by_id(chamado_id).participantes
        p = next(p for p in participantes if p["supervisor_id"] == "id_pedro")
        assert p["status"] == "concluido"

    def test_concluir_minha_parte_grava_concluido_em(self):
        """concluir_minha_parte grava concluido_em com datetime."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "em_atendimento",
                    "concluido_em": None,
                }
            ],
        )

        with patch("app.services.escalonamento_service.Historico"):
            concluir_minha_parte(chamado_id, PEDRO)

        participantes = Chamado.get_by_id(chamado_id).participantes
        p = next(p for p in participantes if p["supervisor_id"] == "id_pedro")
        assert p["concluido_em"] is not None

    def test_concluir_minha_parte_nao_participante_retorna_erro(self):
        """Usuário que não é participante recebe erro."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )

        resultado = concluir_minha_parte(chamado_id, FERNANDA)

        assert resultado["sucesso"] is False
        assert "participant" in resultado["erro"].lower()

    def test_concluir_minha_parte_ja_concluido_retorna_erro(self):
        """Participante que já concluiu não pode concluir novamente."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "concluido",
                    "concluido_em": "2024-01-01",
                }
            ],
        )

        resultado = concluir_minha_parte(chamado_id, PEDRO)

        assert resultado["sucesso"] is False

    def test_concluir_minha_parte_registra_historico(self):
        """concluir_minha_parte registra histórico."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )
        hist_instancia = MagicMock()

        with patch("app.services.escalonamento_service.Historico") as mock_hist_cls:
            mock_hist_cls.return_value = hist_instancia
            concluir_minha_parte(chamado_id, PEDRO)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "conclusao_parte_participante"
        hist_instancia.save.assert_called_once()

    def test_concluir_minha_parte_nao_altera_data_em_atendimento(self):
        """Fase 7 regressão: concluir_minha_parte NÃO deve alterar data_em_atendimento.

        Garante que o deadline de resolução (calculado a partir de data_em_atendimento)
        não seja alterado acidentalmente ao marcar parte como concluída.
        """
        from app.services.escalonamento_service import concluir_minha_parte

        chamado_id = _criar_chamado_real(
            responsavel_id="id_julia",
            participantes=[
                {
                    "supervisor_id": "id_pedro",
                    "area": "Logistica",
                    "status": "pendente",
                    "concluido_em": None,
                }
            ],
        )
        antes = Chamado.get_by_id(chamado_id).data_em_atendimento

        with patch("app.services.escalonamento_service.Historico"):
            resultado = concluir_minha_parte(chamado_id, PEDRO)

        assert resultado["sucesso"] is True
        assert Chamado.get_by_id(chamado_id).data_em_atendimento == antes


class TestPodeConcluirGlobal:
    """Testes dos helpers pode_concluir_global e todos_participantes_concluidos."""

    def test_pode_concluir_sem_participantes(self):
        from app.services.escalonamento_service import pode_concluir_global

        c = Chamado.from_dict(
            {
                "categoria": "TI",
                "tipo_solicitacao": "S",
                "descricao": "D",
                "responsavel": "R",
                "participantes": [],
            }
        )
        assert pode_concluir_global(c) is True

    def test_pode_concluir_todos_concluidos(self):
        from app.services.escalonamento_service import pode_concluir_global

        c = Chamado.from_dict(
            {
                "categoria": "TI",
                "tipo_solicitacao": "S",
                "descricao": "D",
                "responsavel": "R",
                "participantes": [
                    {
                        "supervisor_id": "id_pedro",
                        "area": "L",
                        "status": "concluido",
                        "concluido_em": "x",
                    },
                    {
                        "supervisor_id": "id_fernanda",
                        "area": "E",
                        "status": "concluido",
                        "concluido_em": "y",
                    },
                ],
            }
        )
        assert pode_concluir_global(c) is True

    def test_nao_pode_concluir_com_pendente(self):
        from app.services.escalonamento_service import pode_concluir_global

        c = Chamado.from_dict(
            {
                "categoria": "TI",
                "tipo_solicitacao": "S",
                "descricao": "D",
                "responsavel": "R",
                "participantes": [
                    {
                        "supervisor_id": "id_pedro",
                        "area": "L",
                        "status": "concluido",
                        "concluido_em": "x",
                    },
                    {
                        "supervisor_id": "id_fernanda",
                        "area": "E",
                        "status": "pendente",
                        "concluido_em": None,
                    },
                ],
            }
        )
        assert pode_concluir_global(c) is False
