"""Testes para app/database.py — inicialização Firebase com retry e branches de credenciais.

Estratégia:
- Função `_inicializar_firebase_com_retry` é testada diretamente via patch de firebase_admin.
- Linhas module-level (137-142 e 148-150) exigem importlib.reload com mocks totais;
  o módulo é restaurado após cada teste via _restaurar_database().
"""

import importlib
import json
from unittest.mock import MagicMock, patch

import pytest


def _restaurar_database():
    """Recarrega app.database com mocks válidos para restaurar estado após teste de reload."""
    import app.database as db_mod

    mock_cred = MagicMock()
    mock_cred.project_id = "proj-restore"

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app"),
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred),
        patch("firebase_admin.firestore.client", return_value=MagicMock()),
        patch("os.path.exists", return_value=False),
        patch("os.getenv", return_value=""),
        patch("time.sleep"),
    ):
        importlib.reload(db_mod)


# ── Testes diretos de _inicializar_firebase_com_retry ──────────────────────


def test_firebase_ja_inicializado_retorna_sem_chamar_init():
    """get_app() não levanta → Firebase já inicializado → return sem chamar initialize_app."""
    from app.database import _inicializar_firebase_com_retry

    with (
        patch("firebase_admin.get_app", return_value=MagicMock()),
        patch("firebase_admin.initialize_app") as mock_init,
    ):
        _inicializar_firebase_com_retry()
        mock_init.assert_not_called()


def test_inicializar_com_google_credentials_json_sem_bucket():
    """GOOGLE_CREDENTIALS_JSON definida, sem FIREBASE_STORAGE_BUCKET → usa project_id como bucket."""
    from app.database import _inicializar_firebase_com_retry

    cred_json = json.dumps({"type": "service_account", "project_id": "meu-projeto"})
    mock_cred = MagicMock()
    mock_cred.project_id = "meu-projeto"

    def fake_getenv(k, default=""):
        return {"GOOGLE_CREDENTIALS_JSON": cred_json, "FIREBASE_STORAGE_BUCKET": ""}.get(k, default)

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred),
        patch("os.getenv", side_effect=fake_getenv),
    ):
        _inicializar_firebase_com_retry()
        mock_init.assert_called_once()
        bucket = mock_init.call_args[0][1]["storageBucket"]
        assert bucket == "meu-projeto.firebasestorage.app"


def test_inicializar_com_google_credentials_json_com_bucket_env():
    """GOOGLE_CREDENTIALS_JSON + FIREBASE_STORAGE_BUCKET → usa o bucket definido."""
    from app.database import _inicializar_firebase_com_retry

    cred_json = json.dumps({"type": "service_account", "project_id": "meu-projeto"})
    mock_cred = MagicMock()
    mock_cred.project_id = "meu-projeto"

    def fake_getenv(k, default=""):
        return {
            "GOOGLE_CREDENTIALS_JSON": cred_json,
            "FIREBASE_STORAGE_BUCKET": "bucket-custom",
        }.get(k, default)

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred),
        patch("os.getenv", side_effect=fake_getenv),
    ):
        _inicializar_firebase_com_retry()
        bucket = mock_init.call_args[0][1]["storageBucket"]
        assert bucket == "bucket-custom"


def test_inicializar_com_arquivo_local():
    """Sem env var, credentials.json existe → Certificate(path) + initialize_app."""
    from app.database import _inicializar_firebase_com_retry

    mock_cred = MagicMock()
    mock_cred.project_id = "projeto-local"

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred) as mock_cert,
        patch("os.getenv", return_value=""),
        patch("os.path.exists", return_value=True),
    ):
        _inicializar_firebase_com_retry()
        mock_cert.assert_called_once()
        mock_init.assert_called_once()


def test_inicializar_adc_com_bucket_env_sem_projeto():
    """ADC, FIREBASE_STORAGE_BUCKET definido → initialize_app(options={'storageBucket': bucket})."""
    from app.database import _inicializar_firebase_com_retry

    def fake_getenv(k, default=""):
        return {
            "GOOGLE_CREDENTIALS_JSON": "",
            "FIREBASE_STORAGE_BUCKET": "bucket-do-env",
            "GOOGLE_CLOUD_PROJECT": "",
        }.get(k, default)

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("os.path.exists", return_value=False),
        patch("os.getenv", side_effect=fake_getenv),
    ):
        _inicializar_firebase_com_retry()
        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["options"]["storageBucket"] == "bucket-do-env"


