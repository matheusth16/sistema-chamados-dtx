"""
Testes unitários do serviço de notificações in-app (notifications_inapp.py).
Cobre: criar_notificacao, listar_para_usuario, contar_nao_lidas,
marcar_como_lida, marcar_todas_como_lidas, localizar_notificacao.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

# ── criar_notificacao ──────────────────────────────────────────────────────────


def test_criar_notificacao_retorna_id_quando_firestore_ok():
    """criar_notificacao retorna o ID do documento criado quando Firestore responde OK."""
    from app.services.notifications_inapp import criar_notificacao

    mock_ref = MagicMock()
    mock_ref.id = "notif_abc123"
    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        result = criar_notificacao(
            "user1", "ch1", "CHM-001", "Novo chamado", "Descrição", "novo_chamado"
        )

    assert result == "notif_abc123"


def test_criar_notificacao_retorna_none_sem_chamado_id():
    """criar_notificacao retorna None quando chamado_id é vazio."""
    from app.services.notifications_inapp import criar_notificacao

    result = criar_notificacao("user1", "", "CHM-001", "Título", "Msg")
    assert result is None


def test_criar_notificacao_retorna_none_quando_firestore_falha():
    """criar_notificacao captura exceção do Firestore e retorna None."""
    from app.services.notifications_inapp import criar_notificacao

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.add.side_effect = Exception("Firestore down")
        result = criar_notificacao("user1", "ch1", "CHM-001", "Título", "Msg")

    assert result is None


# ── listar_para_usuario ────────────────────────────────────────────────────────


def test_listar_para_usuario_retorna_docs_ordenados_por_data():
    """listar_para_usuario retorna lista de dicts com data_criacao serializado, mais recente primeiro."""
    from app.services.notifications_inapp import listar_para_usuario

    # doc2 mais recente — Firestore retorna em DESC por data_criacao
    doc2 = MagicMock()
    doc2.id = "n2"
    doc2.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch2",
        "numero_chamado": "CHM-002",
        "titulo": "Notif 2",
        "mensagem": "Mensagem 2",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 3, 21, 10, 0, 0),
    }

    doc1 = MagicMock()
    doc1.id = "n1"
    doc1.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "Notif 1",
        "mensagem": "Mensagem 1",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 3, 20, 10, 0, 0),
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        # Suporta encadeamento: .where(...).order_by(...).limit(...).stream()
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc2, doc1]
        result = listar_para_usuario("u1")

    assert len(result) == 2
    # Mais recente primeiro (Firestore retorna na ordem correta via order_by DESC)
    assert result[0]["id"] == "n2"
    assert result[1]["id"] == "n1"


def test_listar_para_usuario_apenas_nao_lidas():
    """listar_para_usuario com apenas_nao_lidas=True adiciona filtro na query."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = []
        listar_para_usuario("u1", apenas_nao_lidas=True)

    # Verifica que .where foi chamado duas vezes (usuario_id + lida==False)
    assert mock_db.collection.return_value.where.call_count >= 1
    assert mock_query.where.call_count >= 1


def test_listar_para_usuario_usa_order_by_data_criacao_desc():
    """listar_para_usuario deve usar order_by(data_criacao DESC) na query Firestore, não sort em memória."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = []
        listar_para_usuario("u1")

    assert mock_query.order_by.called, "listar_para_usuario deve chamar order_by"
    order_by_args = mock_query.order_by.call_args_list[0].args
    assert order_by_args[0] == "data_criacao", "order_by deve ser por data_criacao"


def test_listar_para_usuario_retorna_vazio_quando_firestore_falha():
    """listar_para_usuario retorna [] quando Firestore lança exceção."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("timeout")
        result = listar_para_usuario("u1")

    assert result == []


def test_listar_para_usuario_serializa_data_isoformat():
    """listar_para_usuario serializa data_criacao datetime para string ISO."""
    from app.services.notifications_inapp import listar_para_usuario

    doc = MagicMock()
    doc.id = "n1"
    doc.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "T",
        "mensagem": "M",
        "tipo": "novo",
        "lida": False,
        "data_criacao": datetime(2026, 1, 1, 12, 0, 0),
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc]
        result = listar_para_usuario("u1")

    assert isinstance(result[0]["data_criacao"], str)
    assert "2026" in result[0]["data_criacao"]


# ── contar_nao_lidas ───────────────────────────────────────────────────────────


def test_contar_nao_lidas_retorna_valor_do_firestore():
    """contar_nao_lidas retorna o count retornado pelo Firestore."""
    from app.services.notifications_inapp import contar_nao_lidas

    mock_count_val = MagicMock()
    mock_count_val.value = 5
    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.count.return_value.get.return_value = [[mock_count_val]]
        result = contar_nao_lidas("u1")

    assert result == 5


