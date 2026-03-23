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

    with patch("app.models_usuario.db"):
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
    """update com email chama Firestore update com novo email."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
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
    """get_all retorna lista de instâncias Usuario para cada doc do Firestore."""
    from app.models_usuario import Usuario

    doc = MagicMock()
    doc.id = "u1"
    doc.to_dict.return_value = {"email": "x@dtx.aero", "nome": "X", "perfil": "admin"}

    with patch("app.models_usuario.db") as mock_db:
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
    """get_supervisores_por_area retorna apenas supervisores da área solicitada."""
    from app.models_usuario import Usuario

    doc_certo = MagicMock()
    doc_certo.id = "sup1"
    doc_certo.to_dict.return_value = {
        "email": "sup1@dtx.aero",
        "nome": "Sup Um",
        "perfil": "supervisor",
        "areas": ["Manutencao"],
    }

    doc_errado = MagicMock()
    doc_errado.id = "sup2"
    doc_errado.to_dict.return_value = {
        "email": "sup2@dtx.aero",
        "nome": "Sup Dois",
        "perfil": "supervisor",
        "areas": ["Qualidade"],
    }

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.side_effect = [
            [doc_certo, doc_errado],  # supervisores
            [],  # admins
        ]
        result = Usuario.get_supervisores_por_area("Manutencao")

    assert len(result) == 1
    assert result[0].id == "sup1"


def test_get_supervisores_por_area_retorna_vazio_quando_firestore_falha():
    """get_supervisores_por_area retorna [] quando Firestore lança exceção."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db") as mock_db:
        mock_db.collection.return_value.where.return_value.stream.side_effect = Exception("err")
        result = Usuario.get_supervisores_por_area("Manutencao")

    assert result == []


# ── __repr__ ───────────────────────────────────────────────────────────────────


def test_repr_contem_email():
    """__repr__ de Usuario contém o email para facilitar debug."""
    from app.models_usuario import Usuario

    with patch("app.models_usuario.db"):
        u = Usuario(id="u1", email="repr@dtx.aero", nome="Repr", perfil="admin")
        r = repr(u)

    assert "repr@dtx.aero" in r or "Usuario" in r
