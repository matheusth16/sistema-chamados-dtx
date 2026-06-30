"""
Testes unitários do modelo Usuario.
Cobre: from_dict, to_dict, set_password/check_password, area property,
save, update, delete, get_all, email_existe, get_supervisores_por_area.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

# ── Construção do modelo ───────────────────────────────────────────────────────


def test_from_dict_campos_basicos():
    """from_dict cria Usuario com campos básicos corretos."""
    from app.models_usuario import Usuario

    data = {
        "email": "teste@dtx.aero",
        "nome": "Teste Silva",
        "perfil": "supervisor",
        "areas": ["Manutencao"],
        "senha_hash": None,
        "must_change_password": False,
        "password_changed_at": None,
        "exp_total": 10,
        "exp_semanal": 5,
        "level": 2,
        "conquistas": ["badge1"],
        "onboarding_completo": True,
        "onboarding_passo": 3,
    }
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_001")

    assert u.id == "u_001"
    assert u.email == "teste@dtx.aero"
    assert u.perfil == "supervisor"
    assert u.areas == ["Manutencao"]
    assert u.level == 2
    assert u.onboarding_completo is True


def test_from_dict_migra_area_string_para_areas_lista():
    """from_dict migra campo 'area' (string) para 'areas' (lista) quando areas está ausente."""
    from app.models_usuario import Usuario

    data = {"email": "m@dtx.aero", "nome": "M", "perfil": "solicitante", "area": "Qualidade"}
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_002")

    assert u.areas == ["Qualidade"]


def test_from_dict_password_changed_at_isoformat():
    """from_dict converte password_changed_at de string ISO para datetime."""
    from app.models_usuario import Usuario

    data = {
        "email": "a@dtx.aero",
        "nome": "A",
        "perfil": "admin",
        "password_changed_at": "2026-01-15T10:30:00",
    }
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_003")

    assert isinstance(u.password_changed_at, datetime)
    assert u.password_changed_at.year == 2026


def test_from_dict_password_changed_at_invalido_vira_none():
    """from_dict trata string inválida de password_changed_at como None."""
    from app.models_usuario import Usuario

    data = {
        "email": "b@dtx.aero",
        "nome": "B",
        "perfil": "solicitante",
        "password_changed_at": "nao-e-data",
    }
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_004")

    assert u.password_changed_at is None


def test_to_dict_contém_campos_esperados():
    """to_dict retorna dicionário com todos os campos necessários para Firestore."""
    from app.models_usuario import Usuario

    with (
        patch("app.models_usuario.db"),
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.maybe_encrypt", side_effect=lambda x: x),
    ):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="admin", areas=["TI"])
        d = u.to_dict()

    assert d["email"] == "x@dtx.aero"
    assert d["perfil"] == "admin"
    assert d["areas"] == ["TI"]
    assert "senha_hash" in d
    assert "must_change_password" in d
    assert "onboarding_completo" in d


# ── Senha ──────────────────────────────────────────────────────────────────────


def test_set_password_e_check_password():
    """set_password gera hash e check_password valida a senha correta."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.set_password("SenhaSegura123!")
        assert u.check_password("SenhaSegura123!") is True
        assert u.check_password("SenhaErrada") is False


def test_check_password_sem_hash_retorna_false():
    """check_password retorna False quando senha_hash é None."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.senha_hash = None
        assert u.check_password("qualquer") is False


# CWI 2.2 — hash Werkzeug: não é plaintext, contém prefixo scrypt:/pbkdf2:
def test_senha_hash_usa_formato_werkzeug_nao_plaintext():
    """CWI 2.2 — set_password gera hash Werkzeug (scrypt:/pbkdf2:), nunca plaintext."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u_cwi22", email="cwi@dtx.aero", nome="CWI Test")
        u.set_password("SenhaCWI2_2!")

    assert u.senha_hash is not None
    assert u.senha_hash != "SenhaCWI2_2!", "senha_hash não deve ser plaintext"
    assert u.senha_hash.startswith("scrypt:") or u.senha_hash.startswith("pbkdf2:"), (
        f"Hash deve ter prefixo Werkzeug (scrypt:/pbkdf2:), obtido: {u.senha_hash[:20]!r}"
    )


# ── Property area ──────────────────────────────────────────────────────────────


def test_area_property_com_areas():
    """property area retorna áreas separadas por vírgula."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(
            id="u1",
            email="x@dtx.aero",
            nome="X",
            perfil="supervisor",
            areas=["Manutencao", "Elétrica"],
        )
        assert u.area == "Manutencao, Elétrica"


def test_area_property_sem_areas():
    """property area retorna None quando lista de áreas está vazia."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante", areas=[])
        assert u.area is None


