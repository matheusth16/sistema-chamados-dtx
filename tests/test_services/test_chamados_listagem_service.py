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
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
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
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
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
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
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


def test_listar_meus_chamados_status_counts_cache_hit_evita_queries_extras():
    """Quando cache de status_counts está quente, as 4 queries de aggregation por status não rodam."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    cached_counts = {"Aberto": 3, "Em Atendimento": 1, "Concluído": 5, "Cancelado": 0}
    mock_count = MagicMock(return_value=0)
    mock_q = MagicMock()
    mock_q.where.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.stream.return_value = []

    def cache_get_side(key):
        if "status_counts" in (key or ""):
            return cached_counts
        return None

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", mock_count),
        patch("app.cache.cache_get", side_effect=cache_get_side),
        patch("app.cache.cache_set"),
    ):
        mock_db.collection.return_value.where.return_value = mock_q
        result = listar_meus_chamados("u1", status_filtro="")

    # Cache hit: as 4 queries por status NÃO devem ser executadas
    assert mock_count.call_count <= 1, (
        f"Com cache quente, obter_total_por_contagem chamado {mock_count.call_count}x; "
        "esperado ≤1 (status_counts vem do cache)"
    )
    assert result["status_counts"] == cached_counts


def test_listar_meus_chamados_tem_proxima_pagina():
    """listar_meus_chamados retorna cursor_next quando há doc extra (n+1)."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(11)]

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=11),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
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


# ── F-26: cursor_prev = ID do 1º doc da página quando cursor é usado ──────────


def test_listar_meus_chamados_cursor_prev_e_id_do_primeiro_doc():
    """F-26: quando cursor é usado, cursor_prev deve ser o ID do primeiro doc da página."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(3)]

    cursor_doc = MagicMock()
    cursor_doc.exists = True

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=10),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_col = MagicMock()
        mock_db.collection.return_value = mock_col
        mock_col.where.return_value = mock_q
        mock_col.document.return_value.get.return_value = cursor_doc
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.start_after.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = docs
        mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)

        result = listar_meus_chamados("u1", cursor="prev_cursor_id", itens_por_pagina=10)

    assert result["cursor_prev"] == "c0", (
        f"cursor_prev deve ser ID do primeiro doc (c0), recebeu: {result['cursor_prev']!r}"
    )


# ── Cobertura: linhas 87 e 105 ───────────────────────────────────────────────


def test_fallback_doc_vazio_e_ignorado():
    """Fallback ignora doc cujo to_dict() retorna {} (cobre linha 87 — continue)."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc_vazio = MagicMock()
    doc_vazio.to_dict.return_value = {}

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc_vazio
        ]
        result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["chamados"] == []


def test_fallback_chamado_prioridade_zero_define_grupo_key_projeto():
    """Chamado com prioridade=0 define _grupo_prio[rl]=0 (cobre linha 105)."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc = _make_doc("c1", {"status": "Aberto", "prioridade": 0})

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            c = MagicMock()
            c.rl_codigo = "RL-PROJ"
            c.prioridade = 0
            mock_chamado_cls.from_dict.return_value = c
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["chamados"][0].grupo_key == "0|RL-PROJ"


def test_fallback_chamado_prioridade_menos_um_define_grupo_key_aog():
    """Chamado AOG (prioridade=-1) define _grupo_prio[rl]=-1, acima de Projetos."""
    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    doc = _make_doc("c1", {"status": "Aberto", "prioridade": -1})

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            c = MagicMock()
            c.rl_codigo = "RL-AOG"
            c.prioridade = -1
            mock_chamado_cls.from_dict.return_value = c
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert result["chamados"][0].grupo_key == "-1|RL-AOG"


def test_listar_meus_chamados_sem_cursor_cursor_prev_e_none():
    """F-26: sem cursor (primeira página), cursor_prev deve ser None."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    docs = [_make_doc(f"c{i}", {"status": "Aberto", "prioridade": 1}) for i in range(3)]

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=3),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = docs
        mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)

        result = listar_meus_chamados("u1", itens_por_pagina=10)

    assert result["cursor_prev"] is None


# ── listar_chamados_como_observador (Lacuna F) ────────────────────────────────


