"""Testes TDD para escalonamento_service: transferir_area e escalonar_colega.

Ordem TDD: estes testes são escritos ANTES da implementação do serviço.
Mock strategy: patch('app.services.escalonamento_service.db') conforme padrão do projeto.
"""

from unittest.mock import MagicMock, patch

import pytest

# ── helpers de mock ───────────────────────────────────────────────────────────


def _usuario(uid, nome, perfil="supervisor", areas=None):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.perfil = perfil
    u.areas = areas or []
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    return u


JULIA = _usuario("id_julia", "Julia Silva", areas=["Engenharia"])
MATHEUS_DEST = _usuario("id_matheus", "Matheus Costa", areas=["Planejamento"])
ADMIN = _usuario("id_admin", "Admin User", "admin")
NAO_OWNER = _usuario("id_nao_owner", "Outro Supervisor", areas=["Outra Area"])


def _chamado_dict(
    area="Engenharia",
    responsavel_id="id_julia",
    responsavel="Julia Silva",
    participantes=None,
    status="Em Atendimento",
):
    return {
        "area": area,
        "responsavel_id": responsavel_id,
        "responsavel": responsavel,
        "motivo_ultima_escalacao": None,
        "supervisor_ids_com_acesso": [responsavel_id] if responsavel_id else [],
        "participantes": participantes or [],
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "descricao": "Descrição teste",
        "status": status,
    }


