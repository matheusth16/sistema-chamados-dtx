"""
Testes unitários do serviço de listagem de chamados.
Cobre: _eh_erro_indice_firestore, listar_meus_chamados_fallback, listar_meus_chamados.
"""

from unittest.mock import MagicMock, patch

# ── _eh_erro_indice_firestore ──────────────────────────────────────────────────


def test_eh_erro_indice_firestore_detecta_failed_precondition():
    """Reconhece FAILED_PRECONDITION como erro de índice."""
    from app.services.chamados_listagem_service import _eh_erro_indice_firestore

    exc = Exception("FAILED_PRECONDITION: index required")
    assert _eh_erro_indice_firestore(exc) is True


def test_eh_erro_indice_firestore_detecta_requires_an_index():
    """Reconhece 'requires an index' como erro de índice."""
    from app.services.chamados_listagem_service import _eh_erro_indice_firestore

    exc = Exception("query requires an index")
    assert _eh_erro_indice_firestore(exc) is True


def test_eh_erro_indice_firestore_nao_detecta_erro_generico():
    """Não trata erro genérico como erro de índice."""
    from app.services.chamados_listagem_service import _eh_erro_indice_firestore

    exc = Exception("network timeout")
    assert _eh_erro_indice_firestore(exc) is False


# ── listar_meus_chamados_fallback ───────────────────────────────────────────────


def _make_doc(chamado_id, data_dict):
    """Cria MagicMock de doc Firestore."""
    doc = MagicMock()
    doc.id = chamado_id
    doc.to_dict.return_value = data_dict
    return doc


def test_fallback_retorna_lista_vazia_quando_sem_docs():
    """Fallback com lista vazia retorna chamados=[] e total_chamados=0."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
        result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["chamados"] == []
    assert result["total_chamados"] == 0
    assert result["pagina_atual"] == 1
    assert result["total_paginas"] == 1
    assert result["cursor_next"] is None
    assert result["cursor_prev"] is None


def test_fallback_filtra_por_status():
    """Fallback filtra docs pelo status informado."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc_aberto = _make_doc("c1", {"status": "Aberto", "solicitante_id": "u1", "prioridade": 1})
    doc_concluido = _make_doc(
        "c2", {"status": "Concluído", "solicitante_id": "u1", "prioridade": 1}
    )

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc_aberto,
            doc_concluido,
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "Aberto", 10, 1)

    assert result["total_chamados"] == 1


def test_fallback_filtra_por_rl_codigo():
    """Fallback filtra docs pelo rl_codigo informado."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc_rl = _make_doc(
        "c1", {"status": "Aberto", "rl_codigo": "RL-001", "solicitante_id": "u1", "prioridade": 1}
    )
    doc_sem_rl = _make_doc(
        "c2", {"status": "Aberto", "rl_codigo": "RL-002", "solicitante_id": "u1", "prioridade": 1}
    )

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc_rl,
            doc_sem_rl,
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="RL-001", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 1, rl_codigo="RL-001")

    assert result["total_chamados"] == 1


def test_fallback_status_counts_corretos():
    """Fallback conta corretamente chamados por status."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    docs = [
        _make_doc("c1", {"status": "Aberto", "prioridade": 1}),
        _make_doc("c2", {"status": "Aberto", "prioridade": 1}),
        _make_doc("c3", {"status": "Concluído", "prioridade": 1}),
    ]

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = docs
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["status_counts"]["Aberto"] == 2
    assert result["status_counts"]["Concluído"] == 1
    assert result["status_counts"]["Em Atendimento"] == 0
    assert result["status_counts"]["Cancelado"] == 0


def test_fallback_paginacao_pagina_2():
    """Fallback com 15 itens e 10 por página retorna pagina_atual=2 no segundo acesso."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(15)]

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = docs
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 2)

    assert result["pagina_atual"] == 2
    assert result["total_paginas"] == 2
    assert result["total_chamados"] == 15
    assert result["cursor_prev"] is not None


def test_fallback_cursor_next_quando_ha_mais_paginas():
    """Fallback retorna cursor_next quando há mais páginas."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(11)]

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = docs
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["cursor_next"] is not None


def test_fallback_ignora_doc_com_data_invalida():
    """Fallback ignora chamado que gera exceção no from_dict (dados inválidos)."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc_valido = _make_doc("c1", {"status": "Aberto", "prioridade": 1})
    doc_invalido = _make_doc("c2", {"status": "Aberto", "prioridade": 1})

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc_valido,
            doc_invalido,
        ]

        chamado_mock = MagicMock(rl_codigo="", prioridade=1)

        def from_dict_side_effect(data, doc_id):
            if doc_id == "c2":
                raise ValueError("dado inválido")
            return chamado_mock

        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.side_effect = from_dict_side_effect
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert len(result["chamados"]) == 1


# ── listar_meus_chamados ───────────────────────────────────────────────────────


def test_listar_meus_chamados_sem_docs_retorna_vazio():
    """listar_meus_chamados sem docs retorna chamados=[] e total=0."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=0),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []
        result = listar_meus_chamados("u1")

    assert result["chamados"] == []
    assert result["total_chamados"] == 0


def test_listar_meus_chamados_com_docs_retorna_lista():
    """listar_meus_chamados com docs retorna lista de chamados."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    doc = _make_doc("c1", {"status": "Aberto", "prioridade": 1, "data_abertura": None})

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=1),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = [doc]
        mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
        result = listar_meus_chamados("u1")

    assert len(result["chamados"]) == 1
    assert result["total_chamados"] == 1


def test_listar_meus_chamados_cursor_invalido_usa_limite_simples():
    """listar_meus_chamados com cursor inválido usa q.limit sem start_after."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=0),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []

        # cursor aponta para um doc que não existe
        mock_cursor_doc = MagicMock()
        mock_cursor_doc.exists = False
        mock_db.collection.return_value.document.return_value.get.return_value = mock_cursor_doc

        result = listar_meus_chamados("u1", cursor="cursor_invalido")

    assert result["chamados"] == []


def test_listar_meus_chamados_tem_proxima_pagina():
    """listar_meus_chamados retorna cursor_next quando há doc extra (n+1)."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(11)]

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=11),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = docs
        mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
        result = listar_meus_chamados("u1", itens_por_pagina=10)

    assert result["cursor_next"] is not None
    assert len(result["chamados"]) == 10
