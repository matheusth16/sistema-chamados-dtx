"""Testes do serviço de criação de chamados (criar_chamado)."""

from unittest.mock import patch, MagicMock, call

from app.services.chamados_criacao_service import criar_chamado


def test_criar_chamado_com_dados_validos_retorna_id_e_numero(app):
    """criar_chamado com form válido e mocks retorna (chamado_id, numero_chamado, None, aviso)."""
    form = {
        'categoria': 'Manutencao',
        'tipo': 'Manutencao',
        'descricao': 'Descrição com mais de 3 caracteres para passar na validação.',
        'rl_codigo': '',
        'impacto': '',
        'gate': '',
    }
    files = MagicMock()
    files.get.return_value = None

    with patch('app.services.chamados_criacao_service.salvar_anexo', return_value=None):
        with patch('app.services.chamados_criacao_service.gerar_numero_chamado', return_value='2026-099'):
            with patch('app.services.chamados_criacao_service.atribuidor') as mock_atr:
                mock_atr.atribuir.return_value = {
                    'sucesso': True,
                    'supervisor': {'id': 'sup1', 'nome': 'Supervisor Teste'},
                    'motivo': '',
                }
                with patch('app.services.chamados_criacao_service.execute_with_retry') as mock_retry:
                    mock_ref = MagicMock()
                    mock_ref.id = 'chamado_id_123'
                    mock_retry.return_value = (None, mock_ref)
                    with patch('app.services.chamados_criacao_service.Historico') as mock_hist:
                        # threading.Thread mockado para não disparar thread real no teste
                        with patch('app.services.chamados_criacao_service.threading.Thread') as mock_thread:
                            with app.app_context():
                                chamado_id, numero, erro, aviso = criar_chamado(
                                    form=form,
                                    files=files,
                                    solicitante_id='sol1',
                                    solicitante_nome='Solicitante Teste',
                                    area_solicitante='Manutencao',
                                    solicitante_email='sol@test.com',
                                )

    assert chamado_id == 'chamado_id_123'
    assert numero == '2026-099'
    assert erro is None
    mock_retry.assert_called_once()
    mock_hist.return_value.save.assert_called_once()
    mock_thread.return_value.start.assert_called_once()  # thread de notificação disparada


def test_criar_chamado_anexo_invalido_retorna_erro():
    """criar_chamado quando salvar_anexo levanta ValueError retorna (None, None, mensagem, None)."""
    form = {
        'categoria': 'Manutencao',
        'tipo': 'Manutencao',
        'descricao': 'Descrição válida.',
        'rl_codigo': '',
        'impacto': '',
        'gate': '',
    }
    files = MagicMock()
    files.get.return_value = MagicMock()

    with patch('app.services.chamados_criacao_service.salvar_anexo', side_effect=ValueError('Extensão não permitida')):
        chamado_id, numero, erro, aviso = criar_chamado(
            form=form,
            files=files,
            solicitante_id='sol1',
            solicitante_nome='Solicitante',
            area_solicitante='Manutencao',
        )

    assert chamado_id is None
    assert numero is None
    assert erro == 'Extensão não permitida'
    assert aviso is None