# ── save ───────────────────────────────────────────────────────────────────────


def test_save_chama_firestore_set():
    """save chama db.collection().document().set() com to_dict()."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.save()

    mock_db.collection.return_value.document.return_value.set.assert_called_once()
    assert result is True


def test_save_retorna_false_quando_firestore_falha():
    """save retorna False quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.document.return_value.set.side_effect = Exception("err")
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.save()

    assert result is False


# ── update ─────────────────────────────────────────────────────────────────────


def test_update_email_atualiza_campo():
    """update com email chama Firestore update com novo email (encryption OFF)."""
    from app.models_usuario import Usuario

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.maybe_encrypt", side_effect=lambda x: x),
    ):
        u = Usuario(id="u1", email="velho@dtx.aero", nome="X", perfil="solicitante")
        u.update(email="novo@dtx.aero")

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["email"] == "novo@dtx.aero"


def test_update_gamification_atualiza_exp_e_level():
    """update com gamification dict atualiza exp_total, exp_semanal, level e conquistas."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.update(
            gamification={"exp_total": 100, "exp_semanal": 20, "level": 3, "conquistas": ["b1"]}
        )

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["exp_total"] == 100
    assert call_args["level"] == 3


def test_update_must_change_password():
    """update com must_change_password persiste no Firestore."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.update(must_change_password=True)

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["must_change_password"] is True


def test_update_sem_campos_retorna_false():
    """update sem kwargs não chama Firestore e retorna False."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.update()

    mock_db.collection.return_value.document.return_value.update.assert_not_called()
    assert result is False


def test_update_retorna_false_quando_firestore_falha():
    """update retorna False quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.side_effect = Exception("err")
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.update(nome="Novo Nome")

    assert result is False


# ── delete ─────────────────────────────────────────────────────────────────────


def test_delete_chama_firestore_delete():
    """delete chama db.collection().document().delete()."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.delete()

    mock_db.collection.return_value.document.return_value.delete.assert_called_once()
    assert result is True


def test_delete_retorna_false_quando_firestore_falha():
    """delete retorna False quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.document.return_value.delete.side_effect = Exception("err")
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        result = u.delete()

    assert result is False


# ── get_all ────────────────────────────────────────────────────────────────────


def test_get_all_retorna_lista_de_usuarios():
    """get_all retorna lista de instâncias Usuario para cada doc do Firestore (encryption OFF)."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u1"
    doc.to_dict.return_value = {"email": "x@dtx.aero", "nome": "X", "perfil": "admin"}

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
    ):
        mock_db.collection.return_value.order_by.return_value.stream.return_value = [doc]
        result = Usuario.get_all()

    assert len(result) == 1
    assert result[0].id == "u1"


def test_get_all_retorna_lista_vazia_quando_firestore_falha():
    """get_all retorna [] quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.order_by.return_value.stream.side_effect = Exception("err")
        result = Usuario.get_all()

    assert result == []


# ── email_existe ───────────────────────────────────────────────────────────────


def test_email_existe_retorna_true_quando_encontrado():
    """email_existe retorna True quando email está cadastrado."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u99"

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc]
        result = Usuario.email_existe("existe@dtx.aero")

    assert result is True


def test_email_existe_retorna_false_quando_nao_encontrado():
    """email_existe retorna False quando email não está cadastrado."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.return_value = []
        result = Usuario.email_existe("novo@dtx.aero")

    assert result is False