def test_contar_nao_lidas_retorna_zero_quando_firestore_falha():
    """contar_nao_lidas retorna 0 quando Firestore lança exceção."""
    from app.services.notifications_inapp import contar_nao_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("err")
        result = contar_nao_lidas("u1")

    assert result == 0


# ── marcar_como_lida ───────────────────────────────────────────────────────────


def test_marcar_como_lida_retorna_true_quando_pertence_ao_usuario():
    """marcar_como_lida retorna True quando doc existe e pertence ao usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"usuario_id": "u1"}

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is True
    mock_ref.update.assert_called_once_with({"lida": True})


def test_marcar_como_lida_retorna_false_quando_nao_existe():
    """marcar_como_lida retorna False quando o documento não existe."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = False

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is False


def test_marcar_como_lida_retorna_false_quando_pertence_a_outro_usuario():
    """marcar_como_lida retorna False quando o doc pertence a outro usuário."""
    from app.services.notifications_inapp import marcar_como_lida

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"usuario_id": "outro_usuario"}

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_ref = MagicMock()
        mock_db.collection.return_value.document.return_value = mock_ref
        mock_ref.get.return_value = mock_doc
        result = marcar_como_lida("notif1", "u1")

    assert result is False


def test_marcar_como_lida_retorna_false_quando_firestore_falha():
    """marcar_como_lida retorna False quando Firestore lança exceção."""
    from app.services.notifications_inapp import marcar_como_lida

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("err")
        result = marcar_como_lida("notif1", "u1")

    assert result is False


# ── marcar_todas_como_lidas ────────────────────────────────────────────────────


def test_marcar_todas_como_lidas_retorna_contagem():
    """marcar_todas_como_lidas retorna a quantidade de notificações marcadas."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    doc1 = MagicMock()
    doc2 = MagicMock()

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = [doc1, doc2]
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch
        result = marcar_todas_como_lidas("u1")

    assert result == 2
    mock_batch.commit.assert_called()


def test_marcar_todas_como_lidas_retorna_zero_sem_notificacoes():
    """marcar_todas_como_lidas retorna 0 quando não há notificações não lidas."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.stream.return_value = []
        result = marcar_todas_como_lidas("u1")

    assert result == 0


def test_marcar_todas_como_lidas_retorna_zero_quando_firestore_falha():
    """marcar_todas_como_lidas retorna 0 quando Firestore lança exceção."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_db.collection.return_value.where.side_effect = Exception("err")
        result = marcar_todas_como_lidas("u1")

    assert result == 0


def test_listar_serializa_timestamp_com_to_pydatetime():
    """listar_para_usuario serializa timestamp com .to_pydatetime() via branch ISO (linha 75)."""
    from app.services.notifications_inapp import listar_para_usuario

    ts = MagicMock()
    ts.to_pydatetime.return_value = datetime(2026, 6, 1, 10, 0, 0)

    doc = MagicMock()
    doc.id = "n_ts"
    doc.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "T",
        "mensagem": "M",
        "tipo": "novo",
        "lida": False,
        "data_criacao": ts,
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc]
        result = listar_para_usuario("u1")

    assert "2026" in result[0]["data_criacao"]


def test_listar_serializa_timestamp_fallback_str():
    """listar_para_usuario usa str(ts) como fallback quando ts não é datetime nem tem to_pydatetime."""
    from app.services.notifications_inapp import listar_para_usuario

    class OpaqueTsObj:
        def __repr__(self):
            return "ts-opaque"

    doc = MagicMock()
    doc.id = "n_fallback"
    doc.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "T",
        "mensagem": "M",
        "tipo": "novo",
        "lida": False,
        "data_criacao": OpaqueTsObj(),
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value.stream.return_value = [doc]
        result = listar_para_usuario("u1")

    assert result[0]["data_criacao"] is not None


def test_marcar_como_lida_sem_ids_retorna_false():
    """marcar_como_lida retorna False quando notificacao_id ou usuario_id é vazio."""
    from app.services.notifications_inapp import marcar_como_lida

    assert marcar_como_lida("", "u1") is False
    assert marcar_como_lida("n1", "") is False


def test_marcar_todas_sem_usuario_id_retorna_zero():
    """marcar_todas_como_lidas retorna 0 quando usuario_id é vazio."""
    from app.services.notifications_inapp import marcar_todas_como_lidas

    assert marcar_todas_como_lidas("") == 0


# ── fallback quando índice Firestore ausente ───────────────────────────────────


def test_listar_para_usuario_fallback_sem_order_by_quando_indice_falha():
    """Se order_by falhar (ex.: índice não deployado), usa fallback sem order_by e sort em memória."""
    from app.services.notifications_inapp import listar_para_usuario

    doc1 = MagicMock()
    doc1.id = "n1"
    doc1.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch1",
        "numero_chamado": "CHM-001",
        "titulo": "T1",
        "mensagem": "M1",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 1, 1, 8, 0, 0),
    }
    doc2 = MagicMock()
    doc2.id = "n2"
    doc2.to_dict.return_value = {
        "usuario_id": "u1",
        "chamado_id": "ch2",
        "numero_chamado": "CHM-002",
        "titulo": "T2",
        "mensagem": "M2",
        "tipo": "novo_chamado",
        "lida": False,
        "data_criacao": datetime(2026, 1, 2, 10, 0, 0),  # mais recente
    }

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        # order_by chain levanta exceção (índice não deployado)
        mock_query.order_by.return_value.limit.return_value.stream.side_effect = Exception(
            "9 FAILED_PRECONDITION: The query requires an index"
        )
        # Fallback: query sem order_by retorna os 2 docs (ordem aleatória)
        mock_query.limit.return_value.stream.return_value = [doc1, doc2]

        result = listar_para_usuario("u1")

    assert len(result) == 2
    # doc2 (mais recente: 2026-01-02) deve vir primeiro após sort em memória
    assert result[0]["id"] == "n2"
    assert result[1]["id"] == "n1"


def test_listar_para_usuario_fallback_retorna_vazio_se_ambas_queries_falham():
    """Se tanto order_by quanto fallback falharem, retorna [] sem propagar exceção."""
    from app.services.notifications_inapp import listar_para_usuario

    with patch("app.services.notifications_inapp.db") as mock_db:
        mock_query = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_query
        mock_query.order_by.return_value.limit.return_value.stream.side_effect = Exception(
            "index error"
        )
        mock_query.limit.return_value.stream.side_effect = Exception("network error")

        result = listar_para_usuario("u1")

    assert result == []


# ── localizar_notificacao ──────────────────────────────────────────────────────


def test_localizar_notificacao_novo_chamado_em_ingles():
    """Notificação com metadados completos deve ser traduzida para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0006",
        "categoria": "Nao Aplicavel",
        "solicitante_nome": "Matheus Costa",
        "titulo": "Novo chamado: CHM-0006",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "en")
    assert out["titulo"] == "New ticket: CHM-0006"
    assert out["mensagem"] == "Not Applicable · Requester: Matheus Costa"


