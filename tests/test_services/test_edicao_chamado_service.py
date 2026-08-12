"""
Testes do serviço de edição de chamados (processar_edicao_chamado).

Fase 2 (Marco 7 + 8): leitura/escrita do CHAMADO usa Chamado.get_by_id()/
atualizar_campos() (Postgres) e o histórico usa Historico.salvar_lote()
(Postgres, Marco 8) — nenhum dos dois toca Firestore mais. Chamado e
Historico são mockados como classe (não precisa de Postgres real neste
arquivo — só o contrato get_by_id/atualizar_campos/salvar_lote importa aqui).
"""

from unittest.mock import MagicMock, patch


def _default_data():
    return {
        "numero_chamado": "CHM-001",
        "status": "Aberto",
        "descricao": "Descrição original",
        "responsavel": "Resp Atual",
        "responsavel_id": "resp1",
        "area": "Manutencao",
        "sla_dias": None,
        "anexo": None,
        "anexos": [],
        "setores_adicionais": [],
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "solicitante_nome": "Sol Teste",
    }


def _make_usuario(perfil="admin", uid="admin1", areas=None):
    u = MagicMock()
    u.id = uid
    u.nome = "Admin Teste"
    u.perfil = perfil
    u.areas = areas or ["Manutencao"]
    # MagicMock() é truthy por padrão — sem isso, is_admin_or_above/is_gestor_only
    # "existem" como sub-mocks truthy e mascaram checagens reais de permissão
    # (ex.: supervisor_pode_alterar_chamado usa usuario.is_admin_or_above de verdade).
    u.is_admin_or_above = perfil in ("admin", "admin_global")
    u.is_supervisor_or_above = perfil in ("supervisor", "admin", "admin_global")
    u.is_gestor_only = False
    return u


def _make_chamado_mock(data=None, **attrs):
    """MagicMock que imita o retorno de Chamado.get_by_id(): to_dict() + atributos
    usados diretamente pelo service (area/status/confirmacao_solicitante/...)."""
    data = data if data is not None else _default_data()
    m = MagicMock()
    m.to_dict.return_value = data
    m.area = data.get("area")
    m.status = data.get("status")
    m.confirmacao_solicitante = data.get("confirmacao_solicitante")
    m.numero_chamado = data.get("numero_chamado")
    m.categoria = data.get("categoria")
    m.tipo_solicitacao = data.get("tipo_solicitacao")
    m.solicitante_nome = data.get("solicitante_nome")
    m.atualizar_campos.return_value = True
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ── Guardas de entrada ─────────────────────────────────────────────────────────


def test_processar_edicao_sem_chamado_id_retorna_erro(app):
    """processar_edicao_chamado com chamado_id vazio retorna sucesso=False."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    with app.app_context():
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert "required" in result.get("erro", "").lower()


def test_processar_edicao_chamado_nao_encontrado_retorna_404(app):
    """processar_edicao_chamado com chamado inexistente retorna sucesso=False e codigo 404."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = None
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch_inexistente",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 404