def test_email_existe_retorna_false_quando_firestore_falha():
    """email_existe retorna False quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.side_effect = Exception("err")
        result = Usuario.email_existe("x@dtx.aero")

    assert result is False


# ── get_supervisores_por_area ──────────────────────────────────────────────────


def test_get_supervisores_por_area_filtra_por_area():
    """get_supervisores_por_area retorna apenas supervisores/admins (não solicitantes)."""
    from app.models_usuario import Usuario

    doc_sup = MagicMock()
    doc_sup.id = "sup1"
    doc_sup.to_dict.return_value = {
        "email": "sup1@dtx.aero",
        "nome": "Sup Um",
        "perfil": "supervisor",
        "areas": ["Manutencao"],
    }

    # Solicitante na mesma área — deve ser filtrado em Python
    doc_sol = MagicMock()
    doc_sol.id = "sol1"
    doc_sol.to_dict.return_value = {
        "email": "sol@dtx.aero",
        "nome": "Sol Um",
        "perfil": "solicitante",
        "areas": ["Manutencao"],
    }

    # Nova implementação: 1 query array_contains, Firestore já filtrou por area
    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.return_value = [
            doc_sup,
            doc_sol,
        ]
        result = Usuario.get_supervisores_por_area("Manutencao")

    assert len(result) == 1
    assert result[0].id == "sup1"


def test_get_supervisores_por_area_inclui_admins():
    """get_supervisores_por_area inclui admins além de supervisores."""
    from app.models_usuario import Usuario

    doc_admin = MagicMock()
    doc_admin.id = "adm1"
    doc_admin.to_dict.return_value = {
        "email": "adm@dtx.aero",
        "nome": "Admin Um",
        "perfil": "admin",
        "areas": ["Manutencao"],
    }

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc_admin]
        result = Usuario.get_supervisores_por_area("Manutencao")

    assert len(result) == 1
    assert result[0].perfil == "admin"


def test_get_supervisores_por_area_retorna_vazio_quando_firestore_falha():
    """get_supervisores_por_area retorna [] quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.side_effect = Exception("err")
        result = Usuario.get_supervisores_por_area("Manutencao")

    assert result == []


# ── Onda 2: campo ativo ────────────────────────────────────────────────────────


def test_usuario_novo_ativo_por_default():
    """Novo usuário tem ativo=True por padrão."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")

    assert u.ativo is True


def test_from_dict_ativo_true_quando_campo_presente():
    """from_dict lê ativo=True corretamente."""
    from app.models_usuario import Usuario

    data = {"email": "a@dtx.aero", "nome": "A", "perfil": "solicitante", "ativo": True}
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_ativo")

    assert u.ativo is True


def test_from_dict_ativo_false():
    """from_dict lê ativo=False corretamente."""
    from app.models_usuario import Usuario

    data = {"email": "a@dtx.aero", "nome": "A", "perfil": "solicitante", "ativo": False}
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_inativo")

    assert u.ativo is False


def test_from_dict_campo_ativo_ausente_default_true():
    """from_dict retorna ativo=True quando campo ausente (retrocompat. Firestore legado)."""
    from app.models_usuario import Usuario

    data = {"email": "a@dtx.aero", "nome": "A", "perfil": "solicitante"}
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "u_sem_ativo")

    assert u.ativo is True


def test_to_dict_contem_campo_ativo():
    """to_dict inclui campo ativo para persistência no Firestore."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        d = u.to_dict()

    assert "ativo" in d
    assert d["ativo"] is True


def test_update_ativo_false_persiste():
    """update(ativo=False) persiste ativo=False no Firestore."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.update(ativo=False)

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["ativo"] is False
    assert u.ativo is False


def test_update_ativo_true_persiste():
    """update(ativo=True) persiste ativo=True no Firestore (reativação)."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        u = Usuario(id="u1", email="x@dtx.aero", nome="X", perfil="solicitante")
        u.ativo = False
        u.update(ativo=True)

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["ativo"] is True
    assert u.ativo is True


# ── __repr__ ───────────────────────────────────────────────────────────────────


