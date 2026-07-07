"""
Fase 5 — TDD: chamado_notificacao_service (fan-out centralizado).

Testa:
- destinatarios_do_chamado: retorna responsável + observadores como lista de usuários
- notificar_cancelamento_chamado: envia email ao responsável e cada observador
"""

from unittest.mock import MagicMock, patch


def _usuario_mock(uid, nome, email, perfil="supervisor"):
    u = MagicMock()
    u.id = uid
    u.nome = nome
    u.email = email
    u.perfil = perfil
    u.ativo = True
    return u


class TestDestinatariosDoChamado:
    def test_retorna_responsavel_e_observadores(self):
        """Com responsável + 2 observadores → lista com 3 usuários."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": "sup_1",
            "observadores": [
                {"usuario_id": "obs_a", "email": "a@test.com", "nome": "Obs A"},
                {"usuario_id": "obs_b", "email": "b@test.com", "nome": "Obs B"},
            ],
        }
        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        obs_a = _usuario_mock("obs_a", "Obs A", "a@test.com")
        obs_b = _usuario_mock("obs_b", "Obs B", "b@test.com")

        def get_by_id_side(uid):
            return {"sup_1": sup, "obs_a": obs_a, "obs_b": obs_b}.get(uid)

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.side_effect = get_by_id_side
            resultado = destinatarios_do_chamado(dados_chamado)

        ids = [u.id for u in resultado]
        assert "sup_1" in ids
        assert "obs_a" in ids
        assert "obs_b" in ids

    def test_sem_responsavel_retorna_so_observadores(self):
        """Sem responsável_id → apenas observadores."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": None,
            "observadores": [
                {"usuario_id": "obs_a", "email": "a@test.com", "nome": "Obs A"},
            ],
        }
        obs_a = _usuario_mock("obs_a", "Obs A", "a@test.com")

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.return_value = obs_a
            resultado = destinatarios_do_chamado(dados_chamado)

        assert len(resultado) == 1
        assert resultado[0].id == "obs_a"

    def test_sem_observadores_retorna_so_responsavel(self):
        """Sem observadores → apenas responsável."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": "sup_1",
            "observadores": [],
        }
        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.return_value = sup
            resultado = destinatarios_do_chamado(dados_chamado)

        assert len(resultado) == 1
        assert resultado[0].id == "sup_1"

    def test_usuario_nao_encontrado_omitido(self):
        """Se get_by_id retorna None (usuário deletado), não entra na lista."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": "sup_inexistente",
            "observadores": [],
        }

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.return_value = None
            resultado = destinatarios_do_chamado(dados_chamado)

        assert resultado == []


class TestNotificarCancelamentoChamado:
    def test_email_enviado_ao_responsavel(self):
        """notificar_cancelamento_chamado envia email ao responsável."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Problema resolvido",
                solicitante_nome="João",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )

        assert mock_email.called
        args = mock_email.call_args[0]
        assert args[0] == "sup@test.com"

    def test_email_enviado_a_cada_observador(self):
        """Email deve ser enviado para cada destinatário (responsável + observadores)."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        obs = _usuario_mock("obs_1", "Obs A", "obs@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup, obs],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Problema resolvido",
                solicitante_nome="João",
                dados_chamado={
                    "responsavel_id": "sup_1",
                    "observadores": [{"usuario_id": "obs_1"}],
                },
            )

        assert mock_email.call_count == 2
        emails_enviados = [c[0][0] for c in mock_email.call_args_list]
        assert "sup@test.com" in emails_enviados
        assert "obs@test.com" in emails_enviados

    def test_sem_destinatarios_nao_envia_email(self):
        """Se não há responsável nem observadores → nenhum email enviado."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Problema resolvido",
                solicitante_nome="João",
                dados_chamado={"responsavel_id": None, "observadores": []},
            )

        mock_email.assert_not_called()


class TestNotificarEdicaoDescricaoSolicitante:
    def test_email_enviado_ao_responsavel_e_observadores(self):
        """notificar_edicao_descricao_solicitante envia email a responsável e observadores."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        obs = _usuario_mock("obs_1", "Obs A", "obs@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup, obs],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                valor_anterior="Texto antigo",
                valor_novo="Texto novo editado",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )

        assert mock_email.call_count == 2
        emails_enviados = [c[0][0] for c in mock_email.call_args_list]
        assert "sup@test.com" in emails_enviados
        assert "obs@test.com" in emails_enviados

    def test_corpo_contem_valores_anterior_e_novo(self):
        """Corpo do email contém valor_anterior e valor_novo truncados."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-002",
                categoria="TI",
                solicitante_nome="Maria",
                valor_anterior="Descrição original do problema",
                valor_novo="Descrição atualizada com mais detalhes",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )

        assert mock_email.called
        corpo_html = mock_email.call_args[0][2]
        assert "CH-002" in corpo_html
        assert "Maria" in corpo_html
        assert "Descrição original" in corpo_html
        assert "Descrição atualizada" in corpo_html

    def test_sem_destinatarios_nao_envia_email(self):
        """Sem responsável nem observadores → nenhum email enviado."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-003",
                categoria="TI",
                solicitante_nome="Carlos",
                valor_anterior="Anterior",
                valor_novo="Novo",
                dados_chamado={},
            )

        mock_email.assert_not_called()


