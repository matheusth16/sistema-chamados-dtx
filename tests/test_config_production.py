"""Testes de hardening de configuração em produção — CWI 2.1 / Onda 3.

Cobre:
- Fail-fast para APP_BASE_URL, HEALTH_SECRET (obrigatórias em prod)
- Redis warning vs fail-fast (REQUIRE_REDIS / GUNICORN_WORKERS)
- Ambientes não-prod não quebram no boot
- Testes de reload isolado (boot real simulado via importlib.reload)
- Cross-ref CWI 2.1: redirect HTTP→HTTPS (evidência principal em test_app_init.py)
- Cookies Secure: default True em produção

Não duplica testes já em test_app_init.py (HTTPS redirect, HSTS).
"""

import importlib
import os
import sys
import warnings
from unittest.mock import patch

import pytest

# ── _validar_config_producao (unit tests da função pura) ─────────────────────
from config import _validar_config_producao, _validar_fernet_key

# Env vars mínimas para boot em produção sem falha (usado nos reload tests)
_PROD_ENV_VALIDO = {
    "FLASK_ENV": "production",
    "SECRET_KEY": "producao-test-key-forte-e-unica-32x!!",
    "APP_BASE_URL": "https://chamados.example.com",
    "HEALTH_SECRET": "minhachavefort32xtest",
    "REDIS_URL": "redis://localhost:6379/0",
    "REQUIRE_REDIS": "false",
    "GUNICORN_WORKERS": "1",
    # Garante que SESSION_COOKIE_SECURE vazia → default True em prod (sobrepõe .env local se houver)
    "SESSION_COOKIE_SECURE": "",
}

# Env vars para restaurar config ao estado testing após reload
_ENV_RESTORE = {
    "FLASK_ENV": "testing",
    "SECRET_KEY": "test-secret-restore-only",
    "APP_BASE_URL": "",
    "HEALTH_SECRET": "",
    "REDIS_URL": "",
    "REQUIRE_REDIS": "false",
    "GUNICORN_WORKERS": "1",
    "SESSION_COOKIE_SECURE": "",  # vazia → default False em testing
}


def _restaurar_config() -> None:
    """Recarrega config.py em modo testing para restaurar estado após reload isolado."""
    config_mod = sys.modules.get("config")
    if config_mod is None:
        return
    with patch.dict(os.environ, _ENV_RESTORE, clear=False):
        importlib.reload(config_mod)


def _args_prod_ok() -> dict:
    """Argumentos mínimos válidos para produção."""
    return {
        "env": "production",
        "app_base_url": "https://chamados.dtx.aero",
        "health_secret": "minhachavesecreta32x",
        "redis_url": "redis://localhost:6379/0",
        "require_redis": False,
        "gunicorn_workers": 1,
    }


# ── Obrigatórias — fail-fast ───────────────────────────────────────────────


def test_prod_sem_app_base_url_raises():
    """Prod sem APP_BASE_URL → ValueError com menção a APP_BASE_URL."""
    args = _args_prod_ok()
    args["app_base_url"] = ""
    with pytest.raises(ValueError, match="APP_BASE_URL"):
        _validar_config_producao(**args)


def test_prod_app_base_url_http_raises():
    """Prod com APP_BASE_URL=http:// → ValueError (exige HTTPS)."""
    args = _args_prod_ok()
    args["app_base_url"] = "http://chamados.dtx.aero"
    with pytest.raises(ValueError, match="[Hh][Tt][Tt][Pp][Ss]"):
        _validar_config_producao(**args)


def test_prod_sem_health_secret_raises():
    """Prod sem HEALTH_SECRET → ValueError com menção a HEALTH_SECRET."""
    args = _args_prod_ok()
    args["health_secret"] = ""
    with pytest.raises(ValueError, match="HEALTH_SECRET"):
        _validar_config_producao(**args)


def test_prod_health_secret_muito_curto_raises():
    """Prod com HEALTH_SECRET < 16 chars → ValueError mencionando 16."""
    args = _args_prod_ok()
    args["health_secret"] = "curto"
    with pytest.raises(ValueError, match="16"):
        _validar_config_producao(**args)


# ── Redis — warning vs fail-fast ───────────────────────────────────────────


def test_prod_sem_redis_um_worker_require_false_sobe_com_warning():
    """1 worker + REQUIRE_REDIS=false + sem REDIS_URL → sobe; emite warning REDIS_URL."""
    args = _args_prod_ok()
    args["redis_url"] = ""
    args["require_redis"] = False
    args["gunicorn_workers"] = 1

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        _validar_config_producao(**args)  # não deve levantar

    assert any("REDIS_URL" in str(w.message) for w in captured), (
        "Esperado warning sobre REDIS_URL ausente"
    )