def _make_db_mock(chamado_data=None, doc_exists=True):
    """Retorna (mock_db, dict_atualizado) onde dict_atualizado captura o .update()."""
    mock_db = MagicMock()
    mock_doc = MagicMock()
    mock_doc.exists = doc_exists
    mock_doc.to_dict.return_value = chamado_data or _chamado_dict()
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    updated = {}
    mock_db.collection.return_value.document.return_value.update.side_effect = (
        lambda d: updated.update(d)
    )

    return mock_db, updated


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
        """Transferência muda area e responsavel_id no Firestore."""
        from app.services.escalonamento_service import transferir_area

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area(
                "id_chamado", "Planejamento", "id_matheus", "Precisa de PPCP", JULIA
            )

        assert resultado["sucesso"] is True
        assert updated["area"] == "Planejamento"
        assert updated["responsavel_id"] == "id_matheus"

    def test_transferir_area_ex_owner_perde_acesso(self):
        """Após transferência, ex-owner (julia, área Engenharia) não pode mais ver o chamado."""
        from app.models import Chamado
        from app.services.escalonamento_service import transferir_area
        from app.services.permissions import usuario_pode_ver_chamado

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", JULIA)

        # Constrói chamado atualizado com o que foi gravado
        chamado_dict_atualizado = {**_chamado_dict(), **updated}
        chamado_atualizado = Chamado.from_dict(chamado_dict_atualizado, "id_chamado")

        julia_user = _usuario("id_julia", "Julia", areas=["Engenharia"])
        assert usuario_pode_ver_chamado(julia_user, chamado_atualizado) is False

    def test_transferir_area_novo_owner_ganha_acesso(self):
        """Após transferência, novo owner (matheus, área Planejamento) passa a ver o chamado."""
        from app.models import Chamado
        from app.services.escalonamento_service import transferir_area
        from app.services.permissions import usuario_pode_ver_chamado

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", JULIA)

        chamado_dict_atualizado = {**_chamado_dict(), **updated}
        chamado_atualizado = Chamado.from_dict(chamado_dict_atualizado, "id_chamado")

        matheus_user = _usuario("id_matheus", "Matheus", areas=["Planejamento"])
        assert usuario_pode_ver_chamado(matheus_user, chamado_atualizado) is True

    def test_anti_orfao_supervisor_id_obrigatorio(self):
        """supervisor_id=None deve levantar ValueError (invariante anti-órfão)."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="supervisor_id obrigatório"):
            transferir_area("id_chamado", "Planejamento", None, "motivo", JULIA)

    def test_transferir_area_registra_historico(self):
        """Transferência deve registrar histórico com acao='transferencia_area'."""
        from app.services.escalonamento_service import transferir_area

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            mock_hist_cls.return_value = hist_instancia
            transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo válido", JULIA)

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

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            mock_calc.return_value = ["id_matheus"]
            transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", JULIA)

        mock_calc.assert_called_once_with("Planejamento", "id_matheus", [])
        assert updated["supervisor_ids_com_acesso"] == ["id_matheus"]

    def test_transferir_area_nao_owner_retorna_erro(self):
        """Supervisor que não é owner não pode transferir — retorna sucesso=False."""
        from app.services.escalonamento_service import transferir_area

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = transferir_area(
                "id_chamado", "Planejamento", "id_matheus", "motivo", NAO_OWNER
            )

        assert resultado["sucesso"] is False
        assert "permission" in resultado["erro"].lower() or "access" in resultado["erro"].lower()

    def test_transferir_area_motivo_vazio_lanca_erro(self):
        """Motivo vazio (após strip) deve levantar ValueError."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="motivo"):
            transferir_area("id_chamado", "Planejamento", "id_matheus", "   ", JULIA)

    def test_transferir_area_area_vazia_lanca_erro(self):
        """Área vazia deve levantar ValueError."""
        from app.services.escalonamento_service import transferir_area

        with pytest.raises(ValueError, match="área"):
            transferir_area("id_chamado", "", "id_matheus", "motivo", JULIA)

    def test_transferir_area_chamado_nao_encontrado(self):
        """Chamado inexistente retorna sucesso=False."""
        from app.services.escalonamento_service import transferir_area

        mock_db, _ = _make_db_mock(doc_exists=False)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = transferir_area(
                "id_inexistente", "Planejamento", "id_matheus", "motivo", JULIA
            )

        assert resultado["sucesso"] is False
        assert "not found" in resultado["erro"].lower()

    def test_transferir_area_supervisor_destino_invalido(self):
        """Supervisor destino que não pertence à área destino retorna erro."""
        from app.services.escalonamento_service import transferir_area

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
        ):
            # Lista vazia — supervisor_id não está na área destino
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = transferir_area(
                "id_chamado", "Planejamento", "id_desconhecido", "motivo", JULIA
            )

        assert resultado["sucesso"] is False
        assert "supervisor" in resultado["erro"].lower() or "área" in resultado["erro"].lower()

    def test_transferir_area_admin_pode_transferir(self):
        """Admin pode transferir mesmo sem ser o owner do chamado."""
        from app.services.escalonamento_service import transferir_area

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        sup_dest = _sup_mock("id_matheus", "Matheus Costa", areas=["Planejamento"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_dest]
            resultado = transferir_area("id_chamado", "Planejamento", "id_matheus", "motivo", ADMIN)

        assert resultado["sucesso"] is True
        assert updated["area"] == "Planejamento"


# ── Task 3.2: escalonar_colega ────────────────────────────────────────────────


class TestEscalonarColega:
    """Testes da função escalonar_colega."""

    def test_escalonar_colega_troca_responsavel(self):
        """Escalonamento troca responsavel_id mantendo a área."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            resultado = escalonar_colega(
                "id_chamado", "id_matheus", "Matheus tem especialidade X", JULIA
            )

        assert resultado["sucesso"] is True
        assert updated["responsavel_id"] == "id_matheus"

    def test_escalonar_colega_area_permanece(self):
        """Escalonamento de colega não altera a área do chamado."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            escalonar_colega("id_chamado", "id_matheus", "motivo", JULIA)

        assert "area" not in updated  # área não foi atualizada

    def test_escalonar_colega_registra_historico(self):
        """Escalonamento deve registrar histórico com acao='escalonamento_colega'."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_matheus"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            mock_hist_cls.return_value = hist_instancia
            escalonar_colega("id_chamado", "id_matheus", "motivo", JULIA)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "escalonamento_colega"
        assert kwargs.get("campo_alterado") == "responsavel_id"
        hist_instancia.save.assert_called_once()

    def test_escalonar_colega_motivo_obrigatorio(self):
        """Motivo vazio deve levantar ValueError."""
        from app.services.escalonamento_service import escalonar_colega

        with pytest.raises(ValueError, match="motivo"):
            escalonar_colega("id_chamado", "id_matheus", "", JULIA)

    def test_escalonar_colega_recalcula_supervisor_ids_com_acesso(self):
        """supervisor_ids_com_acesso deve ser recalculado após escalonamento."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        colega = _sup_mock("id_matheus", "Matheus Costa", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [colega]
            mock_calc.return_value = ["id_matheus"]
            escalonar_colega("id_chamado", "id_matheus", "motivo", JULIA)

        mock_calc.assert_called_once_with("Engenharia", "id_matheus", [])
        assert updated["supervisor_ids_com_acesso"] == ["id_matheus"]

    def test_escalonar_colega_colega_outra_area_invalido(self):
        """Supervisor destino de área diferente retorna erro."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
        ):
            # Colega não está na área (lista vazia)
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = escalonar_colega("id_chamado", "id_outro_area", "motivo", JULIA)

        assert resultado["sucesso"] is False
        assert "área" in resultado["erro"].lower() or "supervisor" in resultado["erro"].lower()

    def test_escalonar_colega_destino_diferente_do_atual(self):
        """Destino igual ao owner atual retorna erro."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = escalonar_colega("id_chamado", "id_julia", "motivo", JULIA)

        assert resultado["sucesso"] is False
        assert (
            "target" in resultado["erro"].lower()
            or "same" in resultado["erro"].lower()
            or "current" in resultado["erro"].lower()
        )

    def test_escalonar_colega_nao_owner_retorna_erro(self):
        """Supervisor que não é owner não pode escalonar."""
        from app.services.escalonamento_service import escalonar_colega

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = escalonar_colega("id_chamado", "id_matheus", "motivo", NAO_OWNER)

        assert resultado["sucesso"] is False

    def test_escalonar_colega_supervisor_id_obrigatorio(self):
        """supervisor_id=None deve levantar ValueError."""
        from app.services.escalonamento_service import escalonar_colega

        with pytest.raises(ValueError, match="supervisor_id"):
            escalonar_colega("id_chamado", None, "motivo", JULIA)


# ── Task 4.2: incluir_participantes e concluir_minha_parte ───────────────────

PEDRO = _usuario("id_pedro", "Pedro Alves", areas=["Logistica"])
FERNANDA = _usuario("id_fernanda", "Fernanda Lima", areas=["Engenharia"])
SOLICITANTE = _usuario("id_sol", "Sol User", "solicitante", areas=[])


class TestIncluirParticipantes:
    """Testes da função incluir_participantes."""

    def test_incluir_participantes_adiciona(self):
        """Adiciona participante novo à lista."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, updated = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        assert resultado["sucesso"] is True
        assert any(p["supervisor_id"] == "id_pedro" for p in updated["participantes"])

    def test_incluir_participantes_status_pendente(self):
        """Participante incluído recebe status='pendente'."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, updated = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        novo_p = next(p for p in updated["participantes"] if p["supervisor_id"] == "id_pedro")
        assert novo_p["status"] == "pendente"
        assert novo_p["concluido_em"] is None

    def test_incluir_participantes_recalcula_supervisor_ids_com_acesso(self):
        """Após incluir participante, supervisor_ids_com_acesso é recalculado."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, updated = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso"
            ) as mock_calc,
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            mock_calc.return_value = ["id_julia", "id_pedro"]
            incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        mock_calc.assert_called_once()
        assert updated["supervisor_ids_com_acesso"] == ["id_julia", "id_pedro"]

    def test_incluir_participantes_nao_duplica_supervisor(self):
        """Não inclui supervisor_id já presente em participantes."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, updated = _make_db_mock(
            _chamado_dict(
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
        )
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        # Todos duplicados → erro semântico (nenhum novo adicionado)
        assert resultado["sucesso"] is False
        assert "no new participants" in resultado["erro"].lower()

    def test_incluir_participantes_apenas_owner_ou_admin(self):
        """Supervisor que não é owner não pode incluir participantes."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, _ = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                NAO_OWNER,
            )

        assert resultado["sucesso"] is False
        assert "permission" in resultado["erro"].lower()

    def test_incluir_participantes_lista_vazia_retorna_erro(self):
        """Lista vazia de participantes retorna erro."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, _ = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = incluir_participantes("id_chamado", [], JULIA)

        assert resultado["sucesso"] is False

    def test_incluir_participantes_nao_inclui_owner(self):
        """Owner não pode ser adicionado como participante."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, _ = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_julia = _sup_mock("id_julia", "Julia Silva", areas=["Engenharia"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_julia]
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_julia", "area": "Engenharia"}],
                JULIA,
            )

        assert resultado["sucesso"] is False
        assert "owner" in resultado["erro"].lower() or "responsável" in resultado["erro"].lower()

    def test_incluir_participantes_admin_pode_incluir(self):
        """Admin pode incluir participantes mesmo sem ser owner."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, updated = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
            patch(
                "app.services.escalonamento_service.calcular_supervisor_ids_com_acesso",
                return_value=["id_julia", "id_pedro"],
            ),
        ):
            mock_usuario.get_supervisores_por_area.return_value = [sup_pedro]
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                ADMIN,
            )

        assert resultado["sucesso"] is True

    def test_incluir_participantes_supervisor_invalido_na_area(self):
        """supervisor_id que não pertence à área informada retorna erro."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, _ = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Usuario") as mock_usuario,
            patch("app.services.escalonamento_service.Historico"),
        ):
            mock_usuario.get_supervisores_por_area.return_value = []
            resultado = incluir_participantes(
                "id_chamado",
                [{"supervisor_id": "id_desconhecido", "area": "Logistica"}],
                JULIA,
            )

        assert resultado["sucesso"] is False

    def test_incluir_participantes_registra_historico(self):
        """incluir_participantes registra histórico com acao='inclusao_participantes'."""
        from app.services.escalonamento_service import incluir_participantes

        mock_db, _ = _make_db_mock(_chamado_dict(responsavel_id="id_julia", participantes=[]))
        sup_pedro = _sup_mock("id_pedro", "Pedro Alves", areas=["Logistica"])
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.db", mock_db),
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
                "id_chamado",
                [{"supervisor_id": "id_pedro", "area": "Logistica"}],
                JULIA,
            )

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "inclusao_participantes"
        hist_instancia.save.assert_called_once()


class TestConcluirMinhaParte:
    """Testes da função concluir_minha_parte."""

    def test_concluir_minha_parte_muda_status(self):
        """concluir_minha_parte atualiza status do participante para 'concluido'."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, updated = _make_db_mock(chamado)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = concluir_minha_parte("id_chamado", PEDRO)

        assert resultado["sucesso"] is True
        p = next(p for p in updated["participantes"] if p["supervisor_id"] == "id_pedro")
        assert p["status"] == "concluido"

    def test_concluir_minha_parte_grava_concluido_em(self):
        """concluir_minha_parte grava concluido_em com datetime."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, updated = _make_db_mock(chamado)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            concluir_minha_parte("id_chamado", PEDRO)

        p = next(p for p in updated["participantes"] if p["supervisor_id"] == "id_pedro")
        assert p["concluido_em"] is not None

    def test_concluir_minha_parte_nao_participante_retorna_erro(self):
        """Usuário que não é participante recebe erro."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, _ = _make_db_mock(chamado)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = concluir_minha_parte("id_chamado", FERNANDA)

        assert resultado["sucesso"] is False
        assert "participant" in resultado["erro"].lower()

    def test_concluir_minha_parte_ja_concluido_retorna_erro(self):
        """Participante que já concluiu não pode concluir novamente."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, _ = _make_db_mock(chamado)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = concluir_minha_parte("id_chamado", PEDRO)

        assert resultado["sucesso"] is False

    def test_concluir_minha_parte_registra_historico(self):
        """concluir_minha_parte registra histórico."""
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, _ = _make_db_mock(chamado)
        hist_instancia = MagicMock()

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
        ):
            mock_hist_cls.return_value = hist_instancia
            concluir_minha_parte("id_chamado", PEDRO)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "conclusao_parte_participante"
        hist_instancia.save.assert_called_once()

    def test_concluir_minha_parte_nao_altera_data_em_atendimento(self):
        """Fase 7 regressão: concluir_minha_parte NÃO deve incluir data_em_atendimento no update.

        Garante que o deadline de resolução (calculado a partir de data_em_atendimento)
        não seja alterado acidentalmente ao marcar parte como concluída.
        """
        from app.services.escalonamento_service import concluir_minha_parte

        chamado = _chamado_dict(
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
        mock_db, updated = _make_db_mock(chamado)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = concluir_minha_parte("id_chamado", PEDRO)

        assert resultado["sucesso"] is True
        assert "data_em_atendimento" not in updated


class TestPodeConcluirGlobal:
    """Testes dos helpers pode_concluir_global e todos_participantes_concluidos."""

    def test_pode_concluir_sem_participantes(self):
        from app.models import Chamado
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
        from app.models import Chamado
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
        from app.models import Chamado
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


# ── Previsão de atendimento — definir_previsao_atendimento ─────────────────────


class TestDefinirPrevisaoAtendimento:
    """Testes da função definir_previsao_atendimento.

    Regra: só owner (responsavel_id == usuario.id) ou admin, E usuario precisa
    ser supervisor+ (perfil in {supervisor, admin, admin_global}). Motivo
    obrigatório. previsao precisa ser no futuro. Sem teto máximo. Só grava os
    campos — não dispara e-mail nenhum (o silêncio é feito pelo motor de SLA
    lendo o campo, não aqui).
    """

    def test_definir_previsao_grava_campos_no_firestore(self):
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        previsao = datetime.now() + timedelta(days=2)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = definir_previsao_atendimento(
                "id_chamado", previsao, "Combinado com o gestor, preciso de mais tempo", JULIA
            )

        assert resultado["sucesso"] is True
        assert updated["previsao_atendimento"] == previsao
        assert (
            updated["motivo_previsao_atendimento"]
            == "Combinado com o gestor, preciso de mais tempo"
        )

    def test_definir_previsao_registra_historico(self):
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))
        hist_instancia = MagicMock()
        previsao = datetime.now() + timedelta(days=1)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico") as mock_hist_cls,
        ):
            mock_hist_cls.return_value = hist_instancia
            definir_previsao_atendimento("id_chamado", previsao, "motivo", JULIA)

        args, kwargs = mock_hist_cls.call_args
        assert kwargs.get("acao") == "definicao_previsao_atendimento"
        assert kwargs.get("campo_alterado") == "previsao_atendimento"
        hist_instancia.save.assert_called_once()

    def test_definir_previsao_motivo_obrigatorio(self):
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        previsao = datetime.now() + timedelta(days=1)
        with pytest.raises(ValueError, match="motivo"):
            definir_previsao_atendimento("id_chamado", previsao, "", JULIA)

    def test_definir_previsao_data_obrigatoria(self):
        from app.services.escalonamento_service import definir_previsao_atendimento

        with pytest.raises(ValueError, match="previsao"):
            definir_previsao_atendimento("id_chamado", None, "motivo", JULIA)

    def test_definir_previsao_no_passado_retorna_erro(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        from app.services.escalonamento_service import definir_previsao_atendimento
        from config import Config

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))
        # "Passado" tem que ser em relação ao fuso de negócio (SLA_TIMEZONE), não
        # ao relógio naive do runner — em CI (UTC), "agora - 1h" ainda pode estar
        # no futuro em Brasília (UTC-3), fazendo o teste passar por acidente.
        agora_fuso_negocio = datetime.now(ZoneInfo(Config.SLA_TIMEZONE)).replace(tzinfo=None)
        previsao_passada = agora_fuso_negocio - timedelta(hours=1)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = definir_previsao_atendimento(
                "id_chamado", previsao_passada, "motivo", JULIA
            )

        assert resultado["sucesso"] is False

    def test_definir_previsao_futura_no_fuso_de_negocio_nao_e_rejeitada(self):
        """Regressão: previsão claramente futura no fuso de negócio (Brasília) não
        pode ser rejeitada só porque o servidor roda em outro fuso (ex.: UTC em
        container Docker/Azure Container Apps).

        O campo chega do <input type="datetime-local"> como string sem timezone
        (ex.: "2026-07-13T11:00"), representando um horário no fuso de negócio
        (Config.SLA_TIMEZONE = America/Sao_Paulo). Comparar isso contra
        datetime.now() puro (relógio do SO, sem fuso) quebra assim que o
        servidor não estiver na mesma timezone que o negócio: um horário 2h no
        futuro em Brasília pode parecer "no passado" pro servidor em UTC
        (Brasília = UTC-3), e a previsão é rejeitada por engano.
        """
        from datetime import datetime

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )

        # Momento real: 09:00 em Brasília (UTC-3) == 12:00 UTC.
        # Supervisor define previsão pra 11:00 em Brasília — 2h no futuro, de verdade.
        previsao_11h_brasilia = datetime(2026, 7, 13, 11, 0)

        def _now_mock(tz=None):
            # Sem tz: relogio "naive" do SO do servidor, que roda em UTC -> 12:00.
            if tz is None:
                return datetime(2026, 7, 13, 12, 0)
            # Com tz (America/Sao_Paulo): mesmo instante real, em Brasilia -> 09:00.
            return datetime(2026, 7, 13, 9, 0, tzinfo=tz)

        mock_datetime = MagicMock(wraps=datetime)
        mock_datetime.now.side_effect = _now_mock

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.datetime", mock_datetime),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = definir_previsao_atendimento(
                "id_chamado", previsao_11h_brasilia, "motivo valido", JULIA
            )

        assert resultado["sucesso"] is True, (
            "Previsão 2h no futuro (fuso de negócio) foi rejeitada como 'passado' "
            "por causa da comparação ingênua com datetime.now() do servidor."
        )

    def test_definir_previsao_nao_owner_retorna_erro(self):
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id="id_julia"))
        previsao = datetime.now() + timedelta(days=1)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = definir_previsao_atendimento("id_chamado", previsao, "motivo", NAO_OWNER)

        assert resultado["sucesso"] is False

    def test_definir_previsao_owner_solicitante_negado(self):
        """Owner que não é supervisor+ (perfil solicitante) não pode definir previsão,
        mesmo sendo o responsavel_id do chamado — regra exige perfil supervisor+."""
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, _ = _make_db_mock(_chamado_dict(area="Engenharia", responsavel_id=SOLICITANTE.id))
        previsao = datetime.now() + timedelta(days=1)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = definir_previsao_atendimento("id_chamado", previsao, "motivo", SOLICITANTE)

        assert resultado["sucesso"] is False

    def test_definir_previsao_admin_nao_owner_permitido(self):
        """Admin pode definir mesmo não sendo o owner."""
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        previsao = datetime.now() + timedelta(days=1)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = definir_previsao_atendimento("id_chamado", previsao, "motivo", ADMIN)

        assert resultado["sucesso"] is True
        assert updated["previsao_atendimento"] == previsao

    def test_definir_previsao_sem_teto_maximo(self):
        """Não há limite de dias — previsão bem distante no futuro é aceita."""
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, updated = _make_db_mock(
            _chamado_dict(area="Engenharia", responsavel_id="id_julia")
        )
        previsao_distante = datetime.now() + timedelta(days=90)

        with (
            patch("app.services.escalonamento_service.db", mock_db),
            patch("app.services.escalonamento_service.Historico"),
        ):
            resultado = definir_previsao_atendimento(
                "id_chamado", previsao_distante, "motivo", JULIA
            )

        assert resultado["sucesso"] is True
        assert updated["previsao_atendimento"] == previsao_distante

    def test_definir_previsao_chamado_nao_encontrado(self):
        from datetime import datetime, timedelta

        from app.services.escalonamento_service import definir_previsao_atendimento

        mock_db, _ = _make_db_mock(doc_exists=False)
        previsao = datetime.now() + timedelta(days=1)

        with patch("app.services.escalonamento_service.db", mock_db):
            resultado = definir_previsao_atendimento("id_chamado", previsao, "motivo", JULIA)

        assert resultado["sucesso"] is False