def test_processar_edicao_supervisor_sem_permissao_retorna_403(app):
    """processar_edicao_chamado com supervisor fora da área retorna sucesso=False e codigo 403."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    supervisor = _make_usuario(perfil="supervisor", uid="sup1", areas=["Qualidade"])

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=False),
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        result = processar_edicao_chamado(
            usuario_atual=supervisor,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 403


def test_processar_edicao_supervisor_observador_fora_da_area_retorna_403(app):
    """Regressão: supervisor que só enxerga o chamado como OBSERVADOR (cc), fora da
    própria área, não pode editar via processar_edicao_chamado.

    A checagem de escrita usava usuario_pode_ver_chamado (leitura) em vez de
    supervisor_pode_alterar_chamado (escrita, só área — já existia em
    permissoes_edicao_chamado.py mas nunca era chamada daqui). Isso deixava qualquer
    supervisor adicionado como observador/cc num chamado de OUTRA área com acesso
    total de edição (mudar status, reatribuir responsável, setores, SLA) — não só
    visibilidade passiva como o recurso "Em cópia" promete.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    supervisor_observador = _make_usuario(perfil="supervisor", uid="sup_obs", areas=["Qualidade"])

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        # Simula o que usuario_pode_ver_chamado retorna de verdade pra um observador:
        # True (ele pode VER o chamado por estar em cópia), mesmo fora da área.
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock(
            area="Manutencao"  # fora das áreas do supervisor
        )
        mock_status.return_value = {"sucesso": True, "mensagem": "Status atualizado"}

        result = processar_edicao_chamado(
            usuario_atual=supervisor_observador,
            chamado_id="ch_obs",
            novo_status="Concluído",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 403


# ── Congelamento (Nível 1 / Nível 2) ──────────────────────────────────────────


def test_processar_edicao_concluido_pendente_retorna_403(app):
    """Chamado Concluído aguardando confirmação → processar_edicao retorna 403 para admin."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    admin = _make_usuario(perfil="admin")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock(
            data={**_default_data(), "status": "Concluído", "confirmacao_solicitante": "pendente"},
            status="Concluído",
            confirmacao_solicitante="pendente",
        )

        result = processar_edicao_chamado(
            usuario_atual=admin,
            chamado_id="ch_conc",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Nova descrição",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 403


def test_processar_edicao_concluido_confirmado_retorna_403(app):
    """Chamado Concluído e confirmado → processar_edicao retorna 403 para qualquer perfil."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    sup = _make_usuario(perfil="supervisor")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock(
            status="Concluído", confirmacao_solicitante="confirmado", area="Manutencao"
        )

        result = processar_edicao_chamado(
            usuario_atual=sup,
            chamado_id="ch_conf",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Tentativa de editar descrição",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert result.get("codigo") == 403


# ── Sem alterações ─────────────────────────────────────────────────────────────


def test_processar_edicao_sem_alteracoes_retorna_sucesso(app):
    """processar_edicao_chamado sem alterações retorna sucesso=True e mensagem no_changes_made."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True


# ── Mudança de status ──────────────────────────────────────────────────────────


def test_processar_edicao_muda_status_com_sucesso(app):
    """processar_edicao_chamado altera status quando válido e diferente do atual."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        mock_status.return_value = {"sucesso": True, "mensagem": "Status atualizado"}
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Em Atendimento",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    mock_status.assert_called_once()


def test_processar_edicao_cancelamento_sem_motivo_retorna_erro(app):
    """processar_edicao_chamado retorna erro ao cancelar sem motivo."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Cancelado",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert "reason" in result.get("erro", "").lower() or "cancel" in result.get("erro", "").lower()


def test_processar_edicao_cancelamento_com_motivo_chama_status(app):
    """processar_edicao_chamado cancela corretamente quando motivo é fornecido."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        mock_status.return_value = {"sucesso": True, "mensagem": "Cancelado"}
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Cancelado",
            motivo_cancelamento="Duplicado",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    kwargs = mock_status.call_args.kwargs
    assert kwargs.get("motivo_cancelamento") == "Duplicado"


def test_processar_edicao_cancelamento_motivo_com_caractere_especial_nao_fica_escapado(app):
    """Regressão: bleach.clean() já retorna texto HTML-escapado ("->"" vira "-&gt;"") — sem
    desfazer esse escaping antes de salvar, o template (autoescape do Jinja) escapa de novo e
    o usuário vê "&gt;" literal na tela em vez de ">"."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        mock_status.return_value = {"sucesso": True, "mensagem": "Cancelado"}
        processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="Cancelado",
            motivo_cancelamento="Duplicado do chamado a->b",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    kwargs = mock_status.call_args.kwargs
    assert kwargs.get("motivo_cancelamento") == "Duplicado do chamado a->b"


# ── SLA ───────────────────────────────────────────────────────────────────────


def test_processar_edicao_sla_invalido_retorna_erro(app):
    """processar_edicao_chamado retorna erro para SLA fora do range 1-365."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="999",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is False
    assert "sla" in result.get("erro", "").lower()


def test_processar_edicao_sla_zero_reseta_para_padrao(app):
    """processar_edicao_chamado com sla_str='0' zera o campo sla_dias (None, sem sentinela Firestore)."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _make_chamado_mock(data={**_default_data(), "sla_dias": 7})
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="0",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert update_data.get("sla_dias") is None


# ── Descrição ─────────────────────────────────────────────────────────────────


def test_processar_edicao_nova_descricao_diferente_salva(app):
    """processar_edicao_chamado com descrição diferente adiciona ao update_data."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _make_chamado_mock()
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Nova descrição completamente diferente",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    mock_chamado.atualizar_campos.assert_called_once()
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert "descricao" in update_data


def test_processar_edicao_nova_descricao_com_caractere_especial_nao_fica_escapada(app):
    """Regressão: bleach.clean() já retorna texto HTML-escapado ("->"" vira "-&gt;"") — sem
    desfazer esse escaping antes de salvar, o template (autoescape do Jinja) escapa de novo e
    o usuário vê "&gt;" literal na tela em vez de ">"."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _make_chamado_mock()
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Fluxo a->b corrigido",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert update_data.get("descricao") == "Fluxo a->b corrigido"


# ── Responsável ───────────────────────────────────────────────────────────────


def test_processar_edicao_novo_responsavel_atualiza_dados(app):
    """processar_edicao_chamado com novo responsável válido atualiza responsavel e area."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    novo_resp = MagicMock()
    novo_resp.id = "resp2"
    novo_resp.nome = "Novo Responsavel"
    novo_resp.areas = ["Elétrica"]
    novo_resp.area = "Elétrica"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Usuario") as mock_usuario_cls,
    ):
        mock_chamado = _make_chamado_mock()
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        mock_usuario_cls.get_by_id.return_value = novo_resp
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="resp2",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )
    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert update_data.get("responsavel") == "Novo Responsavel"


