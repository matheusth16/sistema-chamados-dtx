"""
Testes do serviço de edição de chamados (processar_edicao_chamado).
Segue ciclo TDD: comportamento especificado antes de validar contra o código.
"""

from unittest.mock import MagicMock, patch


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


def _make_doc(exists=True, data=None):
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data or {
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
    return doc


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
    doc_nao_existe = _make_doc(exists=False)

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc_nao_existe
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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=False),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    permission_validation.py mas nunca era chamada daqui). Isso deixava qualquer
    supervisor adicionado como observador/cc num chamado de OUTRA área com acesso
    total de edição (mudar status, reatribuir responsável, setores, SLA) — não só
    visibilidade passiva como o recurso "Em cópia" promete.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    supervisor_observador = _make_usuario(perfil="supervisor", uid="sup_obs", areas=["Qualidade"])
    doc = _make_doc()  # area="Manutencao" — fora das áreas do supervisor

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        # Simula o que usuario_pode_ver_chamado retorna de verdade pra um observador:
        # True (ele pode VER o chamado por estar em cópia), mesmo fora da área.
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado = MagicMock()
        mock_chamado.status = "Aberto"
        mock_chamado.confirmacao_solicitante = None
        mock_chamado.area = "Manutencao"
        mock_chamado_cls.from_dict.return_value = mock_chamado
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
    doc = _make_doc(
        data={
            **_make_doc().to_dict(),
            "status": "Concluído",
            "confirmacao_solicitante": "pendente",
        }
    )

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado = MagicMock()
        mock_chamado.status = "Concluído"
        mock_chamado.confirmacao_solicitante = "pendente"
        mock_chamado_cls.from_dict.return_value = mock_chamado

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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.permissions.usuario_pode_ver_chamado", return_value=True),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado = MagicMock()
        mock_chamado.status = "Concluído"
        mock_chamado.confirmacao_solicitante = "confirmado"
        mock_chamado.area = "Manutencao"
        mock_chamado_cls.from_dict.return_value = mock_chamado

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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.atualizar_status_chamado") as mock_status,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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


# ── SLA ───────────────────────────────────────────────────────────────────────


def test_processar_edicao_sla_invalido_retorna_erro(app):
    """processar_edicao_chamado retorna erro para SLA fora do range 1-365."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    """processar_edicao_chamado com sla_str='0' remove o campo sla_dias."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc(data={**_make_doc().to_dict(), "sla_dias": 7})

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
        patch("firebase_admin.firestore") as mock_fs,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
        mock_fs.DELETE_FIELD = "DELETE"
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


# ── Descrição ─────────────────────────────────────────────────────────────────


def test_processar_edicao_nova_descricao_diferente_salva(app):
    """processar_edicao_chamado com descrição diferente adiciona ao update_data."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    mock_retry.assert_called_once()
    update_data = mock_retry.call_args[0][1]
    assert "descricao" in update_data


# ── Responsável ───────────────────────────────────────────────────────────────


def test_processar_edicao_novo_responsavel_atualiza_dados(app):
    """processar_edicao_chamado com novo responsável válido atualiza responsavel e area."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()
    novo_resp = MagicMock()
    novo_resp.id = "resp2"
    novo_resp.nome = "Novo Responsavel"
    novo_resp.areas = ["Elétrica"]
    novo_resp.area = "Elétrica"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Usuario") as mock_usuario_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    update_data = mock_retry.call_args[0][1]
    assert update_data.get("responsavel") == "Novo Responsavel"