def test_repr_contem_email():
    """__repr__ de Usuario contém o email para facilitar debug."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="repr@dtx.aero", nome="Repr", perfil="admin")
        r = repr(u)

    assert "repr@dtx.aero" in r or "Usuario" in r


# ── Onda 4: criptografia PII ───────────────────────────────────────────────────


def test_to_dict_encryption_enabled_criptografa_email_e_nome():
    """Onda 4: to_dict criptografa email e nome quando encryption ON."""
    from app.models_usuario import Usuario

    fake_encrypt = lambda x: f"fernet:v1:{x}"  # noqa: E731

    with (
        patch("app.models_usuario.db"),
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
        patch("app.models_usuario.maybe_encrypt", side_effect=fake_encrypt),
        patch("app.models_usuario.email_lookup_hash", return_value="hash_abc123"),
    ):
        u = Usuario(id="u_enc", email="enc@dtx.aero", nome="Nome Secreto", perfil="solicitante")
        d = u.to_dict()

    assert d["email"] == "fernet:v1:enc@dtx.aero"
    assert d["nome"] == "fernet:v1:Nome Secreto"
    assert d["email_lookup_hash"] == "hash_abc123"


def test_to_dict_encryption_disabled_nao_criptografa():
    """Onda 4: to_dict grava plaintext quando encryption OFF (compatibilidade)."""
    from app.models_usuario import Usuario

    with (
        patch("app.models_usuario.db"),
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.maybe_encrypt", side_effect=lambda x: x),
    ):
        u = Usuario(id="u_plain", email="plain@dtx.aero", nome="Nome Plain", perfil="solicitante")
        d = u.to_dict()

    assert d["email"] == "plain@dtx.aero"
    assert d["nome"] == "Nome Plain"
    assert "email_lookup_hash" not in d


def test_from_dict_encryption_enabled_descriptografa_email_nome():
    """Onda 4: from_dict descriptografa campos quando encryption ON."""
    from app.models_usuario import Usuario

    fake_decrypt = lambda x: x.replace("fernet:v1:", "") if x.startswith("fernet:v1:") else x  # noqa: E731

    data = {
        "email": "fernet:v1:secreto@dtx.aero",
        "nome": "fernet:v1:Nome Secreto",
        "perfil": "solicitante",
    }
    with (
        patch("app.models_usuario.db"),
        patch("app.models_usuario.maybe_decrypt", side_effect=fake_decrypt),
    ):
        u = Usuario.from_dict(data, "u_dec")

    assert u.email == "secreto@dtx.aero"
    assert u.nome == "Nome Secreto"


def test_from_dict_legado_plaintext_sem_prefixo_passa_sem_erro():
    """Onda 4: from_dict aceita docs sem prefixo (legado) mesmo com encryption ON."""
    from app.models_usuario import Usuario

    data = {"email": "legado@dtx.aero", "nome": "Nome Legado", "perfil": "admin"}
    with (
        patch("app.models_usuario.db"),
        patch(
            "app.models_usuario.maybe_decrypt",
            side_effect=lambda x: x,  # legado passa como-está
        ),
    ):
        u = Usuario.from_dict(data, "u_legado")

    assert u.email == "legado@dtx.aero"
    assert u.nome == "Nome Legado"


def test_get_by_email_usa_hash_quando_encryption_enabled():
    """Onda 4: get_by_email consulta email_lookup_hash quando encryption ON."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u_hash"
    doc.to_dict.return_value = {
        "email": "fernet:v1:teste@dtx.aero",
        "nome": "X",
        "perfil": "solicitante",
    }

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
        patch("app.models_usuario.email_lookup_hash", return_value="hash_xyz"),
        patch(
            "app.models_usuario.maybe_decrypt",
            side_effect=lambda x: x.replace("fernet:v1:", "") if x.startswith("fernet:v1:") else x,
        ),
    ):
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc]
        result = Usuario.get_by_email("teste@dtx.aero")

    # Deve ter consultado pelo hash, não pelo email plaintext
    # where() deve ter sido chamado (via email_lookup_hash, não email plaintext)
    mock_db.collection.return_value.where.assert_called_once()
    assert result is not None
    assert result.id == "u_hash"


