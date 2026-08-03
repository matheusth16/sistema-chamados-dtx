"""
Fase 2 — TDD: persistência de observadores na criação de chamados.

Persistência roda contra Postgres real (db_session) via Chamado.salvar() —
não mockamos mais execute_with_retry/db.collection (Marco 7). A antiga
desnormalização "observadores_ids" (usada pro array-contains do Firestore)
não existe mais: observadores viram linhas reais em chamados_observadores
(tabela-junção), verificadas via Chamado.get_by_id(...).observadores.
"""

import json
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.models import Chamado

pytestmark = pytest.mark.usefixtures("db_session")


@pytest.fixture(autouse=True)
def _patch_supervisores():
    with patch("app.models_usuario.Usuario.get_supervisores_por_area", return_value=[]):
        yield


def _base_form(observadores_json="[]"):
    return {
        "categoria": "TI",
        "tipo": "TI",
        "descricao": "Descrição com mais de 10 chars para passar na validação.",
        "rl_codigo": "",
        "impacto": "",
        "gate": "",
        "observadores_json": observadores_json,
    }


def _files_mock():
    m = MagicMock()
    m.getlist.return_value = []
    m.get.return_value = None
    return m


def _fake_atribuidor_result():
    return {
        "sucesso": True,
        "supervisor": {"id": "sup_1", "nome": "Supervisor Teste"},
        "motivo": "",
    }