def test_edicao_troca_responsavel_atualiza_supervisor_ids_com_acesso(app):
    """Lacuna 4: trocar responsável deve recalcular supervisor_ids_com_acesso no update_data."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    novo_resp = MagicMock()
    novo_resp.id = "resp2"
    novo_resp.nome = "Novo Responsavel"
    novo_resp.areas = ["Manutencao"]
    novo_resp.area = "Manutencao"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Usuario") as mock_usuario_cls,
        patch(
            "app.services.edicao_chamado_service.calcular_supervisor_ids_com_acesso",
            return_value=["resp2"],
        ) as mock_calc,
    ):
        mock_chamado = _make_chamado_mock()
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        mock_usuario_cls.get_by_id.return_value = novo_resp
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="resp2",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert "supervisor_ids_com_acesso" in update_data
    assert update_data["supervisor_ids_com_acesso"] == ["resp2"]
    mock_calc.assert_called_once()


# ── Setores adicionais ────────────────────────────────────────────────────────


def test_processar_edicao_setores_adicionais_dispara_notificacao(app):
    """processar_edicao_chamado com novo setor adicional dispara thread de notificação."""

    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.threading") as mock_threading,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()  # setores_adicionais = []
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=["Elétrica"],
        )
    assert result["sucesso"] is True
    assert mock_threading.Thread.call_count >= 1


# ── Multi-anexo em edição (TDD RED → GREEN) ───────────────────────────────────


def _arq(nome: str):
    f = MagicMock()
    f.filename = nome
    return f


def _base_patches(mock_chamado_cls, data=None):
    """Configura o mock de Chamado comum nos testes de anexo. Retorna o mock
    do Chamado (para inspecionar atualizar_campos.call_args depois)."""
    mock_chamado = _make_chamado_mock(data=data)
    mock_chamado_cls.get_by_id.return_value = mock_chamado
    return mock_chamado


def test_edicao_aceita_arquivos_novos_como_lista(app):
    """
    RED: processar_edicao_chamado deve aceitar 'arquivos_novos' (list) no lugar de
    'arquivo_anexo'. Dois arquivos enviados → ambos salvos e adicionados ao chamado.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    a1, a2 = _arq("relatorio.pdf"), _arq("foto.png")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:relatorio.pdf", "r2:foto.png"],
        ) as mock_salvar,
    ):
        mock_chamado = _base_patches(mock_chamado_cls)
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[a1, a2],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    assert mock_salvar.call_count == 2
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert "r2:relatorio.pdf" in update_data.get("anexos", [])
    assert "r2:foto.png" in update_data.get("anexos", [])


def test_edicao_lista_vazia_nao_altera_anexos(app):
    """
    arquivos_novos=[] não deve modificar a lista de anexos existente.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.salvar_anexo") as mock_salvar,
    ):
        _base_patches(mock_chamado_cls)
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    mock_salvar.assert_not_called()


def test_edicao_falha_em_um_arquivo_retorna_erro_sem_persistir(app):
    """
    Se salvar_anexo levantar ValueError em qualquer arquivo da lista,
    retorna erro e não persiste o chamado (atualizar_campos não chamado).
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    a1, a2 = _arq("bom.pdf"), _arq("mal.exe")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:bom.pdf", ValueError("Extensão não permitida")],
        ),
    ):
        mock_chamado = _base_patches(mock_chamado_cls)
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[a1, a2],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is False
    assert (
        "extensão" in result.get("erro", "").lower()
        or "permitida" in result.get("erro", "").lower()
    )
    mock_chamado.atualizar_campos.assert_not_called()