def test_prod_sem_redis_dois_workers_raises():
    """2 workers + sem REDIS_URL → ValueError (rate limit não funciona entre processos)."""
    args = _args_prod_ok()
    args["redis_url"] = ""
    args["require_redis"] = False
    args["gunicorn_workers"] = 2

    with pytest.raises(ValueError, match="GUNICORN_WORKERS"):
        _validar_config_producao(**args)


def test_prod_sem_redis_require_redis_true_raises():
    """REQUIRE_REDIS=true + sem REDIS_URL → ValueError mesmo com 1 worker."""
    args = _args_prod_ok()
    args["redis_url"] = ""
    args["require_redis"] = True
    args["gunicorn_workers"] = 1

    with pytest.raises(ValueError, match="REQUIRE_REDIS"):
        _validar_config_producao(**args)


def test_prod_com_redis_definido_nao_raise():
    """Prod com REDIS_URL definida → nenhum erro nem warning."""
    args = _args_prod_ok()
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        _validar_config_producao(**args)
    redis_warnings = [w for w in captured if "REDIS_URL" in str(w.message)]
    assert not redis_warnings


# ── Ambientes não-prod ignoram validação ──────────────────────────────────


def test_development_ignora_validacao():
    """Em development, vars obrigatórias de prod ausentes não levantam erro."""
    _validar_config_producao(
        env="development",
        app_base_url="",
        health_secret="",
        redis_url="",
        require_redis=False,
        gunicorn_workers=1,
    )


def test_testing_ignora_validacao():
    """Em testing (conftest.py), vars obrigatórias de prod ausentes não levantam erro."""
    _validar_config_producao(
        env="testing",
        app_base_url="",
        health_secret="",
        redis_url="",
        require_redis=False,
        gunicorn_workers=1,
    )


def test_conftest_app_base_url_vazio_nao_quebra_boot(app):
    """conftest.py define APP_BASE_URL='' em testing — não deve quebrar o boot."""
    assert app.config.get("APP_BASE_URL") == ""


# ── Prod válida completa — smoke ──────────────────────────────────────────


def test_prod_config_completa_valida_nao_raise():
    """Configuração completa e válida em produção → nenhuma exceção."""
    _validar_config_producao(**_args_prod_ok())


# ── CWI 2.1 — redirect HTTP→HTTPS (cross-ref test_app_init.py) ───────────


def test_cwi21_https_redirect_em_producao(app, client):
    """CWI 2.1 — request HTTP em produção → 301 para HTTPS.

    Evidência primária: test_app_init.py::test_forcar_https_redireciona_em_producao.
    Este teste faz cross-ref explícito ao critério CWI 2.1 para rastreabilidade.
    """
    app.config["ENV"] = "production"
    r = client.get("/login")
    assert r.status_code == 301
    assert r.location.startswith("https://")


def test_cwi21_cookies_secure_default_em_config_producao():
    """CWI 2.1 — reload em prod: SESSION_COOKIE_SECURE e REMEMBER_COOKIE_SECURE são True por default.

    Verifica que a classe Config deriva os valores corretos do ambiente, sem setar
    manualmente. Garante que secure-by-default funciona sem SESSION_COOKIE_SECURE explícito no .env.
    """
    config_mod = sys.modules["config"]
    try:
        with patch.dict(os.environ, _PROD_ENV_VALIDO, clear=False):
            importlib.reload(config_mod)
        assert config_mod.Config.SESSION_COOKIE_SECURE is True, (
            "SESSION_COOKIE_SECURE deve ser True por default em produção"
        )
        assert config_mod.Config.REMEMBER_COOKIE_SECURE is True, (
            "REMEMBER_COOKIE_SECURE deve ser True por default em produção"
        )
    finally:
        _restaurar_config()


# ── Reload isolado — boot real simulado (L2) ──────────────────────────────


def test_import_config_producao_com_vars_validas_sobe():
    """Boot real simulado: reload config com env prod válida → sem exceção."""
    config_mod = sys.modules["config"]
    try:
        with patch.dict(os.environ, _PROD_ENV_VALIDO, clear=False):
            importlib.reload(config_mod)
        # Chegou aqui → nenhuma ValueError levantada no import
        assert config_mod.Config.ENV == "production"
        # CWI 2.1: cookies Secure default True em prod
        assert config_mod.Config.SESSION_COOKIE_SECURE is True
        assert config_mod.Config.REMEMBER_COOKIE_SECURE is True
    finally:
        _restaurar_config()


def test_import_config_producao_sem_app_base_url_falha():
    """Boot real simulado: APP_BASE_URL ausente em prod → ValueError no import."""
    config_mod = sys.modules["config"]
    env = {**_PROD_ENV_VALIDO, "APP_BASE_URL": ""}
    try:
        with (
            patch.dict(os.environ, env, clear=False),
            pytest.raises(ValueError, match="APP_BASE_URL"),
        ):
            importlib.reload(config_mod)
    finally:
        _restaurar_config()


