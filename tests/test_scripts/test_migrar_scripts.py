"""
Testes TDD — F-75: dry-run obrigatório, batch writes, checkpoint JSON e paginação.

Cada script deve:
- Não escrever nada no Firestore sem --apply  (dry_run=True)
- Usar batch.update/commit em vez de doc.reference.update direto (apply mode)
- Gravar checkpoint JSON por fase após apply bem-sucedido
- Funcionar sem carregar toda a coleção em memória (processamento streaming)
"""

import json
from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_doc(data: dict) -> MagicMock:
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def _make_mock_db(*docs) -> tuple[MagicMock, MagicMock]:
    batch = MagicMock()
    db = MagicMock()
    # Suporta paginação: limit(page_size).stream() devolve todos os docs; start_after para.
    q = MagicMock()
    q.stream.return_value = iter(docs)
    q.start_after.return_value.stream.return_value = iter([])
    db.collection.return_value.limit.return_value = q
    db.batch.return_value = batch
    return db, batch


# ─────────────────────────────────────────────────────────────────────────────
# migrar_setores_catalogo — dry-run (já funciona; teste de regressão)
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_chamados_dry_run_nao_grava():
    from scripts.migrar_setores_catalogo import migrar_chamados

    doc = _make_doc({"area": "PPCP", "setores_adicionais": None})
    db, _batch = _make_mock_db(doc)

    migrar_chamados(db, dry_run=True)

    doc.reference.update.assert_not_called()
    _batch.commit.assert_not_called()


def test_migrar_usuarios_dry_run_nao_grava():
    from scripts.migrar_setores_catalogo import migrar_usuarios

    doc = _make_doc({"areas": ["PPCP", "Logistica"], "email": "a@b.com"})
    db, _batch = _make_mock_db(doc)

    migrar_usuarios(db, dry_run=True)

    doc.reference.update.assert_not_called()
    _batch.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# migrar_setores_catalogo — apply deve usar batch (RED: ainda usa update direto)
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_chamados_apply_usa_batch_e_nao_update_direto():
    """Apply mode: batch.update + batch.commit, NÃO doc.reference.update."""
    from scripts.migrar_setores_catalogo import migrar_chamados

    doc = _make_doc({"area": "PPCP", "setores_adicionais": None})
    db, batch = _make_mock_db(doc)

    migrar_chamados(db, dry_run=False)

    batch.commit.assert_called_once()
    doc.reference.update.assert_not_called()  # RED: atualmente chama update direto


def test_migrar_usuarios_apply_usa_batch_e_nao_update_direto():
    """Apply mode: batch.update + batch.commit, NÃO doc.reference.update."""
    from scripts.migrar_setores_catalogo import migrar_usuarios

    doc = _make_doc({"areas": ["PPCP", "Logistica"], "email": "a@b.com"})
    db, batch = _make_mock_db(doc)

    migrar_usuarios(db, dry_run=False)

    batch.commit.assert_called_once()
    doc.reference.update.assert_not_called()  # RED: atualmente chama update direto


def test_migrar_chamados_apply_batch_update_chamado_correto():
    """Batch deve incluir atualização do campo area renomeado."""
    from scripts.migrar_setores_catalogo import migrar_chamados

    doc = _make_doc({"area": "Procurement", "setores_adicionais": None})
    db, batch = _make_mock_db(doc)

    migrar_chamados(db, dry_run=False)

    batch.update.assert_called_once_with(doc.reference, {"area": "Compras"})