def test_edicao_historico_criado_por_arquivo_adicionado(app):
    """
    Para cada arquivo salvo com sucesso, deve haver um registro no histórico
    com campo_alterado='novo anexo' — verificado via Historico.salvar_lote(),
    chamado uma única vez com a lista completa (N writes → 1 round-trip).
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    a1, a2 = _arq("doc1.pdf"), _arq("doc2.xlsx")

    class _FakeHistorico:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:doc1.pdf", "r2:doc2.xlsx"],
        ),
        patch(
            "app.services.edicao_chamado_service.Historico", side_effect=_FakeHistorico
        ) as mock_historico_cls,
    ):
        _base_patches(mock_chamado_cls)

        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[a1, a2],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    mock_historico_cls.salvar_lote.assert_called_once()
    historico_pendente = mock_historico_cls.salvar_lote.call_args.args[0]
    anexo_entries = [
        h for h in historico_pendente if h._kwargs.get("campo_alterado") == "novo anexo"
    ]
    assert len(anexo_entries) == 2


# ── F-25: Truncar nova_descricao em 3000 chars antes de salvar ────────────────


def _data_f25():
    return {
        "numero_chamado": "CHM-F25",
        "status": "Aberto",
        "descricao": "desc curta",
        "responsavel": "Resp",
        "responsavel_id": "r1",
        "area": "Manutencao",
        "sla_dias": None,
        "anexo": None,
        "anexos": [],
        "setores_adicionais": [],
        "categoria": "Manutencao",
        "tipo_solicitacao": "Corretiva",
        "solicitante_nome": "Sol",
    }


def test_processar_edicao_descricao_acima_de_3000_chars_e_truncada(app):
    """F-25: nova_descricao com > 3000 chars deve ser salva com no máximo 3000 chars."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    descricao_longa = "x" * 4000

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _base_patches(mock_chamado_cls, data=_data_f25())
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch_f25",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao=descricao_longa,
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert "descricao" in update_data
    assert len(update_data["descricao"]) <= 3000


