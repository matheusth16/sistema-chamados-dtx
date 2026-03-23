"""
Testes unitários dos modelos CategoriaSetor, CategoriaGate, CategoriaImpacto.
Cobre: from_dict, to_dict, save (novo/update), get_all (sucesso/exceção), get_by_id (encontrado/não/exceção).
"""

from unittest.mock import MagicMock, patch

# ── CategoriaSetor ─────────────────────────────────────────────────────────────


def _traduzir_mock():
    return {"en": "Test EN", "es": "Test ES"}


def test_setor_from_dict_cria_com_campos_corretos():
    """CategoriaSetor.from_dict cria objeto com campos corretos."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "Eng", "es": "Ing"}):
        s = CategoriaSetor.from_dict(
            {
                "nome_pt": "Engenharia",
                "nome_en": "Engineering",
                "nome_es": "Ingeniería",
                "ativo": True,
            },
            id="s1",
        )

    assert s.id == "s1"
    assert s.nome_pt == "Engenharia"
    assert s.nome_en == "Engineering"
    assert s.ativo is True


def test_setor_to_dict_contém_campos_esperados():
    """CategoriaSetor.to_dict retorna dict com todos os campos."""
    from app.models_categorias import CategoriaSetor

    with patch(
        "app.models_categorias.traduzir_categoria", return_value={"en": "Maint", "es": "Mant"}
    ):
        s = CategoriaSetor(nome_pt="Manutencao", nome_en="Maintenance", nome_es="Mantenimiento")
        d = s.to_dict()

    assert d["nome_pt"] == "Manutencao"
    assert d["nome_en"] == "Maintenance"
    assert "ativo" in d
    assert "data_criacao" in d


def test_setor_save_novo_chama_add():
    """CategoriaSetor.save sem id chama db.collection().add()."""
    from app.models_categorias import CategoriaSetor

    mock_ref = MagicMock()
    mock_ref.id = "s_novo"

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "E", "es": "E"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        s = CategoriaSetor(nome_pt="Novo Setor", nome_en="New", nome_es="Nuevo")
        result = s.save()

    assert result == "s_novo"
    mock_db.collection.return_value.add.assert_called_once()


def test_setor_save_existente_chama_update():
    """CategoriaSetor.save com id chama db.collection().document().update()."""
    from app.models_categorias import CategoriaSetor

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "E", "es": "E"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        s = CategoriaSetor(
            nome_pt="Setor Existente", nome_en="Existing", nome_es="Existente", id="s1"
        )
        s.save()

    mock_db.collection.return_value.document.return_value.update.assert_called_once()


def test_setor_get_all_retorna_lista():
    """CategoriaSetor.get_all retorna lista de instâncias."""
    from app.models_categorias import CategoriaSetor

    doc = MagicMock()
    doc.id = "s1"
    doc.to_dict.return_value = {
        "nome_pt": "TI",
        "nome_en": "IT",
        "nome_es": "TI",
        "ativo": True,
    }

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "IT", "es": "TI"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.stream.return_value = [doc]
        result = CategoriaSetor.get_all()

    assert len(result) == 1
    assert result[0].id == "s1"


def test_setor_get_all_retorna_vazio_quando_excecao():
    """CategoriaSetor.get_all retorna [] quando Firestore lança exceção."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.stream.side_effect = Exception("err")
        result = CategoriaSetor.get_all()

    assert result == []


def test_setor_get_by_id_encontrado():
    """CategoriaSetor.get_by_id retorna setor quando encontrado."""
    from app.models_categorias import CategoriaSetor

    doc = MagicMock()
    doc.id = "s1"
    doc.exists = True
    doc.to_dict.return_value = {"nome_pt": "TI", "nome_en": "IT", "nome_es": "TI"}

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "IT", "es": "TI"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = CategoriaSetor.get_by_id("s1")

    assert result is not None
    assert result.id == "s1"


def test_setor_get_by_id_nao_encontrado_retorna_none():
    """CategoriaSetor.get_by_id retorna None quando doc não existe."""
    from app.models_categorias import CategoriaSetor

    doc = MagicMock()
    doc.exists = False

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = CategoriaSetor.get_by_id("naoexiste")

    assert result is None