# ─────────────────────────────────────────────────────────────────────────────
# migrar_gates_subetapas — sem --apply não deve gravar (RED: sem parâmetro)
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_gates_dry_run_nao_chama_save():
    """migrar(dry_run=True) não chama gate.save() em nenhum gate novo."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    with patch.object(m, "CategoriaGate") as mock_gate_cls:
        mock_gate_cls.get_all.return_value = []
        mock_gate_cls.return_value = gate_inst

        m.migrar(dry_run=True)  # RED: migrar() não aceita dry_run ainda

    gate_inst.save.assert_not_called()


def test_migrar_gates_apply_usa_batch():
    """migrar(dry_run=False) usa batch.commit, NÃO gate.save()."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    gate_inst.to_dict.return_value = {"nome_pt": "Gate Test"}
    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.batch.return_value = batch

    with patch.object(m, "CategoriaGate") as mock_gate_cls, patch.object(m, "db", mock_db):
        mock_gate_cls.get_all.return_value = []
        mock_gate_cls.return_value = gate_inst
        m.migrar(dry_run=False)

    batch.commit.assert_called()
    gate_inst.save.assert_not_called()


def test_migrar_gates_ja_existente_nao_duplica():
    """Gate com mesmo nome_pt existente não é criado novamente."""
    import scripts.migrar_gates_subetapas as m
    from app.gates_config import GATE_SUBETAPAS

    primeiro_pai = next(iter(GATE_SUBETAPAS))
    primeiro_nome = GATE_SUBETAPAS[primeiro_pai][0]

    existente = MagicMock()
    existente.nome_pt = primeiro_nome
    existente.gate_pai = primeiro_pai

    gate_inst = MagicMock()
    gate_inst.to_dict.return_value = {"nome_pt": "Gate Test"}
    mock_db = MagicMock()
    mock_db.batch.return_value = MagicMock()

    with patch.object(m, "CategoriaGate") as mock_gate_cls, patch.object(m, "db", mock_db):
        mock_gate_cls.get_all.return_value = [existente]
        mock_gate_cls.return_value = gate_inst
        m.migrar(dry_run=False)

    # to_dict() chamado para cada gate NOVO (não para o já existente)
    total_subetapas = sum(len(v) for v in GATE_SUBETAPAS.values())
    assert gate_inst.to_dict.call_count == total_subetapas - 1
    gate_inst.save.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# migrar_grupos_rl — sem --apply não deve gravar (RED: sem parâmetro)
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_grupos_rl_dry_run_nao_grava():
    """migrar_grupos_rl(dry_run=True) não chama .update() no chamado."""
    doc = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-001",
            "grupo_rl_id": None,
            "solicitante_id": "u1",
            "area": "TI",
        }
    )
    doc.id = "chamado-x"

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref

    mock_grupo = MagicMock()
    mock_grupo.id = "grupo-1"

    import scripts.migrar_grupos_rl as m

    with (
        patch.object(m, "db", mock_db),
        patch.object(m, "GrupoRL") as mock_grupo_rl_cls,
    ):
        mock_grupo_rl_cls.get_or_create.return_value = mock_grupo
        m.migrar_grupos_rl(dry_run=True)

    mock_chamados_ref.document.return_value.update.assert_not_called()


def test_migrar_grupos_rl_apply_atualiza_chamado():
    """migrar_grupos_rl(dry_run=False) usa batch para atualizar grupo_rl_id no chamado."""
    doc = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-002",
            "grupo_rl_id": None,
            "solicitante_id": "u2",
            "area": "TI",
        }
    )
    doc.id = "chamado-y"

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q
    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref
    mock_db.batch.return_value = batch

    mock_grupo = MagicMock()
    mock_grupo.id = "grupo-2"

    import scripts.migrar_grupos_rl as m

    with (
        patch.object(m, "db", mock_db),
        patch.object(m, "GrupoRL") as mock_grupo_rl_cls,
    ):
        mock_grupo_rl_cls.get_or_create.return_value = mock_grupo
        m.migrar_grupos_rl(dry_run=False)

    batch.commit.assert_called_once()
    # Referência do chamado passada ao batch (via chamados_ref.document(doc.id))
    batch.update.assert_called_once_with(
        mock_chamados_ref.document.return_value, {"grupo_rl_id": "grupo-2"}
    )
    mock_chamados_ref.document.return_value.update.assert_not_called()