def test_localizar_notificacao_novo_chamado_em_pt():
    """Notificação com metadados completos em PT deve manter strings PT."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0006",
        "categoria": "Nao Aplicavel",
        "solicitante_nome": "Matheus Costa",
        "titulo": "Novo chamado: CHM-0006",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert out["titulo"] == "Novo chamado: CHM-0006"
    assert "Solicitante: Matheus Costa" in out["mensagem"]


def test_localizar_notificacao_legacy_sem_metadados():
    """Notificações antigas sem campos categoria/solicitante_nome devem usar fallback parser."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "novo_chamado",
        "numero_chamado": "CHM-0005",
        "titulo": "Novo chamado: CHM-0005",
        "mensagem": "Nao Aplicavel · Solicitante: Matheus Costa",
    }
    out = localizar_notificacao(doc, "en")
    assert "New ticket" in out["titulo"]
    assert "Requester" in out["mensagem"]
    assert "Not Applicable" in out["mensagem"]


def test_localizar_notificacao_tipo_desconhecido_nao_altera():
    """Tipos que não sejam novo_chamado devem retornar doc sem modificações."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "outro_tipo",
        "titulo": "Algum título",
        "mensagem": "Alguma mensagem",
    }
    out = localizar_notificacao(doc, "en")
    assert out["titulo"] == "Algum título"
    assert out["mensagem"] == "Alguma mensagem"


# ── Novos tipos — solicitante ──────────────────────────────────────────────────


def test_localizar_status_em_atendimento_en():
    """localizar_notificacao traduz tipo status_em_atendimento para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_em_atendimento",
        "numero_chamado": "CHM-010",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-010" in out["titulo"]
    assert "in progress" in out["titulo"].lower()
    assert "being handled" in out["mensagem"].lower()


def test_localizar_status_em_atendimento_pt():
    """localizar_notificacao traduz tipo status_em_atendimento para pt_BR."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_em_atendimento",
        "numero_chamado": "CHM-010",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert "CHM-010" in out["titulo"]
    assert "atendimento" in out["titulo"].lower()


def test_localizar_status_concluido_confirmar_en():
    """localizar_notificacao traduz tipo status_concluido_confirmar para EN."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "status_concluido_confirmar",
        "numero_chamado": "CHM-020",
        "categoria": "Manutencao",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "CHM-020" in out["titulo"]
    assert "completed" in out["titulo"].lower()
    assert "confirm" in out["mensagem"].lower()