class TestListarChamadosComoObservadorFallback:
    """Lacuna F: fallback em memória quando query observadores_ids retorna vazio."""

    def test_fallback_retorna_chamado_quando_query_vazia(self):
        """Query observadores_ids retorna [] → scan memória filtra por observadores[*].usuario_id."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        user_id = "obs_1"
        doc_match = _make_doc(
            "ch1",
            {
                "status": "Aberto",
                "observadores": [{"usuario_id": user_id, "nome": "Obs 1"}],
            },
        )
        doc_no_match = _make_doc(
            "ch2",
            {
                "status": "Aberto",
                "observadores": [{"usuario_id": "outro", "nome": "Outro"}],
            },
        )

        mock_db = MagicMock()
        # observadores_ids query → vazio (fallback acionado)
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
        # scan recente
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            doc_match,
            doc_no_match,
        ]

        with (
            patch("app.services.chamados_listagem_service.db", mock_db),
            patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        ):
            chamado_mock = MagicMock()
            mock_chamado_cls.from_dict.return_value = chamado_mock
            result = listar_chamados_como_observador(user_id)

        assert len(result) == 1
        assert result[0].em_copia is True

    def test_fallback_nao_acionado_quando_query_retorna_docs(self):
        """Query retorna docs → sem fallback, order_by não é chamado."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        doc = _make_doc(
            "ch1",
            {
                "status": "Aberto",
                "observadores": [{"usuario_id": "obs_1"}],
            },
        )

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc
        ]

        with (
            patch("app.services.chamados_listagem_service.db", mock_db),
            patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        ):
            mock_chamado_cls.from_dict.return_value = MagicMock()
            result = listar_chamados_como_observador("obs_1")

        assert len(result) == 1
        mock_db.collection.return_value.order_by.assert_not_called()

    def test_query_array_contains_falha_aciona_fallback(self):
        """Exceção na query observadores_ids (linhas 142-144) força o scan em memória."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        doc_match = _make_doc(
            "ch1",
            {"status": "Aberto", "observadores": [{"usuario_id": "obs_1"}]},
        )

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
            Exception("índice ausente")
        )
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            doc_match
        ]

        with (
            patch("app.services.chamados_listagem_service.db", mock_db),
            patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        ):
            mock_chamado_cls.from_dict.return_value = MagicMock()
            result = listar_chamados_como_observador("obs_1")

        assert len(result) == 1

    def test_scan_fallback_tambem_falha_retorna_lista_vazia(self):
        """Exceção no scan de fallback (linhas 154-156) retorna lista vazia sem propagar erro."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
            Exception("índice ausente")
        )
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.side_effect = Exception(
            "scan falhou"
        )

        with patch("app.services.chamados_listagem_service.db", mock_db):
            result = listar_chamados_como_observador("obs_1")

        assert result == []

    def test_fallback_ignora_doc_invalido_no_from_dict(self):
        """Doc que gera exceção no from_dict (linhas 180-181) é ignorado, não propaga erro."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        doc_invalido = _make_doc(
            "invalido", {"status": "Aberto", "observadores": [{"usuario_id": "obs_1"}]}
        )

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = []
        mock_db.collection.return_value.order_by.return_value.limit.return_value.stream.return_value = [
            doc_invalido,
        ]

        with (
            patch("app.services.chamados_listagem_service.db", mock_db),
            patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        ):
            mock_chamado_cls.from_dict.side_effect = ValueError("dado inválido")
            result = listar_chamados_como_observador("obs_1")

        assert result == []

    def test_doc_com_to_dict_vazio_e_ignorado_no_path_direto(self):
        """Doc com to_dict() vazio (linha 176) é ignorado quando a query direta já retorna docs."""
        from app.services.chamados_listagem_service import listar_chamados_como_observador

        doc_vazio = MagicMock()
        doc_vazio.id = "vazio"
        doc_vazio.to_dict.return_value = {}
        doc_valido = _make_doc(
            "valido", {"status": "Aberto", "observadores": [{"usuario_id": "obs_1"}]}
        )

        mock_db = MagicMock()
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc_vazio,
            doc_valido,
        ]

        with (
            patch("app.services.chamados_listagem_service.db", mock_db),
            patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        ):
            mock_chamado_cls.from_dict.return_value = MagicMock()
            result = listar_chamados_como_observador("obs_1")

        assert len(result) == 1


# ── _data_key (linhas 59-61) ──────────────────────────────────────────────────


def test_data_key_usa_to_pydatetime_quando_disponivel():
    """_data_key converte timestamp do Firestore via to_pydatetime (linha 60)."""
    import datetime

    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    dt_esperado = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    data_mock = MagicMock()
    data_mock.to_pydatetime.return_value = dt_esperado
    doc = _make_doc("c1", {"status": "Aberto", "prioridade": 1, "data_abertura": data_mock})

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert len(result["chamados"]) == 1


def test_data_key_retorna_datetime_puro_sem_to_pydatetime():
    """_data_key retorna o valor bruto quando não tem to_pydatetime (linha 61)."""
    import datetime

    from app.services.chamados_listagem_service import listar_meus_chamados_fallback

    dt_puro = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    doc = _make_doc("c1", {"status": "Aberto", "prioridade": 1, "data_abertura": dt_puro})

    with patch("app.services.chamados_listagem_service.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = [
            doc
        ]
        with patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls:
            mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)
            result = listar_meus_chamados_fallback("u1", "", 10, 1)

    assert len(result["chamados"]) == 1


# ── listar_meus_chamados: filtros status/rl_codigo e branches de erro ────────


def test_listar_meus_chamados_aplica_filtro_status_e_rl(monkeypatch):
    """status_filtro e rl_codigo aplicam .where() extras (linhas 204, 206, 212)."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=0),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []

        result = listar_meus_chamados("u1", status_filtro="Aberto", rl_codigo="RL-1")

    assert result["chamados"] == []
    # .where() extra por status e por rl_codigo (2x no q + 1x no base_ref)
    assert mock_q.where.call_count >= 2