class TestNotificarObservadoresCriacao:
    def test_email_enviado_a_cada_observador(self):
        """notificar_observadores_criacao envia email para cada observador (resolução via get_by_id)."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        obs_list = [
            {"usuario_id": "obs_1", "nome": "Obs Um"},
            {"usuario_id": "obs_2", "nome": "Obs Dois"},
        ]
        mock_u1 = _usuario_mock("obs_1", "Obs Um", "obs1@test.com")
        mock_u2 = _usuario_mock("obs_2", "Obs Dois", "obs2@test.com")

        with (
            patch("app.services.chamado_notificacao_service.Usuario") as mock_uclass,
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.chamado_notificacao_service.webpush_service"),
        ):
            mock_uclass.get_by_id.side_effect = lambda uid: {
                "obs_1": mock_u1,
                "obs_2": mock_u2,
            }.get(uid)
            mock_email.return_value = (True, None)
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=obs_list,
            )

        assert mock_email.call_count == 2
        emails = [c[0][0] for c in mock_email.call_args_list]
        assert "obs1@test.com" in emails
        assert "obs2@test.com" in emails

    def test_lista_vazia_nao_envia_email(self):
        """Lista vazia de observadores → nenhum email enviado."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        with patch("app.services.chamado_notificacao_service.enviar_email") as mock_email:
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=[],
            )

        mock_email.assert_not_called()

    def test_observador_sem_email_ignorado(self):
        """Observador sem email no banco → não envia email para ele."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        obs_list = [
            {"usuario_id": "obs_1", "nome": "Obs Sem Email"},
            {"usuario_id": "obs_2", "nome": "Obs Com Email"},
        ]
        mock_u1 = _usuario_mock("obs_1", "Obs Sem Email", "")
        mock_u2 = _usuario_mock("obs_2", "Obs Com Email", "obs2@test.com")

        with (
            patch("app.services.chamado_notificacao_service.Usuario") as mock_uclass,
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.chamado_notificacao_service.webpush_service"),
        ):
            mock_uclass.get_by_id.side_effect = lambda uid: {
                "obs_1": mock_u1,
                "obs_2": mock_u2,
            }.get(uid)
            mock_email.return_value = (True, None)
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=obs_list,
            )

        assert mock_email.call_count == 1
        assert mock_email.call_args[0][0] == "obs2@test.com"

    def test_destinatarios_sem_email_pulados_em_cancelamento(self):
        """notificar_cancelamento_chamado pula usuário sem email."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        usuario_sem_email = _usuario_mock("u_1", "Sem Email", "")
        usuario_sem_email.email = ""

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[usuario_sem_email],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Motivo",
                solicitante_nome="João",
                dados_chamado={},
            )

        mock_email.assert_not_called()

    def test_observador_sem_usuario_id_ignorado(self):
        """Observador sem usuario_id na dict → omitido silenciosamente."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": None,
            "observadores": [{"nome": "Obs Sem ID", "email": "obs@test.com"}],
        }

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.return_value = None
            resultado = destinatarios_do_chamado(dados_chamado)

        assert resultado == []

    def test_responsavel_tambem_observador_aparece_uma_vez(self):
        """CT-REQ-12: se responsável é observador, destinatarios_do_chamado deduplica por id."""
        from app.services.chamado_notificacao_service import destinatarios_do_chamado

        dados_chamado = {
            "responsavel_id": "sup_1",
            "observadores": [
                {"usuario_id": "sup_1", "email": "sup@test.com", "nome": "Supervisor"},
                {"usuario_id": "obs_a", "email": "a@test.com", "nome": "Obs A"},
            ],
        }
        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        obs_a = _usuario_mock("obs_a", "Obs A", "a@test.com")

        def get_by_id_side(uid):
            return {"sup_1": sup, "obs_a": obs_a}.get(uid)

        with patch("app.services.chamado_notificacao_service.Usuario") as mock_cls:
            mock_cls.get_by_id.side_effect = get_by_id_side
            resultado = destinatarios_do_chamado(dados_chamado)

        ids = [u.id for u in resultado]
        assert ids.count("sup_1") == 1, (
            "Responsável duplicado como observador deve aparecer uma vez"
        )
        assert len(resultado) == 2


class TestNotificarAnexoTardioChamado:
    def test_email_enviado_ao_responsavel_e_observadores(self):
        """notificar_anexo_tardio_chamado envia email a responsável + observadores."""
        from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        obs = _usuario_mock("obs_1", "Obs A", "obs@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup, obs],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_anexo_tardio_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                nome_arquivo="relatorio.pdf",
                motivo="Documento esquecido no envio",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )

        assert mock_email.call_count == 2
        emails_enviados = [c[0][0] for c in mock_email.call_args_list]
        assert "sup@test.com" in emails_enviados
        assert "obs@test.com" in emails_enviados

    def test_corpo_contem_nome_arquivo_e_motivo(self):
        """Corpo do email deve incluir nome do arquivo e motivo."""
        from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            mock_email.return_value = (True, None)
            notificar_anexo_tardio_chamado(
                chamado_id="ch_2",
                numero_chamado="CH-002",
                categoria="Infra",
                solicitante_nome="Maria",
                nome_arquivo="planilha.xlsx",
                motivo="Arquivo adicional necessário",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )

        corpo_html = mock_email.call_args[0][2]
        assert "CH-002" in corpo_html
        assert "planilha.xlsx" in corpo_html
        assert "Arquivo adicional necessário" in corpo_html

    def test_sem_destinatarios_nao_envia_email(self):
        """Sem responsável nem observadores → nenhum email enviado."""
        from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
        ):
            notificar_anexo_tardio_chamado(
                chamado_id="ch_3",
                numero_chamado="CH-003",
                categoria="TI",
                solicitante_nome="Carlos",
                nome_arquivo="f.pdf",
                motivo="Motivo qualquer",
                dados_chamado={},
            )

        mock_email.assert_not_called()


class TestInAppEWebPushNotificacoes:
    """Lacunas A+B: in-app e web push para edição/anexo/cancelamento."""

    def _dados(self):
        return {"responsavel_id": "sup_1", "observadores": []}

    def test_inapp_criada_em_edicao_descricao(self):
        """notificar_edicao_descricao_solicitante cria in-app para cada destinatário."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                valor_anterior="A",
                valor_novo="B",
                dados_chamado=self._dados(),
            )
        mock_inapp.assert_called_once()
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_edicao_descricao"

    def test_inapp_criada_em_anexo_tardio(self):
        """notificar_anexo_tardio_chamado cria in-app para cada destinatário."""
        from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_anexo_tardio_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                nome_arquivo="f.pdf",
                motivo="motivo",
                dados_chamado=self._dados(),
            )
        mock_inapp.assert_called_once()
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_anexo_tardio"

    def test_inapp_criada_em_cancelamento(self):
        """notificar_cancelamento_chamado cria in-app para cada destinatário."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Problema resolvido",
                solicitante_nome="João",
                dados_chamado=self._dados(),
            )
        mock_inapp.assert_called_once()
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_cancelamento"

    def test_webpush_enviado_em_edicao_descricao(self, app):
        """notificar_edicao_descricao_solicitante envia web push por destinatário."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        with (
            app.app_context(),
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
        ):
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                valor_anterior="A",
                valor_novo="B",
                dados_chamado=self._dados(),
            )
        mock_push.assert_called_once()

    def test_webpush_enviado_em_anexo_tardio(self, app):
        """notificar_anexo_tardio_chamado envia web push por destinatário."""
        from app.services.chamado_notificacao_service import notificar_anexo_tardio_chamado

        sup = _usuario_mock("sup_1", "Supervisor", "sup@test.com")
        with (
            app.app_context(),
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
        ):
            notificar_anexo_tardio_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                nome_arquivo="f.pdf",
                motivo="motivo",
                dados_chamado=self._dados(),
            )
        mock_push.assert_called_once()