def test_localizar_lembrete_confirmacao_1_en():
    """localizar_notificacao traduz tipo lembrete_confirmacao_1 para EN com n=1."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_1",
        "numero_chamado": "CHM-030",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "1" in out["titulo"]
    assert "reminder" in out["titulo"].lower()
    assert "CHM-030" in out["titulo"]
    assert "confirmation" in out["mensagem"].lower()


def test_localizar_lembrete_confirmacao_2_en():
    """localizar_notificacao traduz tipo lembrete_confirmacao_2 para EN com n=2."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_2",
        "numero_chamado": "CHM-031",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "en")
    assert "2" in out["titulo"]
    assert "reminder" in out["titulo"].lower()


def test_localizar_lembrete_confirmacao_1_pt():
    """localizar_notificacao traduz tipo lembrete_confirmacao_1 para pt_BR."""
    from app.services.notifications_inapp import localizar_notificacao

    doc = {
        "tipo": "lembrete_confirmacao_1",
        "numero_chamado": "CHM-032",
        "categoria": "TI",
        "titulo": "fallback",
        "mensagem": "fallback",
    }
    out = localizar_notificacao(doc, "pt_BR")
    assert "Lembrete" in out["titulo"]
    assert "1" in out["titulo"]


# ── texto_notificacao_status_solicitante ───────────────────────────────────────


def test_texto_status_solicitante_em_atendimento_en():
    """texto_notificacao_status_solicitante retorna título e msg EN para em_atendimento."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099", categoria="TI", tipo_evento="status_em_atendimento", language="en"
    )
    assert "CHM-099" in titulo
    assert "in progress" in titulo.lower()
    assert "being handled" in mensagem.lower()


def test_texto_status_solicitante_concluido_confirmar_pt():
    """texto_notificacao_status_solicitante retorna título e msg pt_BR para concluido_confirmar."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099",
        categoria="TI",
        tipo_evento="status_concluido_confirmar",
        language="pt_BR",
    )
    assert "concluído" in titulo.lower()
    assert "confirme" in titulo.lower() or "confirmação" in mensagem.lower()


def test_texto_status_solicitante_lembrete_en():
    """texto_notificacao_status_solicitante retorna texto correto para lembrete #2."""
    from app.services.notifications_inapp import texto_notificacao_status_solicitante

    titulo, mensagem = texto_notificacao_status_solicitante(
        numero="CHM-099",
        categoria="TI",
        tipo_evento="lembrete_confirmacao",
        language="en",
        numero_lembrete=2,
    )
    assert "2" in titulo
    assert "reminder" in titulo.lower()
    assert "confirmation" in mensagem.lower()


# ── criar_notificacao_solicitante ──────────────────────────────────────────────


def test_criar_notificacao_solicitante_chama_criar_notificacao():
    """criar_notificacao_solicitante delega para criar_notificacao com dados corretos."""
    from unittest.mock import patch

    from app.services.notifications_inapp import criar_notificacao_solicitante

    with patch("app.services.notifications_inapp.criar_notificacao") as mock_criar:
        mock_criar.return_value = "notif_xyz"
        result = criar_notificacao_solicitante(
            solicitante_id="sol1",
            chamado_id="ch1",
            numero_chamado="CHM-001",
            categoria="TI",
            tipo="status_em_atendimento",
            language="en",
        )

    assert result == "notif_xyz"
    mock_criar.assert_called_once()
    call_kwargs = mock_criar.call_args
    assert call_kwargs.kwargs["tipo"] == "status_em_atendimento"
    assert call_kwargs.kwargs["usuario_id"] == "sol1"


def test_criar_notificacao_solicitante_lembrete_1_usa_tipo_correto():
    """criar_notificacao_solicitante usa tipo 'lembrete_confirmacao_1'."""
    from unittest.mock import patch

    from app.services.notifications_inapp import criar_notificacao_solicitante

    with patch("app.services.notifications_inapp.criar_notificacao") as mock_criar:
        mock_criar.return_value = "notif_l1"
        criar_notificacao_solicitante(
            solicitante_id="sol1",
            chamado_id="ch1",
            numero_chamado="CHM-001",
            categoria="TI",
            tipo="lembrete_confirmacao_1",
            language="en",
        )

    call_kwargs = mock_criar.call_args
    assert call_kwargs.kwargs["tipo"] == "lembrete_confirmacao_1"


def test_criar_notificacao_solicitante_retorna_none_sem_ids():
    """criar_notificacao_solicitante retorna None quando solicitante_id vazio."""
    from app.services.notifications_inapp import criar_notificacao_solicitante

    result = criar_notificacao_solicitante(
        solicitante_id="",
        chamado_id="ch1",
        numero_chamado="CHM-001",
        categoria="TI",
        tipo="status_em_atendimento",
    )
    assert result is None
