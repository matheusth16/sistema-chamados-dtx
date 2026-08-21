"""
Testes do modelo Usuario (Fase 2 — Postgres real).

Substitui a suíte anterior baseada em mock do Firestore. Persistência
(save/update/delete/get_*) roda contra Postgres real (db_session); lógica
pura (from_dict/to_dict/properties) não precisa do banco, mas herda a
fixture via pytestmark por simplicidade.
"""

import os
from datetime import datetime
from unittest.mock import patch

import pytest

from app.models_usuario import NIVEIS_GESTAO_VALIDOS, Usuario

pytestmark = pytest.mark.usefixtures("db_session")


def _pii_off():
    """Desliga PII encryption de verdade (env var real) — patchar só
    app.models_usuario.is_pii_encryption_enabled não é suficiente, já que
    maybe_encrypt/maybe_decrypt (pii_encryption.py) chamam a própria versão
    do módulo deles, não a referência importada em models_usuario.py."""
    return patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "false"})


def _pii_on():
    """Liga PII encryption de verdade, com uma chave Fernet válida gerada
    na hora (não depende da ENCRYPTION_KEY do .env local)."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    return patch.dict(os.environ, {"ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": key})


# ── from_dict / to_dict (lógica pura, sem banco) ─────────────────────────────


def test_from_dict_campos_basicos():
    u = Usuario.from_dict(
        {"email": "a@b.com", "nome": "Fulano", "perfil": "supervisor", "areas": ["TI"]},
        id="u1",
    )
    assert u.id == "u1"
    assert u.email == "a@b.com"
    assert u.nome == "Fulano"
    assert u.perfil == "supervisor"
    assert u.areas == ["TI"]


def test_from_dict_migra_area_string_para_areas_lista():
    u = Usuario.from_dict({"email": "a@b.com", "nome": "F", "area": "Manutencao"}, id="u1")
    assert u.areas == ["Manutencao"]


def test_from_dict_password_changed_at_isoformat():
    u = Usuario.from_dict(
        {"email": "a@b.com", "nome": "F", "password_changed_at": "2026-01-01T10:00:00"}, id="u1"
    )
    assert u.password_changed_at == datetime.fromisoformat("2026-01-01T10:00:00")


def test_from_dict_password_changed_at_invalido_vira_none():
    u = Usuario.from_dict(
        {"email": "a@b.com", "nome": "F", "password_changed_at": "nao-e-data"}, id="u1"
    )
    assert u.password_changed_at is None


def test_is_supervisor_or_above_true_para_supervisor_admin_e_admin_global():
    assert Usuario(id="u1", email="a@b.com", nome="F", perfil="supervisor").is_supervisor_or_above
    assert Usuario(id="u2", email="a@b.com", nome="F", perfil="admin").is_supervisor_or_above
    assert Usuario(id="u3", email="a@b.com", nome="F", perfil="admin_global").is_supervisor_or_above


def test_is_supervisor_or_above_false_para_solicitante():
    assert not Usuario(
        id="u1", email="a@b.com", nome="F", perfil="solicitante"
    ).is_supervisor_or_above


def test_to_public_dict_nao_contem_senha_hash():
    u = Usuario(id="u1", email="a@b.com", nome="Fulano", perfil="solicitante")
    u.set_password("segredo123")

    d = u.to_public_dict()

    assert d["id"] == "u1"
    assert d["email"] == "a@b.com"
    assert d["nome"] == "Fulano"
    assert "senha_hash" not in d


def test_invalidar_cache_supervisores_por_area_e_noop():
    """Método é placeholder (no-op) — só garante que existe e não lança."""
    assert Usuario.invalidar_cache_supervisores_por_area() is None


def test_to_dict_contem_campos_esperados():
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="Fulano", perfil="solicitante")
        d = u.to_dict()

    assert d["email"] == "a@b.com"
    assert d["nome"] == "Fulano"
    assert d["perfil"] == "solicitante"
    assert "email_lookup_hash" not in d


def test_to_dict_encryption_enabled_criptografa_email_e_nome():
    with _pii_on():
        u = Usuario(id="u1", email="a@b.com", nome="Fulano")
        d = u.to_dict()

    assert d["email"] != "a@b.com"
    assert d["nome"] != "Fulano"
    assert "email_lookup_hash" in d


def test_set_password_e_check_password():
    u = Usuario(id="u1", email="a@b.com", nome="F")
    u.set_password("minhasenha123")
    assert u.check_password("minhasenha123") is True
    assert u.check_password("errada") is False


def test_check_password_sem_hash_retorna_false():
    u = Usuario(id="u1", email="a@b.com", nome="F")
    assert u.check_password("qualquer") is False


def test_area_property_com_areas():
    u = Usuario(id="u1", email="a@b.com", nome="F", areas=["TI", "RH"])
    assert u.area == "TI, RH"


def test_area_property_sem_areas():
    u = Usuario(id="u1", email="a@b.com", nome="F", areas=[])
    assert u.area is None


def test_nivel_gestao_invalido_vira_none():
    u = Usuario(id="u1", email="a@b.com", nome="F", nivel_gestao="valor_invalido")
    assert u.nivel_gestao is None


def test_nivel_gestao_valido_e_preservado():
    valido = next(iter(NIVEIS_GESTAO_VALIDOS))
    u = Usuario(id="u1", email="a@b.com", nome="F", nivel_gestao=valido)
    assert u.nivel_gestao == valido


def test_is_gestor_true_quando_nivel_preenchido():
    u = Usuario(id="u1", email="a@b.com", nome="F", nivel_gestao="gestor_setor")
    assert u.is_gestor is True


def test_is_gestor_false_quando_nivel_none():
    u = Usuario(id="u1", email="a@b.com", nome="F")
    assert u.is_gestor is False


def test_is_gestor_only_true_para_solicitante_com_nivel_gestao():
    u = Usuario(id="u1", email="a@b.com", nome="F", perfil="solicitante", nivel_gestao="gm")
    assert u.is_gestor_only is True


def test_is_gestor_only_false_para_supervisor_com_nivel_gestao():
    u = Usuario(id="u1", email="a@b.com", nome="F", perfil="supervisor", nivel_gestao="gm")
    assert u.is_gestor_only is False


def test_repr_contem_email():
    u = Usuario(id="u1", email="a@b.com", nome="F")
    assert "a@b.com" in repr(u)


# ── save / get_by_id / update / delete (Postgres real) ───────────────────────


def test_save_novo_persiste_e_get_by_id_recupera(app):
    with _pii_off():
        u = Usuario(id="u_novo", email="novo@b.com", nome="Novo", perfil="solicitante")
        u.set_password("senha123")
        assert u.save() is True

        recarregado = Usuario.get_by_id("u_novo")

    assert recarregado is not None
    assert recarregado.email == "novo@b.com"
    assert recarregado.nome == "Novo"
    assert recarregado.check_password("senha123") is True


def test_save_existente_sobrescreve(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="Original")
        u.save()
        u.nome = "Renomeado"
        u.save()

        recarregado = Usuario.get_by_id("u1")

    assert recarregado.nome == "Renomeado"


def test_get_by_id_nao_encontrado_retorna_none(app):
    assert Usuario.get_by_id("nao-existe") is None


def test_update_email_atualiza_campo(app):
    with _pii_off():
        u = Usuario(id="u1", email="antigo@b.com", nome="F")
        u.save()

        resultado = u.update(email="novo@b.com")
        recarregado = Usuario.get_by_id("u1")

    assert resultado is True
    assert recarregado.email == "novo@b.com"


def test_update_gamification_atualiza_exp_e_level(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(gamification={"exp_total": 100, "level": 3})
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.exp_total == 100
    assert recarregado.level == 3


def test_update_gamification_atualiza_exp_semanal_e_conquistas(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(gamification={"exp_semanal": 50, "conquistas": ["primeira_missao"]})
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.exp_semanal == 50
    assert recarregado.conquistas == ["primeira_missao"]


def test_update_email_com_encryption_enabled_atualiza_lookup_hash(app):
    with _pii_on():
        u = Usuario(id="u1", email="antigo@b.com", nome="F")
        u.save()

        resultado = u.update(email="novo_cripto@b.com")

    assert resultado is True
    assert Usuario.email_existe("novo_cripto@b.com") is True


def test_update_nome_atualiza_campo(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="Original")
        u.save()

        u.update(nome="Renomeado")
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.nome == "Renomeado"


def test_update_perfil_e_areas_atualiza_campos(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F", perfil="solicitante")
        u.save()

        u.update(perfil="supervisor", areas=["TI", "RH"])
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.perfil == "supervisor"
    assert recarregado.areas == ["TI", "RH"]


def test_update_senha_atualiza_hash(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(senha="novaSenha123")
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.check_password("novaSenha123") is True


def test_update_senha_vazia_nao_atualiza(app):
    """update(senha="") não deve entrar no branch de troca de senha (senha falsy)."""
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.set_password("original")
        u.save()

        resultado = u.update(senha="")

    assert resultado is False


def test_update_must_change_password_e_password_changed_at(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        agora = datetime.now()
        u.update(must_change_password=True, password_changed_at=agora)
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.must_change_password is True
    assert recarregado.password_changed_at is not None


def test_update_onboarding_atualiza_perfis_vistos_e_passo(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(
            onboarding_perfis_vistos=["solicitante", "perfil_invalido_ignorado"],
            onboarding_passo=3,
        )
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.onboarding_perfis_vistos == ["solicitante"]
    assert recarregado.onboarding_passo == 3


def test_update_ativo_atualiza_campo(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(ativo=False)
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.ativo is False


def test_update_nivel_gestao_valido_e_invalido(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(nivel_gestao="gestor_setor")
        assert Usuario.get_by_id("u1").nivel_gestao == "gestor_setor"

        u.update(nivel_gestao="valor_que_nao_existe")
        assert Usuario.get_by_id("u1").nivel_gestao is None


def test_update_mfa_enabled_e_backup_codes(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(mfa_enabled=True, mfa_backup_codes=["code1", "code2"])
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.mfa_enabled is True
    assert recarregado.mfa_backup_codes == ["code1", "code2"]


def test_update_mfa_secret_atualiza_campo_criptografado(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(mfa_secret="JBSWY3DPEHPK3PXP")
        recarregado = Usuario.get_by_id("u1")

    assert recarregado.mfa_secret == "JBSWY3DPEHPK3PXP"


def test_update_auth_provider_valido_e_invalido(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        u.update(auth_provider="microsoft")
        assert Usuario.get_by_id("u1").auth_provider == "microsoft"

        u.update(auth_provider="valor_que_nao_existe")
        assert Usuario.get_by_id("u1").auth_provider == "local"


def test_update_sem_campos_retorna_false(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        assert u.update() is False


def test_update_usuario_inexistente_retorna_false(app):
    u = Usuario(id="nao-existe", email="a@b.com", nome="F")
    assert u.update(nome="X") is False


def test_delete_remove_usuario(app):
    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

        assert u.delete() is True
        assert Usuario.get_by_id("u1") is None


# ── get_all ───────────────────────────────────────────────────────────────────


def test_get_all_retorna_lista_ordenada_por_nome_encryption_off(app):
    with _pii_off():
        Usuario(id="u_z", email="z@b.com", nome="Zeca").save()
        Usuario(id="u_a", email="a@b.com", nome="Ana").save()

        resultado = Usuario.get_all()

    nomes = [u.nome for u in resultado]
    assert nomes.index("Ana") < nomes.index("Zeca")


def test_get_all_ordena_em_python_quando_encryption_enabled(app):
    with _pii_on():
        Usuario(id="u_z2", email="z2@b.com", nome="Zeca2").save()
        Usuario(id="u_a2", email="a2@b.com", nome="Ana2").save()

        resultado = Usuario.get_all()

    nomes = [u.nome for u in resultado]
    assert nomes.index("Ana2") < nomes.index("Zeca2")


def test_get_all_sem_usuarios_retorna_lista_vazia(app):
    assert Usuario.get_all() == []


def test_get_all_atinge_teto_de_seguranca_loga_aviso_encryption_off(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario, "MAX_USUARIOS_GET_ALL", 1)

    with _pii_off():
        Usuario(id="u1", email="a@b.com", nome="A").save()
        Usuario(id="u2", email="b@b.com", nome="B").save()

        resultado = Usuario.get_all()

    assert len(resultado) == 1  # limit aplicado pelo teto rebaixado


def test_get_all_atinge_teto_de_seguranca_loga_aviso_encryption_on(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario, "MAX_USUARIOS_GET_ALL", 1)

    with _pii_on():
        Usuario(id="u1", email="a@b.com", nome="A").save()
        Usuario(id="u2", email="b@b.com", nome="B").save()

        resultado = Usuario.get_all()

    assert len(resultado) == 1


# ── get_sem_mfa ──────────────────────────────────────────────────────────────


def test_get_sem_mfa_retorna_apenas_ativos_sem_mfa(app):
    with _pii_off():
        Usuario(id="u_sem_mfa", email="sem@b.com", nome="Sem MFA", mfa_enabled=False).save()
        Usuario(id="u_com_mfa", email="com@b.com", nome="Com MFA", mfa_enabled=True).save()
        Usuario(
            id="u_inativo",
            email="inativo@b.com",
            nome="Inativo Sem MFA",
            mfa_enabled=False,
            ativo=False,
        ).save()

        resultado = Usuario.get_sem_mfa()

    ids = [u.id for u in resultado]
    assert ids == ["u_sem_mfa"]


def test_get_sem_mfa_ordenado_por_nome(app):
    with _pii_off():
        Usuario(id="u_z", email="z@b.com", nome="Zeca", mfa_enabled=False).save()
        Usuario(id="u_a", email="a@b.com", nome="Ana", mfa_enabled=False).save()

        resultado = Usuario.get_sem_mfa()

    nomes = [u.nome for u in resultado]
    assert nomes.index("Ana") < nomes.index("Zeca")


def test_get_sem_mfa_sem_usuarios_retorna_lista_vazia(app):
    with _pii_off():
        resultado = Usuario.get_sem_mfa()

    assert resultado == []


# ── email_existe ──────────────────────────────────────────────────────────────


def test_email_existe_retorna_true_quando_encontrado(app):
    with _pii_off():
        Usuario(id="u1", email="existe@b.com", nome="F").save()

        assert Usuario.email_existe("existe@b.com") is True


def test_email_existe_retorna_false_quando_nao_encontrado(app):
    with _pii_off():
        assert Usuario.email_existe("naoexiste@b.com") is False


def test_email_existe_ignora_id_atual(app):
    with _pii_off():
        Usuario(id="u1", email="proprio@b.com", nome="F").save()

        assert Usuario.email_existe("proprio@b.com", id_atual="u1") is False


def test_email_existe_usa_hash_quando_encryption_enabled(app):
    with _pii_on():
        Usuario(id="u1", email="cripto@b.com", nome="F").save()

        assert Usuario.email_existe("cripto@b.com") is True
        assert Usuario.email_existe("outro@b.com") is False


def test_email_existe_vazio_retorna_false(app):
    assert Usuario.email_existe("   ") is False


# ── get_by_email ──────────────────────────────────────────────────────────────


def test_get_by_email_encryption_disabled(app):
    with _pii_off():
        Usuario(id="u1", email="plain@b.com", nome="F").save()

        resultado = Usuario.get_by_email("plain@b.com")

    assert resultado is not None
    assert resultado.id == "u1"


def test_get_by_email_usa_hash_quando_encryption_enabled(app):
    with _pii_on():
        Usuario(id="u1", email="cripto2@b.com", nome="F").save()

        resultado = Usuario.get_by_email("cripto2@b.com")

    assert resultado is not None
    assert resultado.id == "u1"


def test_get_by_email_nao_encontrado_retorna_none(app):
    with _pii_off():
        assert Usuario.get_by_email("naoexiste@b.com") is None


def test_get_by_email_vazio_retorna_none(app):
    assert Usuario.get_by_email("") is None
    assert Usuario.get_by_email(None) is None


# ── get_by_ids ────────────────────────────────────────────────────────────────


def test_get_by_ids_retorna_dict_com_encontrados(app):
    with _pii_off():
        Usuario(id="u1", email="a@b.com", nome="A").save()
        Usuario(id="u2", email="b@b.com", nome="B").save()

        resultado = Usuario.get_by_ids(["u1", "u2", "nao-existe"])

    assert set(resultado.keys()) == {"u1", "u2"}
    assert resultado["u1"].nome == "A"


def test_get_by_ids_lista_vazia_retorna_dict_vazio(app):
    assert Usuario.get_by_ids([]) == {}


# ── get_supervisores_por_area ─────────────────────────────────────────────────


def test_get_supervisores_por_area_filtra_por_area_e_perfil(app):
    with _pii_off():
        Usuario(id="sup1", email="s1@b.com", nome="Sup1", perfil="supervisor", areas=["TI"]).save()
        Usuario(id="sup2", email="s2@b.com", nome="Sup2", perfil="supervisor", areas=["RH"]).save()
        Usuario(
            id="sol1", email="so1@b.com", nome="Sol1", perfil="solicitante", areas=["TI"]
        ).save()

        resultado = Usuario.get_supervisores_por_area("TI")

    ids = {u.id for u in resultado}
    assert ids == {"sup1"}


def test_get_supervisores_por_area_inclui_admins(app):
    with _pii_off():
        Usuario(id="adm1", email="a1@b.com", nome="Adm1", perfil="admin", areas=["TI"]).save()

        resultado = Usuario.get_supervisores_por_area("TI")

    assert any(u.id == "adm1" for u in resultado)


def test_get_supervisores_por_area_sem_resultado_retorna_vazio(app):
    assert Usuario.get_supervisores_por_area("Area Sem Ninguem") == []


# ── buscar_ativos ─────────────────────────────────────────────────────────────


def test_buscar_ativos_q_vazio_retorna_lista_vazia(app):
    assert Usuario.buscar_ativos("") == []


def test_buscar_ativos_encontra_por_nome(app):
    with _pii_off():
        Usuario(id="u1", email="a@b.com", nome="Fulano Silva").save()

        resultado = Usuario.buscar_ativos("fulano")

    assert len(resultado) == 1


def test_buscar_ativos_ignora_usuario_inativo(app):
    with _pii_off():
        Usuario(id="u1", email="a@b.com", nome="Inativo Fulano", ativo=False).save()

        resultado = Usuario.buscar_ativos("fulano")

    assert resultado == []


def test_buscar_ativos_ignora_acento_na_busca(app):
    """Regressão (achado ao vivo, 2026-08-21): busca de observadores não
    ignorava acento — "Júlia" (grafia correta em português) não encontrava
    "Julia Salgado" cadastrada sem acento no banco. Confirmado em produção via
    Usuario.buscar_ativos("Júlia") retornando [] enquanto "Julia" achava."""
    with _pii_off():
        Usuario(id="u1", email="julia@b.com", nome="Julia Salgado").save()

        resultado = Usuario.buscar_ativos("Júlia")

    assert len(resultado) == 1
    assert resultado[0].nome == "Julia Salgado"


def test_buscar_ativos_ignora_acento_no_nome_cadastrado(app):
    """Caso inverso: nome cadastrado COM acento deve ser encontrado buscando
    sem acento."""
    with _pii_off():
        Usuario(id="u1", email="joao@b.com", nome="João Ísis").save()

        resultado = Usuario.buscar_ativos("joao isis")

    assert len(resultado) == 1


# ── Exceções de banco (SessionLocal indisponível) ─────────────────────────────


def _explode():
    raise RuntimeError("banco indisponível")


def test_get_by_email_excecao_no_banco_retorna_none(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.get_by_email("qualquer@b.com") is None


def test_get_by_id_excecao_no_banco_retorna_none(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.get_by_id("qualquer") is None


def test_save_excecao_no_banco_retorna_false(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    u = Usuario(id="u1", email="a@b.com", nome="F")
    assert u.save() is False


def test_update_excecao_no_banco_retorna_false(app, monkeypatch):
    from app import models_usuario

    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert u.update(nome="Outro") is False


def test_delete_excecao_no_banco_retorna_false(app, monkeypatch):
    from app import models_usuario

    with _pii_off():
        u = Usuario(id="u1", email="a@b.com", nome="F")
        u.save()

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert u.delete() is False


def test_get_by_ids_excecao_no_banco_retorna_dict_vazio(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.get_by_ids(["u1", "u2"]) == {}


def test_get_all_excecao_no_banco_retorna_lista_vazia(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.get_all() == []


def test_email_existe_excecao_no_banco_retorna_false(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.email_existe("qualquer@b.com") is False


def test_buscar_ativos_excecao_retorna_lista_vazia(app, monkeypatch):
    """buscar_ativos tem seu próprio try/except em volta de get_all() — get_all()
    já engole exceção de SessionLocal e retorna [], então pra exercitar o except
    de buscar_ativos é preciso que get_all() em si lance."""
    monkeypatch.setattr(
        Usuario, "get_all", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    assert Usuario.buscar_ativos("qualquer") == []


def test_get_supervisores_por_area_excecao_no_banco_retorna_lista_vazia(app, monkeypatch):
    from app import models_usuario

    monkeypatch.setattr(models_usuario.db_module, "SessionLocal", _explode)

    assert Usuario.get_supervisores_por_area("TI") == []


# ── Fernet round-trip (integração real com pii_encryption) ───────────────────


def test_integracao_fernet_to_dict_from_dict_round_trip():
    with _pii_on():
        u = Usuario(id="u1", email="secreto@b.com", nome="Nome Secreto")
        d = u.to_dict()
        assert d["email"] != "secreto@b.com"

        recuperado = Usuario.from_dict(d, id="u1")
        assert recuperado.email == "secreto@b.com"
        assert recuperado.nome == "Nome Secreto"