def test_setor_get_by_id_excecao_retorna_none():
    """CategoriaSetor.get_by_id retorna None quando Firestore lança exceção."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("err")
        result = CategoriaSetor.get_by_id("s1")

    assert result is None


# ── CategoriaGate ─────────────────────────────────────────────────────────────


def test_gate_from_dict_cria_com_campos_corretos():
    """CategoriaGate.from_dict cria objeto correto."""
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G1", "es": "G1"}):
        g = CategoriaGate.from_dict(
            {
                "nome_pt": "Gate 1",
                "nome_en": "Gate 1",
                "nome_es": "Gate 1",
                "ordem": 1,
                "ativo": True,
            },
            id="g1",
        )

    assert g.id == "g1"
    assert g.nome_pt == "Gate 1"
    assert g.ordem == 1


def test_gate_save_novo_chama_add():
    """CategoriaGate.save sem id chama db.collection().add()."""
    from app.models_categorias import CategoriaGate

    mock_ref = MagicMock()
    mock_ref.id = "g_novo"

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        g = CategoriaGate(nome_pt="Novo Gate")
        result = g.save()

    assert result == "g_novo"


def test_gate_get_all_retorna_lista_ordenada():
    """CategoriaGate.get_all retorna gates ordenados por ordem."""
    from app.models_categorias import CategoriaGate

    doc1 = MagicMock()
    doc1.id = "g2"
    doc1.to_dict.return_value = {"nome_pt": "Gate 2", "nome_en": "G2", "nome_es": "G2", "ordem": 2}
    doc2 = MagicMock()
    doc2.id = "g1"
    doc2.to_dict.return_value = {"nome_pt": "Gate 1", "nome_en": "G1", "nome_es": "G1", "ordem": 1}

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.stream.return_value = [doc1, doc2]
        result = CategoriaGate.get_all()

    assert result[0].ordem == 1
    assert result[1].ordem == 2


def test_gate_get_all_retorna_vazio_quando_excecao():
    """CategoriaGate.get_all retorna [] quando Firestore lança exceção."""
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.stream.side_effect = Exception("err")
        result = CategoriaGate.get_all()

    assert result == []


def test_gate_get_by_id_encontrado():
    """CategoriaGate.get_by_id retorna gate quando encontrado."""
    from app.models_categorias import CategoriaGate

    doc = MagicMock()
    doc.id = "g1"
    doc.exists = True
    doc.to_dict.return_value = {"nome_pt": "Gate 1", "nome_en": "G1", "nome_es": "G1"}

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = CategoriaGate.get_by_id("g1")

    assert result is not None


def test_gate_get_by_id_excecao_retorna_none():
    """CategoriaGate.get_by_id retorna None quando exceção."""
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("err")
        result = CategoriaGate.get_by_id("g1")

    assert result is None


# ── CategoriaImpacto ──────────────────────────────────────────────────────────


def test_impacto_from_dict_cria_com_campos_corretos():
    """CategoriaImpacto.from_dict cria objeto correto."""
    from app.models_categorias import CategoriaImpacto

    with patch(
        "app.models_categorias.traduzir_categoria", return_value={"en": "High", "es": "Alto"}
    ):
        imp = CategoriaImpacto.from_dict(
            {"nome_pt": "Alto", "nome_en": "High", "nome_es": "Alto", "nivel": 3, "cor": "#red"},
            id="i1",
        )

    assert imp.id == "i1"
    assert imp.nivel == 3
    assert imp.cor == "#red"


def test_impacto_save_novo_chama_add():
    """CategoriaImpacto.save sem id chama db.collection().add()."""
    from app.models_categorias import CategoriaImpacto

    mock_ref = MagicMock()
    mock_ref.id = "i_novo"

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.add.return_value = (None, mock_ref)
        imp = CategoriaImpacto(nome_pt="Novo Impacto")
        result = imp.save()

    assert result == "i_novo"


def test_impacto_get_all_retorna_lista():
    """CategoriaImpacto.get_all retorna lista de impactos."""
    from app.models_categorias import CategoriaImpacto

    doc = MagicMock()
    doc.id = "i1"
    doc.to_dict.return_value = {"nome_pt": "Baixo", "nome_en": "Low", "nome_es": "Bajo", "nivel": 1}

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "L", "es": "B"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc]
        result = CategoriaImpacto.get_all()

    assert len(result) == 1


def test_impacto_get_all_retorna_vazio_quando_excecao():
    """CategoriaImpacto.get_all retorna [] quando Firestore lança exceção."""
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.side_effect = Exception("err")
        result = CategoriaImpacto.get_all()

    assert result == []


def test_impacto_get_by_id_encontrado():
    """CategoriaImpacto.get_by_id retorna impacto quando encontrado."""
    from app.models_categorias import CategoriaImpacto

    doc = MagicMock()
    doc.id = "i1"
    doc.exists = True
    doc.to_dict.return_value = {"nome_pt": "Médio", "nome_en": "Medium", "nome_es": "Medio"}

    with (
        patch("app.models_categorias.traduzir_categoria", return_value={"en": "M", "es": "M"}),
        patch("app.models_categorias.db") as mock_db,
    ):
        mock_db.collection.return_value.document.return_value.get.return_value = doc
        result = CategoriaImpacto.get_by_id("i1")

    assert result is not None


def test_impacto_get_by_id_excecao_retorna_none():
    """CategoriaImpacto.get_by_id retorna None quando exceção."""
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.db") as mock_db:
        mock_db.collection.return_value.document.return_value.get.side_effect = Exception("err")
        result = CategoriaImpacto.get_by_id("i1")

    assert result is None
