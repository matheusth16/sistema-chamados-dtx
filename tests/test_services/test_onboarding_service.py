"""Testes unitários do serviço de onboarding."""

from unittest.mock import patch


def test_avancar_passo_sucesso_retorna_true():
    """avancar_passo chama Firestore e retorna True."""
    from app.services.onboarding_service import avancar_passo

    with patch("app.services.onboarding_service.db") as mock_db:
        result = avancar_passo("u1", 3)

    assert result is True
    mock_db.collection.return_value.document.return_value.update.assert_called_once_with(
        {"onboarding_passo": 3}
    )


def test_avancar_passo_excecao_retorna_false():
    """avancar_passo retorna False quando Firestore lança exceção."""
    from app.services.onboarding_service import avancar_passo

    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.side_effect = Exception("err")
        result = avancar_passo("u1", 2)

    assert result is False


def test_concluir_onboarding_sucesso_retorna_true():
    """concluir_onboarding chama Firestore com onboarding_completo=True e retorna True."""
    from app.services.onboarding_service import concluir_onboarding

    with patch("app.services.onboarding_service.db") as mock_db:
        result = concluir_onboarding("u1")

    assert result is True
    call_kwargs = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert call_kwargs["onboarding_completo"] is True
    assert call_kwargs["onboarding_passo"] == 0


def test_concluir_onboarding_excecao_retorna_false():
    """concluir_onboarding retorna False quando Firestore lança exceção."""
    from app.services.onboarding_service import concluir_onboarding

    with patch("app.services.onboarding_service.db") as mock_db:
        mock_db.collection.return_value.document.return_value.update.side_effect = Exception("err")
        result = concluir_onboarding("u1")

    assert result is False