def test_supervisor_nao_pode_editar_descricao_do_solicitante(app):
    """Supervisor tentando alterar a descrição original do solicitante → 403.

    Anexos já eram protegidos (só permitiam adicionar, nunca remover/substituir);
    a descrição era o único campo escrito pelo solicitante que o supervisor ainda
    conseguia sobrescrever livremente.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    sup = _make_usuario(perfil="supervisor", uid="sup1", areas=["Manutencao"])

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _make_chamado_mock(
            status="Aberto", confirmacao_solicitante=None, area="Manutencao"
        )
        mock_chamado_cls.get_by_id.return_value = mock_chamado

        result = processar_edicao_chamado(
            usuario_atual=sup,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Descrição alterada pelo supervisor",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is False
    assert result.get("codigo") == 403
    mock_chamado.atualizar_campos.assert_not_called()


def test_admin_ainda_pode_editar_descricao_do_solicitante(app):
    """Admin continua podendo editar a descrição (válvula de escape administrativa)."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    admin = _make_usuario(perfil="admin")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _base_patches(mock_chamado_cls)

        result = processar_edicao_chamado(
            usuario_atual=admin,
            chamado_id="ch1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Descrição corrigida pelo admin",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert update_data.get("descricao") == "Descrição corrigida pelo admin"


def test_supervisor_pode_editar_outros_campos_sem_tocar_descricao(app):
    """Supervisor continua podendo mudar status/responsável/SLA sem mexer na descrição."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    sup = _make_usuario(perfil="supervisor", uid="sup1", areas=["Manutencao"])

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
    ):
        mock_chamado = _make_chamado_mock(
            status="Aberto", confirmacao_solicitante=None, area="Manutencao"
        )
        mock_chamado_cls.get_by_id.return_value = mock_chamado
        mock_status.return_value = {"sucesso": True, "mensagem": "Status atualizado"}

        result = processar_edicao_chamado(
            usuario_atual=sup,
            chamado_id="ch1",
            novo_status="Em Atendimento",
            motivo_cancelamento="",
            nova_descricao="",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    mock_status.assert_called_once()


def test_processar_edicao_descricao_menor_que_3000_nao_e_alterada(app):
    """F-25: nova_descricao com <= 3000 chars deve ser salva sem truncamento."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    descricao_normal = "Descrição de teste com tamanho normal"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _base_patches(mock_chamado_cls, data=_data_f25())
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch_f25b",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao=descricao_normal,
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert update_data.get("descricao") == descricao_normal


# ── Fase 7 — Regressão: deadline imutável ────────────────────────────────────


def test_edicao_descricao_nao_altera_data_em_atendimento(app):
    """Fase 7 regressão: editar descrição NÃO deve incluir data_em_atendimento no update.

    Garante que o deadline de resolução (calculado a partir de data_em_atendimento)
    não seja alterado acidentalmente por edições de campos de texto.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado = _base_patches(mock_chamado_cls, data=_data_f25())
        result = processar_edicao_chamado(
            usuario_atual=u,
            chamado_id="ch_reg_1",
            novo_status="",
            motivo_cancelamento="",
            nova_descricao="Descrição atualizada para teste de regressão",
            novo_responsavel_id="",
            novo_sla_str="",
            arquivos_novos=[],
            setores_adicionais_lista=[],
        )

    assert result["sucesso"] is True
    update_data = mock_chamado.atualizar_campos.call_args.kwargs
    assert "data_em_atendimento" not in update_data


# ── responder_chamado_supervisor — resposta em texto livre ao solicitante ──────


def test_responder_supervisor_com_permissao_sucede(app):
    """Supervisor/admin da área + chamado não congelado + mensagem válida → sucesso + histórico."""
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Historico") as mock_hist,
        patch("app.services.edicao_chamado_service._notificar_resposta_supervisor"),
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        mock_hist.return_value.save.return_value = True

        resultado = responder_chamado_supervisor(
            chamado_id="ch1",
            mensagem="Já verificamos o equipamento, aguardando a peça chegar.",
            usuario=u,
        )

    assert resultado["sucesso"] is True
    mock_hist.return_value.save.assert_called_once()


def test_responder_supervisor_chamado_nao_encontrado_retorna_404(app):
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = None
        resultado = responder_chamado_supervisor("ch_x", "Resposta válida", u)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 404


def test_responder_supervisor_sem_permissao_area_retorna_403(app):
    """Supervisor fora da área do chamado não pode responder."""
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    supervisor = _make_usuario(perfil="supervisor", uid="sup1", areas=["Qualidade"])

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()  # area="Manutencao"
        resultado = responder_chamado_supervisor("ch1", "Resposta qualquer", supervisor)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403


def test_responder_supervisor_chamado_congelado_retorna_403(app):
    """Chamado Concluído e confirmado (congelado) bloqueia resposta."""
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()
    data = _default_data()
    data["status"] = "Concluído"
    data["confirmacao_solicitante"] = "confirmado"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock(data)
        resultado = responder_chamado_supervisor("ch1", "Resposta qualquer", u)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403


def test_responder_supervisor_chamado_cancelado_retorna_403(app):
    """Chamado Cancelado bloqueia resposta do responsável — alinhado com o lado
    solicitante (solicitante_edicao_service._STATUS_PERMITIDOS_RESPOSTA), que já
    não permite responder num chamado cancelado. Sem isso, o responsável podia
    mandar mensagem sem o solicitante ter como responder de volta."""
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()
    data = _default_data()
    data["status"] = "Cancelado"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock(data)
        resultado = responder_chamado_supervisor("ch1", "Resposta qualquer", u)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 403


def test_responder_supervisor_mensagem_vazia_retorna_400(app):
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        resultado = responder_chamado_supervisor("ch1", "   ", u)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 400


def test_responder_supervisor_sucesso_dispara_notificacao(app):
    """Após sucesso, _notificar_resposta_supervisor deve ser chamado."""
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Historico") as mock_hist,
        patch("app.services.edicao_chamado_service._notificar_resposta_supervisor") as mock_notif,
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        mock_hist.return_value.save.return_value = True

        responder_chamado_supervisor("ch1", "Resposta enviada ao solicitante.", u)

    mock_notif.assert_called_once()
    assert mock_notif.call_args.kwargs["mensagem"] == "Resposta enviada ao solicitante."


def test_responder_supervisor_excecao_retorna_500(app):
    from app.services.edicao_chamado_service import responder_chamado_supervisor

    u = _make_usuario()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.Historico",
            side_effect=RuntimeError("boom"),
        ),
    ):
        mock_chamado_cls.get_by_id.return_value = _make_chamado_mock()
        resultado = responder_chamado_supervisor("ch1", "Resposta válida", u)

    assert resultado["sucesso"] is False
    assert resultado.get("codigo") == 500