class TestEmailShellEstrutura:
    """Lacuna C: emails usam build_email_shell (verificação de estrutura no HTML)."""

    def _dest(self, uid="sup_1", email="sup@test.com"):
        return _usuario_mock(uid, "Supervisor", email)

    def test_cancelamento_usa_email_shell(self):
        """notificar_cancelamento_chamado → HTML contém estrutura do shell."""
        from app.services.chamado_notificacao_service import notificar_cancelamento_chamado

        sup = self._dest()
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
        ):
            mock_email.return_value = (True, None)
            notificar_cancelamento_chamado(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                motivo="Motivo teste",
                solicitante_nome="João",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )
        corpo_html = mock_email.call_args[0][2]
        assert 'role="presentation"' in corpo_html or "Andon" in corpo_html

    def test_edicao_descricao_usa_email_shell(self):
        """notificar_edicao_descricao_solicitante → HTML contém estrutura do shell."""
        from app.services.chamado_notificacao_service import notificar_edicao_descricao_solicitante

        sup = self._dest()
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[sup],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
        ):
            mock_email.return_value = (True, None)
            notificar_edicao_descricao_solicitante(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                valor_anterior="Anterior",
                valor_novo="Novo",
                dados_chamado={"responsavel_id": "sup_1", "observadores": []},
            )
        corpo_html = mock_email.call_args[0][2]
        assert 'role="presentation"' in corpo_html or "Andon" in corpo_html