def test_import_config_producao_sem_health_secret_falha():
    """Boot real simulado: HEALTH_SECRET ausente em prod → ValueError no import."""
    config_mod = sys.modules["config"]
    env = {**_PROD_ENV_VALIDO, "HEALTH_SECRET": ""}
    try:
        with (
            patch.dict(os.environ, env, clear=False),
            pytest.raises(ValueError, match="HEALTH_SECRET"),
        ):
            importlib.reload(config_mod)
    finally:
        _restaurar_config()


# ── _validar_fernet_key (unit tests — Onda 4 polish) ─────────────────────────


def test_fernet_prod_flag_true_sem_key_raises():
    """Prod + ENCRYPT_PII_AT_REST=true + ENCRYPTION_KEY ausente → ValueError."""
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        _validar_fernet_key(env="production", encrypt_pii=True, key="")


def test_fernet_prod_flag_true_key_invalida_raises():
    """Prod + ENCRYPT_PII_AT_REST=true + ENCRYPTION_KEY inválida → ValueError."""
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        _validar_fernet_key(env="production", encrypt_pii=True, key="chave-invalida-nao-base64")


def test_fernet_prod_flag_false_nao_raise():
    """Prod + ENCRYPT_PII_AT_REST=false → sem exceção (default seguro)."""
    _validar_fernet_key(env="production", encrypt_pii=False, key="")


def test_fernet_dev_flag_true_sem_key_emite_warning():
    """Dev + ENCRYPT_PII_AT_REST=true + key ausente → warnings.warn (não ValueError)."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        _validar_fernet_key(env="development", encrypt_pii=True, key="")
    assert any("ENCRYPTION_KEY" in str(w.message) for w in captured), (
        "Esperado warning sobre ENCRYPTION_KEY ausente em dev"
    )


def test_fernet_prod_flag_true_key_valida_nao_raise():
    """Prod + flag=true + ENCRYPTION_KEY válida → nenhuma exceção."""
    from cryptography.fernet import Fernet

    valid_key = Fernet.generate_key().decode()
    _validar_fernet_key(env="production", encrypt_pii=True, key=valid_key)


def test_fernet_reload_prod_com_flag_true_sem_key_falha():
    """Boot real simulado: prod + ENCRYPT_PII_AT_REST=true + ENCRYPTION_KEY ausente → ValueError."""
    config_mod = sys.modules["config"]
    env = {**_PROD_ENV_VALIDO, "ENCRYPT_PII_AT_REST": "true", "ENCRYPTION_KEY": ""}
    try:
        with (
            patch.dict(os.environ, env, clear=False),
            pytest.raises(ValueError, match="ENCRYPTION_KEY"),
        ):
            importlib.reload(config_mod)
    finally:
        _restaurar_config()


# ── GESTOR_EMAILS (Fase 5 — prep Fase 6) ────────────────────────────────────


def test_gestor_emails_default_dict_vazio():
    """GESTOR_EMAILS default é dict vazio quando env não definida."""
    from config import Config

    # Config carregada sem GESTOR_EMAILS → dict vazio (sem KeyError)
    assert isinstance(Config.GESTOR_EMAILS, dict)


def test_get_gestor_email_nivel_inexistente_retorna_none():
    """get_gestor_email retorna None para nivel não configurado."""
    from config import Config

    assert Config.get_gestor_email("nivel_inexistente") is None


def test_get_gestor_email_nivel_configurado():
    """get_gestor_email retorna e-mail correto para nivel configurado."""
    import json

    emails_json = json.dumps({"gestor_setor": "gs@dtx.aero", "gm": "gm@dtx.aero"})
    config_mod = sys.modules["config"]
    try:
        with patch.dict(os.environ, {"GESTOR_EMAILS": emails_json}, clear=False):
            importlib.reload(config_mod)
            from config import Config as ConfigReloaded

            assert ConfigReloaded.get_gestor_email("gestor_setor") == "gs@dtx.aero"
            assert ConfigReloaded.get_gestor_email("gm") == "gm@dtx.aero"
            assert ConfigReloaded.get_gestor_email("inexistente") is None
    finally:
        _restaurar_config()


def test_gestor_emails_json_invalido_vira_dict_vazio():
    """GESTOR_EMAILS com JSON inválido não levanta exceção — default para dict vazio."""
    config_mod = sys.modules["config"]
    try:
        with patch.dict(os.environ, {"GESTOR_EMAILS": "nao-e-json"}, clear=False):
            importlib.reload(config_mod)
            from config import Config as ConfigReloaded

            assert isinstance(ConfigReloaded.GESTOR_EMAILS, dict)
    finally:
        _restaurar_config()