def test_edicao_troca_responsavel_atualiza_supervisor_ids_com_acesso(app):
    """Lacuna 4: trocar responsável deve recalcular supervisor_ids_com_acesso no update_data."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()
    novo_resp = MagicMock()
    novo_resp.id = "resp2"
    novo_resp.nome = "Novo Responsavel"
    novo_resp.areas = ["Manutencao"]
    novo_resp.area = "Manutencao"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.Usuario") as mock_usuario_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
        patch(
            "app.services.edicao_chamado_service.calcular_supervisor_ids_com_acesso",
            return_value=["resp2"],
        ) as mock_calc,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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
    update_data = mock_retry.call_args[0][1]
    assert "supervisor_ids_com_acesso" in update_data
    assert update_data["supervisor_ids_com_acesso"] == ["resp2"]
    mock_calc.assert_called_once()


# ── Setores adicionais ────────────────────────────────────────────────────────


def test_processar_edicao_setores_adicionais_dispara_notificacao(app):
    """processar_edicao_chamado com novo setor adicional dispara thread de notificação."""

    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    doc = _make_doc()  # setores_adicionais = []

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry"),
        patch("app.services.edicao_chamado_service.threading") as mock_threading,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        mock_db.batch.return_value = MagicMock()
        mock_chamado_cls.from_dict.return_value = MagicMock()
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


def _base_patches(mock_db, mock_chamado_cls, doc=None):
    """Configura mocks de DB/Chamado comuns nos testes de anexo."""
    d = doc or _make_doc()
    mock_db.collection.return_value.document.return_value.get.return_value = d
    mock_db.batch.return_value = MagicMock()
    mock_chamado_cls.from_dict.return_value = MagicMock()


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
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:relatorio.pdf", "r2:foto.png"],
        ) as mock_salvar,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        _base_patches(mock_db, mock_chamado_cls)
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
    update_data = mock_retry.call_args[0][1]
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
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.salvar_anexo") as mock_salvar,
    ):
        _base_patches(mock_db, mock_chamado_cls)
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
    retorna erro e não persiste o chamado (execute_with_retry não chamado).
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    a1, a2 = _arq("bom.pdf"), _arq("mal.exe")

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:bom.pdf", ValueError("Extensão não permitida")],
        ),
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        _base_patches(mock_db, mock_chamado_cls)
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
    mock_retry.assert_not_called()


def test_edicao_historico_criado_por_arquivo_adicionado(app):
    """
    Para cada arquivo salvo com sucesso, deve haver um registro no histórico
    com campo_alterado='novo anexo'.
    """
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    a1, a2 = _arq("doc1.pdf"), _arq("doc2.xlsx")

    class _FakeHistorico:
        def __init__(self, **kwargs):
            self._kwargs = kwargs

        def to_dict(self):
            return self._kwargs

    batch_mock = MagicMock()

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch(
            "app.services.edicao_chamado_service.salvar_anexo",
            side_effect=["r2:doc1.pdf", "r2:doc2.xlsx"],
        ),
        patch("app.services.edicao_chamado_service.Historico", side_effect=_FakeHistorico),
        patch("app.services.edicao_chamado_service.execute_with_retry"),
    ):
        _base_patches(mock_db, mock_chamado_cls)
        mock_db.batch.return_value = batch_mock
        mock_db.collection.return_value.document.return_value = MagicMock()

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
    # batch.set deve ser chamado pelo menos 2x (um por arquivo)
    historico_calls = list(batch_mock.set.call_args_list)
    anexo_entries = [
        c
        for c in historico_calls
        if c.args
        and isinstance(c.args[1], dict)
        and c.args[1].get("campo_alterado") == "novo anexo"
    ]
    assert len(anexo_entries) == 2


# ── F-25: Truncar nova_descricao em 3000 chars antes de salvar ────────────────


def _base_patches_for_f25(mock_db, mock_chamado_cls):
    doc = _make_doc(
        data={
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
    )
    mock_db.collection.return_value.document.return_value.get.return_value = doc
    mock_db.batch.return_value = MagicMock()
    mock_chamado_cls.from_dict.return_value = MagicMock()


def test_processar_edicao_descricao_acima_de_3000_chars_e_truncada(app):
    """F-25: nova_descricao com > 3000 chars deve ser salva com no máximo 3000 chars."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    descricao_longa = "x" * 4000

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        _base_patches_for_f25(mock_db, mock_chamado_cls)
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
    update_data = mock_retry.call_args[0][1]
    assert "descricao" in update_data
    assert len(update_data["descricao"]) <= 3000


def test_processar_edicao_descricao_menor_que_3000_nao_e_alterada(app):
    """F-25: nova_descricao com <= 3000 chars deve ser salva sem truncamento."""
    from app.services.edicao_chamado_service import processar_edicao_chamado

    u = _make_usuario()
    descricao_normal = "Descrição de teste com tamanho normal"

    with (
        app.app_context(),
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        _base_patches_for_f25(mock_db, mock_chamado_cls)
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
    update_data = mock_retry.call_args[0][1]
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
        patch("app.services.edicao_chamado_service.db") as mock_db,
        patch("app.services.edicao_chamado_service.Chamado") as mock_chamado_cls,
        patch("app.services.edicao_chamado_service.execute_with_retry") as mock_retry,
    ):
        _base_patches_for_f25(mock_db, mock_chamado_cls)
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
    update_data = mock_retry.call_args[0][1]
    assert "data_em_atendimento" not in update_data