def test_migrar_grupos_rl_ignora_sem_rl_codigo():
    """Chamados sem rl_codigo são ignorados (não chamam GrupoRL.get_or_create)."""
    doc = _make_doc({"categoria": "Projetos", "rl_codigo": "", "grupo_rl_id": None})

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref

    import scripts.migrar_grupos_rl as m

    with (
        patch.object(m, "db", mock_db),
        patch.object(m, "GrupoRL") as mock_grupo_rl_cls,
    ):
        m.migrar_grupos_rl(dry_run=False)

    mock_grupo_rl_cls.get_or_create.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# F-75 — segurança de default: migrar() e migrar_grupos_rl() sem args
#          devem comportar-se como dry_run=True
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_gates_default_eh_dry_run():
    """migrar() sem argumento explícito NÃO deve chamar gate.save()."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    with patch.object(m, "CategoriaGate") as mock_gate_cls:
        mock_gate_cls.get_all.return_value = []
        mock_gate_cls.return_value = gate_inst
        m.migrar()  # sem dry_run explícito — deve ser dry_run=True

    gate_inst.save.assert_not_called()  # RED: default atual é False → save é chamado


def test_migrar_grupos_rl_default_eh_dry_run():
    """migrar_grupos_rl() sem argumento explícito NÃO deve gravar (default dry_run=True)."""
    doc = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-001",
            "grupo_rl_id": None,
            "solicitante_id": "u1",
            "area": "TI",
        }
    )
    doc.id = "chamado-z"

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref

    mock_grupo = MagicMock()
    mock_grupo.id = "grupo-z"

    import scripts.migrar_grupos_rl as m

    with (
        patch.object(m, "db", mock_db),
        patch.object(m, "GrupoRL") as mock_grupo_rl_cls,
    ):
        mock_grupo_rl_cls.get_or_create.return_value = mock_grupo
        m.migrar_grupos_rl()  # sem dry_run explícito

    mock_chamados_ref.document.return_value.update.assert_not_called()
    mock_db.batch.return_value.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# F-75 — checkpoint JSON por fase
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_chamados_apply_escreve_checkpoint(tmp_path):
    """Apply mode: arquivo JSON de checkpoint é criado após migrar_chamados."""
    from scripts.migrar_setores_catalogo import migrar_chamados

    doc = _make_doc({"area": "PPCP", "setores_adicionais": None})
    db, batch = _make_mock_db(doc)

    migrar_chamados(db, dry_run=False, checkpoint_dir=tmp_path)  # RED: sem parâmetro

    files = list(tmp_path.glob("*chamados*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "chamados"
    assert "concluida_em" in data
    assert data["stats"]["alterados"] == 1


def test_migrar_chamados_dry_run_com_checkpoint_dir_nao_cria_arquivo(tmp_path):
    """Dry-run: mesmo com checkpoint_dir fornecido, nenhum JSON é criado."""
    from scripts.migrar_setores_catalogo import migrar_chamados

    doc = _make_doc({"area": "PPCP", "setores_adicionais": None})
    db, _batch = _make_mock_db(doc)

    migrar_chamados(db, dry_run=True, checkpoint_dir=tmp_path)  # RED: sem parâmetro

    assert list(tmp_path.glob("*.json")) == []


def test_migrar_usuarios_apply_escreve_checkpoint(tmp_path):
    """Apply mode: arquivo JSON de checkpoint é criado após migrar_usuarios."""
    from scripts.migrar_setores_catalogo import migrar_usuarios

    doc = _make_doc({"areas": ["Logistica"], "email": "a@b.com"})
    db, batch = _make_mock_db(doc)

    migrar_usuarios(db, dry_run=False, checkpoint_dir=tmp_path)  # RED

    files = list(tmp_path.glob("*usuarios*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "usuarios"
    assert data["stats"]["alterados"] == 1


def test_migrar_usuarios_dry_run_com_checkpoint_dir_nao_cria_arquivo(tmp_path):
    """Dry-run: mesmo com checkpoint_dir fornecido, nenhum JSON é criado."""
    from scripts.migrar_setores_catalogo import migrar_usuarios

    doc = _make_doc({"areas": ["Logistica"], "email": "a@b.com"})
    db, _batch = _make_mock_db(doc)

    migrar_usuarios(db, dry_run=True, checkpoint_dir=tmp_path)  # RED

    assert list(tmp_path.glob("*.json")) == []


def test_migrar_catalogo_apply_escreve_checkpoint(tmp_path):
    """Apply mode: arquivo JSON de checkpoint é criado após migrar_catalogo."""
    from scripts.migrar_setores_catalogo import migrar_catalogo

    # Setor sem rename/desativar necessário → sem chamada a translation_service
    doc = _make_doc({"nome_pt": "TI", "ativo": True})
    db = MagicMock()
    db.collection.return_value.stream.return_value = iter([doc])

    migrar_catalogo(db, dry_run=False, checkpoint_dir=tmp_path)  # RED

    files = list(tmp_path.glob("*catalogo*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "catalogo"
    assert "concluida_em" in data


# ─────────────────────────────────────────────────────────────────────────────
# F-75 — paginação: 501 docs → 2 batch commits (≤500 ops cada)
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_chamados_501_docs_usa_dois_batch_commits():
    """Com 501 docs a alterar, _commit_batch deve usar exatamente 2 commits."""
    from scripts.migrar_setores_catalogo import migrar_chamados

    docs = [_make_doc({"area": "PPCP", "setores_adicionais": None}) for _ in range(501)]
    batch1, batch2 = MagicMock(), MagicMock()
    db = MagicMock()
    # Paginação: limit().stream() devolve todos os 501 docs na primeira página
    q = MagicMock()
    q.stream.return_value = iter(docs)
    q.start_after.return_value.stream.return_value = iter([])
    db.collection.return_value.limit.return_value = q
    db.batch.side_effect = [batch1, batch2]

    migrar_chamados(db, dry_run=False)

    assert db.batch.call_count == 2
    batch1.commit.assert_called_once()
    batch2.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Lacuna 1 — migrar_catalogo: batch em vez de update direto
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_catalogo_apply_usa_batch_nao_update_direto():
    """Apply: RENAME usa batch.update, nunca doc.reference.update direto."""
    from scripts.migrar_setores_catalogo import migrar_catalogo

    doc1 = _make_doc({"nome_pt": "PPCP", "ativo": True})
    doc2 = _make_doc({"nome_pt": "Logistica", "ativo": True})
    batch = MagicMock()
    db = MagicMock()
    db.collection.return_value.stream.return_value = iter([doc1, doc2])
    db.batch.return_value = batch

    with patch(
        "scripts.migrar_setores_catalogo._rename_nome_en_es",
        return_value={"nome_en": "x", "nome_es": "y"},
    ):
        migrar_catalogo(db, dry_run=False)

    batch.commit.assert_called()
    doc1.reference.update.assert_not_called()
    doc2.reference.update.assert_not_called()


def test_migrar_catalogo_apply_desativar_usa_batch():
    """Apply: DESATIVAR usa batch.update, nunca doc.reference.update direto."""
    from scripts.migrar_setores_catalogo import migrar_catalogo

    doc = _make_doc({"nome_pt": "Produção - Usinagem", "ativo": True})
    batch = MagicMock()
    db = MagicMock()
    db.collection.return_value.stream.return_value = iter([doc])
    db.batch.return_value = batch

    migrar_catalogo(db, dry_run=False)

    batch.update.assert_called_with(doc.reference, {"ativo": False})
    doc.reference.update.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Lacuna 2 — migrar_gates_subetapas: batch + checkpoint
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_gates_apply_usa_batch_set_nao_save():
    """Apply: batch.commit chamado via db.batch(), gate.save() NÃO chamado."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    gate_inst.to_dict.return_value = {"nome_pt": "Test Gate", "ativo": True}
    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.batch.return_value = batch

    with patch.object(m, "CategoriaGate") as mock_cls, patch.object(m, "db", mock_db, create=True):
        mock_cls.get_all.return_value = []
        mock_cls.return_value = gate_inst
        m.migrar(dry_run=False)

    batch.commit.assert_called()
    gate_inst.save.assert_not_called()