class TestNotificarObservadoresMudancaStatus:
    def test_email_e_inapp_enviados_para_cada_observador(self):
        """notificar_observadores_mudanca_status envia email + in-app a cada observador."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        obs1 = _usuario_mock("obs_1", "Obs A", "a@test.com")
        obs2 = _usuario_mock("obs_2", "Obs B", "b@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[obs1, obs2],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            mock_email.return_value = (True, None)
            notificar_observadores_mudanca_status(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                novo_status="Em Atendimento",
                dados_chamado={
                    "responsavel_id": "sup_1",
                    "observadores": [{"usuario_id": "obs_1"}, {"usuario_id": "obs_2"}],
                },
            )

        assert mock_email.call_count == 2
        assert mock_inapp.call_count == 2

    def test_sem_observadores_nao_envia_nada(self):
        """Sem destinatários → nenhum email ou in-app."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_observadores_mudanca_status(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                novo_status="Concluído",
                dados_chamado={},
            )

        mock_email.assert_not_called()
        mock_inapp.assert_not_called()

    def test_corpo_email_contem_novo_status_e_numero(self):
        """Corpo do email contém o novo status e número do chamado."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        obs = _usuario_mock("obs_1", "Obs A", "a@test.com")

        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[obs],
            ),
            patch("app.services.chamado_notificacao_service.enviar_email") as mock_email,
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
        ):
            mock_email.return_value = (True, None)
            notificar_observadores_mudanca_status(
                chamado_id="ch_2",
                numero_chamado="CH-042",
                categoria="Infra",
                novo_status="Concluído",
                dados_chamado={"responsavel_id": None, "observadores": [{"usuario_id": "obs_1"}]},
            )

        corpo_html = mock_email.call_args[0][2]
        assert "CH-042" in corpo_html
        assert "Completed" in corpo_html


class TestNotificarObservadoresMudancaStatusLacunas:
    """Lacunas 1+2: tipos in-app corretos e web push em mudança de status."""

    def _dados(self):
        return {"responsavel_id": "sup_1", "observadores": []}

    def test_tipo_inapp_concluido_usa_observador_status_concluido(self):
        """Lacuna 2: tipo in-app para 'Concluído' deve ser 'observador_status_concluido'."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        obs = _usuario_mock("obs_1", "Obs", "obs@test.com")
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[obs],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_observadores_mudanca_status(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                novo_status="Concluído",
                dados_chamado=self._dados(),
            )
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_status_concluido"

    def test_tipo_inapp_em_atendimento_usa_observador_status_em_atendimento(self):
        """Lacuna 2: tipo in-app para 'Em Atendimento' deve ser 'observador_status_em_atendimento'."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        obs = _usuario_mock("obs_1", "Obs", "obs@test.com")
        with (
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[obs],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_observadores_mudanca_status(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                novo_status="Em Atendimento",
                dados_chamado=self._dados(),
            )
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_status_em_atendimento"

    def test_webpush_enviado_por_destinatario(self, app):
        """Lacuna 1: web push enviado para cada destinatário em mudança de status."""
        from app.services.chamado_notificacao_service import notificar_observadores_mudanca_status

        obs = _usuario_mock("obs_1", "Obs", "obs@test.com")
        with (
            app.app_context(),
            patch(
                "app.services.chamado_notificacao_service.destinatarios_do_chamado",
                return_value=[obs],
            ),
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
        ):
            notificar_observadores_mudanca_status(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                novo_status="Em Atendimento",
                dados_chamado=self._dados(),
            )
        mock_push.assert_called_once()


class TestNotificarObservadoresCriacaoInApp:
    """Lacuna 3: in-app + web push na inclusão de observador na criação."""

    def test_inapp_disparada_para_observador_com_usuario_id(self):
        """notificar_observadores_criacao cria in-app para obs com usuario_id."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        obs_list = [{"usuario_id": "obs_1", "nome": "Obs Um"}]
        mock_u = _usuario_mock("obs_1", "Obs Um", "obs1@test.com")
        with (
            patch("app.services.chamado_notificacao_service.Usuario") as mock_uclass,
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
            patch("app.services.chamado_notificacao_service.webpush_service"),
        ):
            mock_uclass.get_by_id.return_value = mock_u
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=obs_list,
            )
        mock_inapp.assert_called_once()
        assert mock_inapp.call_args.kwargs.get("tipo") == "observador_incluido"

    def test_webpush_enviado_na_inclusao_de_observador(self, app):
        """notificar_observadores_criacao envia web push para obs com usuario_id."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        obs_list = [{"usuario_id": "obs_1", "nome": "Obs Um"}]
        mock_u = _usuario_mock("obs_1", "Obs Um", "obs1@test.com")
        with (
            app.app_context(),
            patch("app.services.chamado_notificacao_service.Usuario") as mock_uclass,
            patch(
                "app.services.chamado_notificacao_service.enviar_email", return_value=(True, None)
            ),
            patch("app.services.chamado_notificacao_service.criar_notificacao"),
            patch("app.services.webpush_service.enviar_webpush_usuario") as mock_push,
        ):
            mock_uclass.get_by_id.return_value = mock_u
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=obs_list,
            )
        mock_push.assert_called_once()

    def test_obs_sem_usuario_id_nao_gera_inapp(self):
        """Obs sem usuario_id é ignorado completamente (sem email e sem in-app)."""
        from app.services.chamado_notificacao_service import notificar_observadores_criacao

        obs_list = [{"nome": "Obs Externo"}]
        with (
            patch("app.services.chamado_notificacao_service.criar_notificacao") as mock_inapp,
        ):
            notificar_observadores_criacao(
                chamado_id="ch_1",
                numero_chamado="CH-001",
                categoria="TI",
                solicitante_nome="João",
                observadores=obs_list,
            )
        mock_inapp.assert_not_called()