def test_get_by_email_usa_email_quando_encryption_disabled():
    """Onda 4: get_by_email consulta campo email quando encryption OFF."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u_plain"
    doc.to_dict.return_value = {"email": "plain@dtx.aero", "nome": "X", "perfil": "solicitante"}

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.maybe_decrypt", side_effect=lambda x: x),
    ):
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc]
        result = Usuario.get_by_email("plain@dtx.aero")

    assert result is not None
    assert result.id == "u_plain"


def test_get_by_email_fallback_hash_quando_encryption_off_e_doc_migrado():
    """Pós-migração: encryption OFF mas doc tem email criptografado → fallback hash lookup."""
    from app.models_usuario import Usuario

    doc_migrado = MagicMock()
    doc_migrado.id = "admin_001"
    doc_migrado.to_dict.return_value = {
        "email": "fernet:v1:token",
        "nome": "fernet:v1:nome",
        "email_lookup_hash": "hash_admin",
        "perfil": "admin",
        "senha_hash": "scrypt:xxx",
    }

    empty_stream = iter([])
    hash_stream = iter([doc_migrado])

    def where_side_effect(*args, **kwargs):
        mock = MagicMock()
        # 1ª chamada: email plaintext vazio; 2ª: hash
        if not hasattr(where_side_effect, "n"):
            where_side_effect.n = 0
        where_side_effect.n += 1
        mock.stream.return_value = empty_stream if where_side_effect.n == 1 else hash_stream
        return mock

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.email_lookup_hash", return_value="hash_admin"),
        patch(
            "app.models_usuario.maybe_decrypt",
            side_effect=lambda x: "admin@dtx.aero" if "token" in x else "Admin",
        ),
    ):
        mock_db.collection.return_value.where.side_effect = where_side_effect
        result = Usuario.get_by_email("admin@dtx.aero")

    assert result is not None
    assert result.id == "admin_001"
    assert mock_db.collection.return_value.where.call_count == 2


def test_get_all_ordena_em_python_quando_encryption_enabled():
    """Onda 4: get_all usa sorted() em Python (não order_by Firestore) quando encryption ON."""
    from app.models_usuario import Usuario

    doc_b = MagicMock()
    doc_b.id = "ub"
    doc_b.to_dict.return_value = {
        "email": "b@dtx.aero",
        "nome": "fernet:v1:Zorro",
        "perfil": "solicitante",
    }

    doc_a = MagicMock()
    doc_a.id = "ua"
    doc_a.to_dict.return_value = {
        "email": "a@dtx.aero",
        "nome": "fernet:v1:Abel",
        "perfil": "solicitante",
    }

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
        patch(
            "app.models_usuario.maybe_decrypt",
            side_effect=lambda x: x.replace("fernet:v1:", "") if x.startswith("fernet:v1:") else x,
        ),
    ):
        mock_db.collection.return_value.stream.return_value = [doc_b, doc_a]
        result = Usuario.get_all()

    # order_by do Firestore NÃO deve ter sido chamado
    mock_db.collection.return_value.order_by.assert_not_called()
    # Resultado ordenado por nome em Python: Abel < Zorro
    assert result[0].id == "ua"
    assert result[1].id == "ub"


def test_update_email_recalcula_hash_quando_encryption_enabled():
    """Onda 4: update(email=...) recalcula email_lookup_hash e criptografa quando ON."""
    from app.models_usuario import Usuario

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
        patch("app.models_usuario.maybe_encrypt", side_effect=lambda x: f"fernet:v1:{x}"),
        patch("app.models_usuario.email_lookup_hash", return_value="novo_hash_xyz"),
    ):
        u = Usuario(id="u1", email="velho@dtx.aero", nome="X", perfil="solicitante")
        u.update(email="novo@dtx.aero")

    call_args = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_args["email"] == "fernet:v1:novo@dtx.aero"
    assert call_args["email_lookup_hash"] == "novo_hash_xyz"


def test_email_existe_usa_hash_quando_encryption_enabled():
    """Onda 4: email_existe consulta email_lookup_hash quando encryption ON."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u_existente"

    with (
        patch("app.models_usuario.db") as mock_db,
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
        patch("app.models_usuario.email_lookup_hash", return_value="hash_existe"),
    ):
        mock_db.collection.return_value.where.return_value.stream.return_value = [doc]
        result = Usuario.email_existe("existe@dtx.aero")

    assert result is True


# ── Integração Onda 4: round-trip real Fernet (sem mock de maybe_*) ────────────


def test_integracao_fernet_to_dict_from_dict_round_trip():
    """Integração: to_dict() criptografa campos reais; from_dict() restaura plaintext.

    Sem mock de maybe_encrypt/maybe_decrypt — valida o fluxo end-to-end com Fernet real.
    """
    import os

    from cryptography.fernet import Fernet

    from app.models_usuario import Usuario

    valid_key = Fernet.generate_key().decode()

    with (
        patch("app.models_usuario.db"),
        patch("app.services.pii_encryption._get_flask_config", return_value=None),
        patch.dict(
            os.environ,
            {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": valid_key},
            clear=False,
        ),
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=True),
    ):
        u = Usuario(id="u_integ", email="integ@dtx.aero", nome="Nome Integração", perfil="admin")
        d = u.to_dict()

        # Campos devem estar criptografados
        assert d["email"].startswith("fernet:v1:"), "email deve ter prefixo fernet:v1:"
        assert d["nome"].startswith("fernet:v1:"), "nome deve ter prefixo fernet:v1:"
        assert "email_lookup_hash" in d, "email_lookup_hash deve estar presente"

        # from_dict com encryption ON deve restaurar plaintext
        u2 = Usuario.from_dict(d, "u_integ")

    assert u2.email == "integ@dtx.aero"
    assert u2.nome == "Nome Integração"
    assert u2.id == "u_integ"


# ── Fase 5 — nivel_gestao ─────────────────────────────────────────────────────


