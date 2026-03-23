"""
Testes unitários do modelo GrupoRL.
Cobre: __init__, to_dict, from_dict, get_by_rl_codigo, get_or_create.
"""

from unittest.mock import MagicMock, patch

import pytest

# ── Construção ─────────────────────────────────────────────────────────────────


def test_init_strip_rl_codigo():
    """GrupoRL.__init__ faz strip no rl_codigo."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db"):
        g = GrupoRL(rl_codigo="  RL-001  ")
    assert g.rl_codigo == "RL-001"


def test_to_dict_contém_campos_esperados():
    """to_dict retorna os campos esperados."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db"):
        g = GrupoRL(rl_codigo="RL-001", criado_por_id="u1", area="TI")
        d = g.to_dict()

    assert d["rl_codigo"] == "RL-001"
    assert d["criado_por_id"] == "u1"
    assert d["area"] == "TI"
    assert "criado_em" in d


def test_from_dict_cria_grupo_correto():
    """from_dict cria GrupoRL com campos corretos."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db"):
        g = GrupoRL.from_dict(
            {"rl_codigo": "RL-999", "criado_por_id": "u2", "area": "Manutencao"},
            id="grp_1",
        )

    assert g.id == "grp_1"
    assert g.rl_codigo == "RL-999"
    assert g.area == "Manutencao"


def test_from_dict_dados_vazios_lanca_valueerror():
    """from_dict com dict vazio/None lança ValueError."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db"), pytest.raises(ValueError):
        GrupoRL.from_dict({})


# ── get_by_rl_codigo ──────────────────────────────────────────────────────────


def test_get_by_rl_codigo_vazio_retorna_none():
    """get_by_rl_codigo com rl_codigo vazio retorna None sem consultar Firestore."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db") as mock_db:
        result = GrupoRL.get_by_rl_codigo("")
    assert result is None
    mock_db.collection.assert_not_called()


def test_get_by_rl_codigo_encontrado_retorna_grupo():
    """get_by_rl_codigo encontra doc e retorna GrupoRL."""
    from app.models_grupo_rl import GrupoRL

    doc = MagicMock()
    doc.id = "grp_1"
    doc.to_dict.return_value = {"rl_codigo": "RL-001", "criado_por_id": "u1", "area": "TI"}

    with patch("app.models_grupo_rl.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            [doc]
        )
        result = GrupoRL.get_by_rl_codigo("RL-001")

    assert result is not None
    assert result.rl_codigo == "RL-001"


def test_get_by_rl_codigo_nao_encontrado_retorna_none():
    """get_by_rl_codigo sem docs retorna None."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.return_value = iter(
            []
        )
        result = GrupoRL.get_by_rl_codigo("RL-999")

    assert result is None


def test_get_by_rl_codigo_excecao_retorna_none():
    """get_by_rl_codigo quando Firestore lança exceção retorna None."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db") as mock_db:
        mock_db.collection.return_value.where.return_value.limit.return_value.stream.side_effect = (
            Exception("err")
        )
        result = GrupoRL.get_by_rl_codigo("RL-001")

    assert result is None


# ── get_or_create ─────────────────────────────────────────────────────────────


def test_get_or_create_rl_codigo_vazio_lanca_valueerror():
    """get_or_create com rl_codigo vazio lança ValueError."""
    from app.models_grupo_rl import GrupoRL

    with patch("app.models_grupo_rl.db"), pytest.raises(ValueError):
        GrupoRL.get_or_create("")


def test_get_or_create_existente_retorna_grupo_existente():
    """get_or_create quando grupo já existe retorna o existente sem criar."""
    from app.models_grupo_rl import GrupoRL

    existente = MagicMock()
    existente.id = "grp_existente"
    existente.rl_codigo = "RL-001"

    with patch.object(GrupoRL, "get_by_rl_codigo", return_value=existente):
        result = GrupoRL.get_or_create("RL-001")

    assert result.id == "grp_existente"


def test_get_or_create_novo_cria_e_retorna():
    """get_or_create quando grupo não existe cria novo e retorna."""
    from app.models_grupo_rl import GrupoRL

    mock_ref = MagicMock()
    mock_ref.id = "grp_novo"

    with (
        patch.object(GrupoRL, "get_by_rl_codigo", return_value=None),
        patch("app.models_grupo_rl.db") as mock_db,
    ):
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        result = GrupoRL.get_or_create("RL-002", criado_por_id="u1", area="TI")

    assert result.id == "grp_novo"
    assert result.rl_codigo == "RL-002"


def test_get_or_create_excecao_propagada():
    """get_or_create propaga exceção quando Firestore falha ao criar."""
    from app.models_grupo_rl import GrupoRL

    with (
        patch.object(GrupoRL, "get_by_rl_codigo", return_value=None),
        patch("app.models_grupo_rl.db") as mock_db,
    ):
        mock_db.collection.return_value.add.side_effect = Exception("timeout")
        with pytest.raises(Exception, match="timeout"):
            GrupoRL.get_or_create("RL-003")