class TestCriacaoComObservadores:
    def test_observadores_persistidos_no_chamado(self, app):
        """observadores_json no form → observadores persistidos na tabela-junção."""
        from app.services.chamados_criacao_service import criar_chamado

        obs_list = [{"usuario_id": "obs_1", "nome": "Obs Um", "email": "obs1@test.com"}]
        form = _base_form(json.dumps(obs_list))

        with ExitStack() as stack:
            stack.enter_context(
                patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None)
            )
            stack.enter_context(
                patch(
                    "app.services.chamados_criacao_service.gerar_numero_chamado",
                    return_value="2026-001",
                )
            )
            mock_atr = stack.enter_context(
                patch("app.services.chamados_criacao_service.atribuidor")
            )
            stack.enter_context(patch("app.services.chamados_criacao_service.Historico"))
            stack.enter_context(patch("app.services.chamados_criacao_service.threading.Thread"))
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service._notificar_observadores_inclusao")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None)
            )

            mock_atr.atribuir.return_value = _fake_atribuidor_result()
            with app.app_context():
                chamado_id, _, erro, _ = criar_chamado(
                    form=form,
                    files=_files_mock(),
                    solicitante_id="sol_1",
                    solicitante_nome="Solicitante",
                )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == obs_list

    def test_observadores_multiplos_persistidos_na_tabela_juncao(self, app):
        """Múltiplos observadores → todos viram linhas em chamados_observadores."""
        from app.services.chamados_criacao_service import criar_chamado

        obs_list = [
            {"usuario_id": "obs_1", "nome": "Obs Um", "email": "obs1@test.com"},
            {"usuario_id": "obs_2", "nome": "Obs Dois", "email": "obs2@test.com"},
        ]
        form = _base_form(json.dumps(obs_list))

        with ExitStack() as stack:
            stack.enter_context(
                patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None)
            )
            stack.enter_context(
                patch(
                    "app.services.chamados_criacao_service.gerar_numero_chamado",
                    return_value="2026-001",
                )
            )
            mock_atr = stack.enter_context(
                patch("app.services.chamados_criacao_service.atribuidor")
            )
            stack.enter_context(patch("app.services.chamados_criacao_service.Historico"))
            stack.enter_context(patch("app.services.chamados_criacao_service.threading.Thread"))
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service._notificar_observadores_inclusao")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None)
            )

            mock_atr.atribuir.return_value = _fake_atribuidor_result()
            with app.app_context():
                chamado_id, _, erro, _ = criar_chamado(
                    form=form,
                    files=_files_mock(),
                    solicitante_id="sol_1",
                    solicitante_nome="Solicitante",
                )

        assert erro is None
        ids_persistidos = {o["usuario_id"] for o in Chamado.get_by_id(chamado_id).observadores}
        assert ids_persistidos == {"obs_1", "obs_2"}

    def test_observadores_json_invalido_ignorado(self, app):
        """JSON inválido → chamado criado sem observadores, sem retornar erro."""
        from app.services.chamados_criacao_service import criar_chamado

        form = _base_form("NAO_EH_JSON_VALIDO")

        with ExitStack() as stack:
            stack.enter_context(
                patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None)
            )
            stack.enter_context(
                patch(
                    "app.services.chamados_criacao_service.gerar_numero_chamado",
                    return_value="2026-001",
                )
            )
            mock_atr = stack.enter_context(
                patch("app.services.chamados_criacao_service.atribuidor")
            )
            stack.enter_context(patch("app.services.chamados_criacao_service.Historico"))
            stack.enter_context(patch("app.services.chamados_criacao_service.threading.Thread"))
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service._notificar_observadores_inclusao")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=None)
            )

            mock_atr.atribuir.return_value = _fake_atribuidor_result()
            with app.app_context():
                chamado_id, _, erro, _ = criar_chamado(
                    form=form,
                    files=_files_mock(),
                    solicitante_id="sol_1",
                    solicitante_nome="Solicitante",
                )

        assert erro is None
        assert Chamado.get_by_id(chamado_id).observadores == []

    def _enter_full_notif_patches(self, stack, sup_mock):
        """Adiciona patches de todas as chamadas dentro de _notificar."""
        stack.enter_context(
            patch("app.services.chamados_criacao_service.Usuario.get_by_id", return_value=sup_mock)
        )
        stack.enter_context(patch("app.services.chamados_criacao_service.criar_notificacao"))
        stack.enter_context(patch("app.services.chamados_criacao_service.enviar_webpush_usuario"))

    def test_notificacao_observadores_disparada(self, app):
        """_notificar_observadores_inclusao chamado quando há observadores."""
        from app.services.chamados_criacao_service import criar_chamado

        obs_list = [{"usuario_id": "obs_1", "nome": "Obs", "email": "obs@test.com"}]
        form = _base_form(json.dumps(obs_list))

        sup_mock = MagicMock()
        sup_mock.id = "sup_1"

        with ExitStack() as stack:
            stack.enter_context(
                patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None)
            )
            stack.enter_context(
                patch(
                    "app.services.chamados_criacao_service.gerar_numero_chamado",
                    return_value="2026-001",
                )
            )
            mock_atr = stack.enter_context(
                patch("app.services.chamados_criacao_service.atribuidor")
            )
            stack.enter_context(patch("app.services.chamados_criacao_service.Historico"))
            mock_thread_cls = stack.enter_context(
                patch("app.services.chamados_criacao_service.threading.Thread")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado")
            )
            mock_notif = stack.enter_context(
                patch("app.services.chamados_criacao_service._notificar_observadores_inclusao")
            )
            self._enter_full_notif_patches(stack, sup_mock)

            mock_atr.atribuir.return_value = _fake_atribuidor_result()

            def fake_thread_cls(target=None, daemon=None, **kw):
                t = MagicMock()
                if target:
                    t.start.side_effect = target
                return t

            mock_thread_cls.side_effect = fake_thread_cls

            with app.app_context():
                criar_chamado(
                    form=form,
                    files=_files_mock(),
                    solicitante_id="sol_1",
                    solicitante_nome="Solicitante",
                )

        mock_notif.assert_called_once()

    def test_sem_observadores_nao_dispara_notificacao(self, app):
        """Sem observadores → _notificar_observadores_inclusao NÃO é chamado."""
        from app.services.chamados_criacao_service import criar_chamado

        form = _base_form("[]")

        sup_mock = MagicMock()
        sup_mock.id = "sup_1"

        with ExitStack() as stack:
            stack.enter_context(
                patch("app.services.chamados_criacao_service.salvar_anexo", return_value=None)
            )
            stack.enter_context(
                patch(
                    "app.services.chamados_criacao_service.gerar_numero_chamado",
                    return_value="2026-001",
                )
            )
            mock_atr = stack.enter_context(
                patch("app.services.chamados_criacao_service.atribuidor")
            )
            stack.enter_context(patch("app.services.chamados_criacao_service.Historico"))
            mock_thread_cls = stack.enter_context(
                patch("app.services.chamados_criacao_service.threading.Thread")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_aprovador_novo_chamado")
            )
            stack.enter_context(
                patch("app.services.chamados_criacao_service.notificar_setores_adicionais_chamado")
            )
            mock_notif = stack.enter_context(
                patch("app.services.chamados_criacao_service._notificar_observadores_inclusao")
            )
            self._enter_full_notif_patches(stack, sup_mock)

            mock_atr.atribuir.return_value = _fake_atribuidor_result()

            def fake_thread_cls(target=None, daemon=None, **kw):
                t = MagicMock()
                if target:
                    t.start.side_effect = target
                return t

            mock_thread_cls.side_effect = fake_thread_cls

            with app.app_context():
                criar_chamado(
                    form=form,
                    files=_files_mock(),
                    solicitante_id="sol_1",
                    solicitante_nome="Solicitante",
                )

        mock_notif.assert_not_called()