def test_listar_meus_chamados_cache_get_falha_recalcula_status_counts():
    """Exceção em cache_get (linhas 222-223) faz status_counts ser recalculado do zero."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=2),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", side_effect=Exception("cache indisponível")),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []
        mock_chamado_cls.from_dict.return_value = MagicMock(rl_codigo="", prioridade=1)

        result = listar_meus_chamados("u1")

    assert result["total_chamados"] == 2


def test_listar_meus_chamados_cache_set_falha_nao_propaga(monkeypatch):
    """Exceção em cache_set (linhas 251-252) é silenciada, não quebra a listagem."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=0),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set", side_effect=Exception("cache indisponível")),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []

        result = listar_meus_chamados("u1")

    assert result["total_chamados"] == 0


def test_listar_meus_chamados_cursor_get_lanca_excecao_usa_limite_simples():
    """Exceção ao buscar o doc do cursor (linhas 264-266) cai no limite simples sem propagar erro."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=0),
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = []
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception(
            "cursor corrompido"
        )

        result = listar_meus_chamados("u1", cursor="cursor_corrompido")

    assert result["chamados"] == []


def test_listar_meus_chamados_ignora_doc_vazio_e_invalido():
    """Doc sem dados (linha 282) e doc inválido no from_dict (284-285) são ignorados."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    doc_vazio = MagicMock()
    doc_vazio.id = "vazio"
    doc_vazio.to_dict.return_value = {}
    doc_invalido = _make_doc("invalido", {"status": "Aberto", "prioridade": 1})

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=2),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = [doc_vazio, doc_invalido]
        mock_chamado_cls.from_dict.side_effect = ValueError("dado inválido")

        result = listar_meus_chamados("u1")

    assert result["chamados"] == []


def test_listar_meus_chamados_prioridade_zero_define_grupo_projeto():
    """Chamado com prioridade=0 marca _grupo_prio[rl]=0 (linha 294)."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    doc = _make_doc("c1", {"status": "Aberto", "prioridade": 0})

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=1),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = [doc]
        c = MagicMock()
        c.rl_codigo = "RL-PROJ"
        c.prioridade = 0
        mock_chamado_cls.from_dict.return_value = c

        result = listar_meus_chamados("u1")

    assert result["chamados"][0].grupo_key == "0|RL-PROJ"


def test_listar_meus_chamados_prioridade_menos_um_define_grupo_aog():
    """Chamado AOG (prioridade=-1) marca _grupo_prio[rl]=-1, acima de Projetos (linha 294)."""
    from app.services.chamados_listagem_service import listar_meus_chamados

    doc = _make_doc("c1", {"status": "Aberto", "prioridade": -1})

    with (
        patch("app.services.chamados_listagem_service.db") as mock_db,
        patch("app.services.chamados_listagem_service.obter_total_por_contagem", return_value=1),
        patch("app.services.chamados_listagem_service.Chamado") as mock_chamado_cls,
        patch("app.cache.cache_get", return_value=None),
        patch("app.cache.cache_set"),
    ):
        mock_q = MagicMock()
        mock_db.collection.return_value.where.return_value = mock_q
        mock_q.where.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.stream.return_value = [doc]
        c = MagicMock()
        c.rl_codigo = "RL-AOG"
        c.prioridade = -1
        mock_chamado_cls.from_dict.return_value = c

        result = listar_meus_chamados("u1")

    assert result["chamados"][0].grupo_key == "-1|RL-AOG"