def test_inicializar_adc_com_projeto_sem_bucket():
    """ADC, GOOGLE_CLOUD_PROJECT definido, sem bucket → usa project.firebasestorage.app."""
    from app.database import _inicializar_firebase_com_retry

    def fake_getenv(k, default=""):
        return {
            "GOOGLE_CREDENTIALS_JSON": "",
            "FIREBASE_STORAGE_BUCKET": "",
            "GOOGLE_CLOUD_PROJECT": "meu-gcp-project",
        }.get(k, default)

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("os.path.exists", return_value=False),
        patch("os.getenv", side_effect=fake_getenv),
    ):
        _inicializar_firebase_com_retry()
        mock_init.assert_called_once()
        bucket = mock_init.call_args.kwargs["options"]["storageBucket"]
        assert "meu-gcp-project" in bucket


def test_inicializar_adc_sem_projeto_sem_bucket():
    """ADC, sem GOOGLE_CLOUD_PROJECT e sem bucket → initialize_app() sem opções + warning."""
    from app.database import _inicializar_firebase_com_retry

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app") as mock_init,
        patch("os.path.exists", return_value=False),
        patch("os.getenv", return_value=""),
    ):
        _inicializar_firebase_com_retry()
        mock_init.assert_called_once_with()


def test_retry_sucesso_na_terceira_tentativa():
    """2 falhas → sleep(1s) → sleep(2s) → 3ª tentativa OK → retorna sem raise."""
    from app.database import _inicializar_firebase_com_retry

    mock_cred = MagicMock()
    mock_cred.project_id = "proj"

    init_mock = MagicMock(side_effect=[Exception("falha 1"), Exception("falha 2"), None])

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app", init_mock),
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred),
        patch("os.getenv", return_value=""),
        patch("os.path.exists", return_value=True),
        patch("time.sleep") as mock_sleep,
    ):
        _inicializar_firebase_com_retry(max_tentativas=3, delay_inicial=1.0)

    assert init_mock.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0)
    mock_sleep.assert_any_call(2.0)


def test_retry_esgota_todas_tentativas_levanta_excecao():
    """Todas as tentativas falham → raise da última exceção."""
    from app.database import _inicializar_firebase_com_retry

    mock_cred = MagicMock()
    mock_cred.project_id = "proj"

    with (
        patch("firebase_admin.get_app", side_effect=ValueError),
        patch("firebase_admin.initialize_app", side_effect=RuntimeError("persistente")),
        patch("firebase_admin.credentials.Certificate", return_value=mock_cred),
        patch("os.getenv", return_value=""),
        patch("os.path.exists", return_value=True),
        patch("time.sleep"),
        pytest.raises(RuntimeError, match="persistente"),
    ):
        _inicializar_firebase_com_retry(max_tentativas=3, delay_inicial=0.01)


# ── Testes das linhas module-level via reload isolado ───────────────────────


def test_modulo_inicializacao_critica_levanta():
    """_inicializar_firebase_com_retry falha no nível do módulo → logger.critical + raise."""
    import app.database as db_mod

    try:
        with (
            patch("firebase_admin.get_app", side_effect=ValueError),
            patch("firebase_admin.initialize_app", side_effect=RuntimeError("cred inválida")),
            patch("firebase_admin.credentials.Certificate", return_value=MagicMock()),
            patch("firebase_admin.firestore.client", return_value=MagicMock()),
            patch("os.path.exists", return_value=False),
            patch("os.getenv", return_value=""),
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="cred inválida"),
        ):
            importlib.reload(db_mod)
    finally:
        _restaurar_database()


def test_firestore_client_falha_levanta():
    """Firebase init OK mas firestore.client() falha → logger.critical + raise."""
    import app.database as db_mod

    try:
        with (
            patch("firebase_admin.get_app", side_effect=ValueError),
            patch("firebase_admin.initialize_app"),
            patch("firebase_admin.credentials.Certificate", return_value=MagicMock()),
            patch("firebase_admin.firestore.client", side_effect=RuntimeError("firestore down")),
            patch("os.path.exists", return_value=False),
            patch("os.getenv", return_value=""),
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="firestore down"),
        ):
            importlib.reload(db_mod)
    finally:
        _restaurar_database()