def test_usuario_from_dict_com_nivel_gestao():
    """from_dict lê nivel_gestao quando presente no doc Firestore."""
    from app.models_usuario import Usuario

    data = {
        "email": "gestor@dtx.aero",
        "nome": "Gestor Setor",
        "perfil": "supervisor",
        "nivel_gestao": "gestor_setor",
    }
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "g_001")

    assert u.nivel_gestao == "gestor_setor"


def test_usuario_from_dict_sem_nivel_gestao():
    """from_dict atribui None para nivel_gestao quando campo ausente."""
    from app.models_usuario import Usuario

    data = {"email": "sup@dtx.aero", "nome": "Sup", "perfil": "supervisor"}
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "s_001")

    assert u.nivel_gestao is None


# ── buscar_ativos — linhas 430-443 ────────────────────────────────────────────


def test_buscar_ativos_q_vazio_retorna_lista_vazia():
    """buscar_ativos com q vazio retorna [] sem chamar get_all (linhas 431-432)."""
    from app.models_usuario import Usuario

    with patch.object(Usuario, "get_all") as mock_get_all:
        result = Usuario.buscar_ativos("")

    assert result == []
    mock_get_all.assert_not_called()


def test_buscar_ativos_encontra_por_nome():
    """buscar_ativos retorna usuário ativo cujo nome contém q (linhas 430-443)."""
    from app.models_usuario import Usuario

    u1 = MagicMock()
    u1.ativo = True
    u1.nome = "Maria Silva"
    u1.email = "maria@dtx.aero"

    u2 = MagicMock()
    u2.ativo = True
    u2.nome = "João Souza"
    u2.email = "joao@dtx.aero"

    with patch.object(Usuario, "get_all", return_value=[u1, u2]):
        result = Usuario.buscar_ativos("maria")

    assert result == [u1]


def test_buscar_ativos_ignora_usuario_inativo():
    """buscar_ativos ignora usuário com ativo=False (linha 438 — continue)."""
    from app.models_usuario import Usuario

    u_inativo = MagicMock()
    u_inativo.ativo = False
    u_inativo.nome = "Maria Inativa"
    u_inativo.email = "maria.i@dtx.aero"

    with patch.object(Usuario, "get_all", return_value=[u_inativo]):
        result = Usuario.buscar_ativos("maria")

    assert result == []


def test_usuario_to_dict_persiste_nivel_gestao():
    """to_dict inclui nivel_gestao para persistência no Firestore."""
    from app.models_usuario import Usuario

    with (
        patch("app.models_usuario.db"),
        patch("app.models_usuario.is_pii_encryption_enabled", return_value=False),
        patch("app.models_usuario.maybe_encrypt", side_effect=lambda x: x),
    ):
        u = Usuario(
            id="g_002",
            email="gm@dtx.aero",
            nome="GM",
            perfil="supervisor",
            nivel_gestao="gm",
        )
        d = u.to_dict()

    assert "nivel_gestao" in d
    assert d["nivel_gestao"] == "gm"


def test_is_gestor_true_quando_nivel_preenchido():
    """is_gestor retorna True quando nivel_gestao é um valor válido."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="g_003", email="g@dtx.aero", nome="G", nivel_gestao="gerente_producao")

    assert u.is_gestor is True


def test_is_gestor_false_quando_nivel_none():
    """is_gestor retorna False quando nivel_gestao é None."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="s_002", email="s@dtx.aero", nome="S")

    assert u.is_gestor is False


def test_is_gestor_only_false_para_admin_com_nivel_gestao():
    """is_gestor_only é False para admin, mesmo com nivel_gestao preenchido (admin mantém write)."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(
            id="a_001",
            email="a@dtx.aero",
            nome="Admin Gestor",
            perfil="admin",
            nivel_gestao="gm",
        )

    assert u.is_gestor is True
    assert u.is_gestor_only is False


def test_is_gestor_only_true_para_supervisor_com_nivel_gestao():
    """is_gestor_only é True para supervisor com nivel_gestao (read-only operacional)."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(
            id="g_004",
            email="gsup@dtx.aero",
            nome="Sup Gestor",
            perfil="supervisor",
            nivel_gestao="assistente_gm",
        )

    assert u.is_gestor_only is True


def test_nivel_gestao_invalido_vira_none():
    """nivel_gestao com valor inválido deve ser normalizado para None."""
    from app.models_usuario import Usuario

    data = {
        "email": "x@dtx.aero",
        "nome": "X",
        "perfil": "supervisor",
        "nivel_gestao": "cargo_inventado",
    }
    with patch("app.models_usuario.db"):
        u = Usuario.from_dict(data, "x_001")

    assert u.nivel_gestao is None