def test_migrar_gates_apply_escreve_checkpoint(tmp_path):
    """Apply com checkpoint_dir: arquivo JSON de checkpoint é criado."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    gate_inst.to_dict.return_value = {"nome_pt": "Test Gate"}
    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.batch.return_value = batch

    with patch.object(m, "CategoriaGate") as mock_cls, patch.object(m, "db", mock_db, create=True):
        mock_cls.get_all.return_value = []
        mock_cls.return_value = gate_inst
        m.migrar(dry_run=False, checkpoint_dir=tmp_path)

    files = list(tmp_path.glob("*gates*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "gates"
    assert "concluida_em" in data


def test_migrar_gates_dry_run_nao_escreve_checkpoint(tmp_path):
    """Dry-run: nenhum checkpoint criado mesmo com checkpoint_dir fornecido."""
    import scripts.migrar_gates_subetapas as m

    gate_inst = MagicMock()
    mock_db = MagicMock()

    with patch.object(m, "CategoriaGate") as mock_cls, patch.object(m, "db", mock_db, create=True):
        mock_cls.get_all.return_value = []
        mock_cls.return_value = gate_inst
        m.migrar(dry_run=True, checkpoint_dir=tmp_path)

    assert list(tmp_path.glob("*.json")) == []


# ─────────────────────────────────────────────────────────────────────────────
# Lacuna 3 — migrar_grupos_rl: batch + checkpoint
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_grupos_rl_apply_usa_batch_nao_update_loop():
    """Apply com 2 chamados elegíveis: batch.commit chamado, update direto NÃO."""
    doc1 = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-001",
            "grupo_rl_id": None,
            "solicitante_id": "u1",
            "area": "TI",
        }
    )
    doc1.id = "c1"
    doc2 = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-001",
            "grupo_rl_id": None,
            "solicitante_id": "u2",
            "area": "TI",
        }
    )
    doc2.id = "c2"

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc1, doc2])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q

    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref
    mock_db.batch.return_value = batch

    mock_grupo = MagicMock()
    mock_grupo.id = "g1"

    import scripts.migrar_grupos_rl as m

    with patch.object(m, "db", mock_db), patch.object(m, "GrupoRL") as mock_rl:
        mock_rl.get_or_create.return_value = mock_grupo
        m.migrar_grupos_rl(dry_run=False)

    batch.commit.assert_called()
    mock_chamados_ref.document.return_value.update.assert_not_called()


def test_migrar_grupos_rl_apply_escreve_checkpoint(tmp_path):
    """Apply com checkpoint_dir: arquivo JSON de checkpoint é criado."""
    doc = _make_doc(
        {
            "categoria": "Projetos",
            "rl_codigo": "RL-001",
            "grupo_rl_id": None,
            "solicitante_id": "u1",
            "area": "TI",
        }
    )
    doc.id = "c1"

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q

    batch = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref
    mock_db.batch.return_value = batch

    mock_grupo = MagicMock()
    mock_grupo.id = "g1"

    import scripts.migrar_grupos_rl as m

    with patch.object(m, "db", mock_db), patch.object(m, "GrupoRL") as mock_rl:
        mock_rl.get_or_create.return_value = mock_grupo
        m.migrar_grupos_rl(dry_run=False, checkpoint_dir=tmp_path)

    files = list(tmp_path.glob("*grupos_rl*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "grupos_rl"
    assert "concluida_em" in data


def test_migrar_grupos_rl_dry_run_nao_escreve_checkpoint(tmp_path):
    """Dry-run: nenhum checkpoint criado mesmo com checkpoint_dir fornecido."""
    doc = _make_doc({"categoria": "Projetos", "rl_codigo": "RL-001", "grupo_rl_id": None})

    mock_chamados_ref = MagicMock()
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.start_after.return_value.stream.return_value = iter([])
    mock_chamados_ref.limit.return_value = q

    mock_db = MagicMock()
    mock_db.collection.return_value = mock_chamados_ref

    import scripts.migrar_grupos_rl as m

    with patch.object(m, "db", mock_db), patch.object(m, "GrupoRL") as mock_rl:
        mock_rl.get_or_create.return_value = MagicMock()
        m.migrar_grupos_rl(dry_run=True, checkpoint_dir=tmp_path)

    assert list(tmp_path.glob("*.json")) == []


# ─────────────────────────────────────────────────────────────────────────────
# Lacuna 4 — Paginação: helper _iter_collection_paginated
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# F-30 — migrar_setor_area: dry-run e apply
# ─────────────────────────────────────────────────────────────────────────────


def test_migrar_setor_area_dry_run_nao_grava():
    """Dry-run: nenhuma escrita no Firestore (ref.set não chamado)."""
    from scripts.migrar_setor_area import executar

    mock_db = MagicMock()
    resultado = executar(mock_db, dry_run=True)

    mock_db.collection.assert_not_called()
    assert resultado["gravado"] is False
    assert resultado["dry_run"] is True
    assert resultado["entradas"] == 2  # Material + Manutenção


def test_migrar_setor_area_apply_grava_mapa(tmp_path):
    """Apply: grava doc config/setor_para_area com campo mapa correto."""
    from scripts.migrar_setor_area import MAPA_INICIAL, executar

    mock_ref = MagicMock()
    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = mock_ref

    resultado = executar(mock_db, dry_run=False, checkpoint_dir=tmp_path)

    mock_db.collection.assert_called_once_with("config")
    mock_db.collection.return_value.document.assert_called_once_with("setor_para_area")
    mock_ref.set.assert_called_once_with({"mapa": MAPA_INICIAL})
    assert resultado["gravado"] is True
    assert resultado["dry_run"] is False


def test_migrar_setor_area_apply_escreve_checkpoint(tmp_path):
    """Apply: checkpoint JSON é criado após gravação."""
    from scripts.migrar_setor_area import executar

    mock_db = MagicMock()
    executar(mock_db, dry_run=False, checkpoint_dir=tmp_path)

    files = list(tmp_path.glob("*migrar_setor_area*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["fase"] == "gravar_mapa"
    assert "concluida_em" in data
    assert data["stats"]["dry_run"] is False


def test_migrar_setor_area_dry_run_nao_escreve_checkpoint(tmp_path):
    """Dry-run: nenhum checkpoint criado mesmo com checkpoint_dir fornecido."""
    from scripts.migrar_setor_area import executar

    mock_db = MagicMock()
    executar(mock_db, dry_run=True, checkpoint_dir=tmp_path)

    assert list(tmp_path.glob("*.json")) == []


# ─────────────────────────────────────────────────────────────────────────────


def test_iter_collection_paginated_1200_docs():
    """1200 docs em páginas de 500: limit(500) chamado ≥3×, total 1200 docs."""
    from scripts._migration_utils import _iter_collection_paginated

    page1 = [MagicMock() for _ in range(500)]
    page2 = [MagicMock() for _ in range(500)]
    page3 = [MagicMock() for _ in range(200)]

    q_initial = MagicMock()
    q_initial.stream.return_value = iter(page1)
    q2 = MagicMock()
    q2.stream.return_value = iter(page2)
    q3 = MagicMock()
    q3.stream.return_value = iter(page3)
    q_initial.start_after.side_effect = [q2, q3]

    collection_ref = MagicMock()
    collection_ref.limit.return_value = q_initial

    docs = list(_iter_collection_paginated(collection_ref, page_size=500))

    assert len(docs) == 1200
    assert collection_ref.limit.call_count >= 3
    collection_ref.limit.assert_called_with(500)


# ─────────────────────────────────────────────────────────────────────────────
# migrar_supervisor_ids_com_acesso
# ─────────────────────────────────────────────────────────────────────────────


def _make_mock_db_with_users(chamado_docs, usuario_docs):
    """Mock de db com coleções separadas para chamados e usuários."""
    batch = MagicMock()
    db = MagicMock()

    def _collection(name):
        col = MagicMock()
        if name == "chamados":
            q = MagicMock()
            q.stream.return_value = iter(chamado_docs)
            q.start_after.return_value.stream.return_value = iter([])
            col.limit.return_value = q
        elif name == "usuarios":
            col.stream.return_value = iter(usuario_docs)
        return col

    db.collection.side_effect = _collection
    db.batch.return_value = batch
    return db, batch


def test_migrar_supervisor_ids_dry_run_nao_grava():
    """--dry-run não deve gravar nenhum dado no Firestore."""
    from scripts.migrar_supervisor_ids_com_acesso import migrar_supervisor_ids

    sup_doc = _make_doc({"perfil": "supervisor", "areas": ["Engenharia"]})
    sup_doc.id = "id_julia"

    chamado_doc = _make_doc({"area": "Engenharia", "responsavel_id": None, "participantes": []})
    chamado_doc.reference = MagicMock()

    db, batch = _make_mock_db_with_users([chamado_doc], [sup_doc])

    migrar_supervisor_ids(db, dry_run=True)

    batch.commit.assert_not_called()
    chamado_doc.reference.update.assert_not_called()


def test_migrar_supervisor_ids_apply_grava_ids():
    """--apply deve gravar supervisor_ids_com_acesso usando batch.update."""
    from scripts.migrar_supervisor_ids_com_acesso import migrar_supervisor_ids

    sup_doc = _make_doc({"perfil": "supervisor", "areas": ["Engenharia"]})
    sup_doc.id = "id_julia"

    chamado_doc = _make_doc({"area": "Engenharia", "responsavel_id": None, "participantes": []})
    chamado_doc.reference = MagicMock()

    db, batch = _make_mock_db_with_users([chamado_doc], [sup_doc])

    stats = migrar_supervisor_ids(db, dry_run=False)

    batch.update.assert_called_once()
    batch.commit.assert_called_once()
    assert stats["total_atualizados"] == 1


def test_migrar_supervisor_ids_ja_ok_nao_atualiza():
    """Chamado já com supervisor_ids_com_acesso correto não deve ser reescrito."""
    from scripts.migrar_supervisor_ids_com_acesso import migrar_supervisor_ids

    sup_doc = _make_doc({"perfil": "supervisor", "areas": ["Engenharia"]})
    sup_doc.id = "id_julia"

    chamado_doc = _make_doc(
        {
            "area": "Engenharia",
            "responsavel_id": None,
            "participantes": [],
            "supervisor_ids_com_acesso": ["id_julia"],  # já correto
        }
    )
    chamado_doc.reference = MagicMock()

    db, batch = _make_mock_db_with_users([chamado_doc], [sup_doc])

    stats = migrar_supervisor_ids(db, dry_run=False)

    batch.commit.assert_not_called()
    assert stats["total_ja_ok"] == 1
    assert stats["total_atualizados"] == 0


def test_migrar_supervisor_ids_com_owner_usa_responsavel():
    """Chamado com owner: supervisor_ids_com_acesso = [owner_id]."""
    from scripts.migrar_supervisor_ids_com_acesso import migrar_supervisor_ids

    chamado_doc = _make_doc(
        {
            "area": "Engenharia",
            "responsavel_id": "id_matheus",
            "participantes": [],
            "supervisor_ids_com_acesso": [],  # desatualizado
        }
    )
    chamado_doc.reference = MagicMock()

    db, batch = _make_mock_db_with_users([chamado_doc], [])

    stats = migrar_supervisor_ids(db, dry_run=False)

    assert stats["total_atualizados"] == 1
    # Verifica que batch.update foi chamado com os ids corretos
    call_args = batch.update.call_args
    updated_data = call_args[0][1]
    assert updated_data["supervisor_ids_com_acesso"] == ["id_matheus"]


# ─────────────────────────────────────────────────────────────────────────────
# migrar_participantes — Fase 4 (Lacuna 4)
# ─────────────────────────────────────────────────────────────────────────────


def _make_db_participantes(chamados_docs, usuarios_docs) -> tuple[MagicMock, MagicMock]:
    """db mock que separa collections 'chamados' e 'usuarios'."""
    batch = MagicMock()
    db = MagicMock()

    q_chamados = MagicMock()
    q_chamados.stream.return_value = iter(chamados_docs)
    q_chamados.start_after.return_value.stream.return_value = iter([])

    q_usuarios = MagicMock()
    q_usuarios.stream.return_value = iter(usuarios_docs)

    def _collection(name):
        col = MagicMock()
        if name == "chamados":
            col.limit.return_value = q_chamados
        else:
            col.stream.return_value = iter(usuarios_docs)
        return col

    db.collection.side_effect = _collection
    db.batch.return_value = batch
    return db, batch


def _sup_firestore_doc(id_: str, areas: list[str]) -> MagicMock:
    doc = MagicMock()
    doc.id = id_
    doc.to_dict.return_value = {
        "perfil": "supervisor",
        "ativo": True,
        "areas": areas,
        "nome": f"Sup {id_}",
    }
    return doc


def test_migrar_participantes_dry_run_nao_grava():
    """dry-run: não escreve no Firestore."""
    from scripts.migrar_participantes import migrar_participantes

    chamado_doc = _make_doc(
        {
            "area": "Manutencao",
            "setores_adicionais": ["TI"],
            "participantes": [],
            "responsavel_id": "sup_1",
            "supervisor_ids_com_acesso": ["sup_1"],
        }
    )
    sup_doc = _sup_firestore_doc("ti_sup_1", ["TI"])
    db, batch = _make_db_participantes([chamado_doc], [sup_doc])

    stats = migrar_participantes(db, dry_run=True)

    batch.commit.assert_not_called()
    assert stats["total_verificados"] >= 1
    assert stats["total_migrados"] >= 1


def test_migrar_participantes_apply_grava_e_checkpoint():
    """apply: escreve via batch e grava checkpoint."""
    from scripts.migrar_participantes import migrar_participantes

    chamado_doc = _make_doc(
        {
            "area": "Manutencao",
            "setores_adicionais": ["TI"],
            "participantes": [],
            "responsavel_id": "sup_1",
            "supervisor_ids_com_acesso": ["sup_1"],
        }
    )
    sup_doc = _sup_firestore_doc("ti_sup_1", ["TI"])
    db, batch = _make_db_participantes([chamado_doc], [sup_doc])

    with patch("scripts.migrar_participantes._write_checkpoint") as mock_checkpoint:
        stats = migrar_participantes(db, dry_run=False)

    batch.commit.assert_called()
    mock_checkpoint.assert_called_once()
    assert stats["total_migrados"] >= 1


def test_migrar_participantes_skip_ja_tem_participantes():
    """Chamado com participantes[] populado é ignorado."""
    from scripts.migrar_participantes import migrar_participantes

    chamado_doc = _make_doc(
        {
            "setores_adicionais": ["TI"],
            "participantes": [{"supervisor_id": "existing", "area": "TI", "status": "pendente"}],
            "responsavel_id": "sup_1",
        }
    )
    db, batch = _make_db_participantes([chamado_doc], [])

    stats = migrar_participantes(db, dry_run=False)

    batch.commit.assert_not_called()
    assert stats["total_ja_tem_participantes"] >= 1


def test_migrar_participantes_skip_sem_setores():
    """Chamado sem setores_adicionais é ignorado."""
    from scripts.migrar_participantes import migrar_participantes

    chamado_doc = _make_doc(
        {
            "area": "Manutencao",
            "setores_adicionais": [],
            "participantes": [],
            "responsavel_id": "sup_1",
        }
    )
    db, batch = _make_db_participantes([chamado_doc], [])

    stats = migrar_participantes(db, dry_run=False)

    batch.commit.assert_not_called()
    assert stats["total_sem_setores"] >= 1
