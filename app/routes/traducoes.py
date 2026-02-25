"""Rotas de administração de traduções globais JSON. Apenas para admins."""
import logging
from flask import render_template, request, redirect, url_for, flash, jsonify, Response
from app.i18n import flash_t
from app.routes import main
from app.limiter import limiter
from app.decoradores import requer_perfil

logger = logging.getLogger(__name__)


@main.route('/admin/traducoes', methods=['GET', 'POST'])
@requer_perfil('admin')
@limiter.limit("30 per minute")
def admin_traducoes() -> Response:
    """GET: Lista e gerencia todas as traduções globais JSON. POST: Salva edição de tradução"""
    from app.i18n import get_translations_dict, save_translations_dict
    
    if request.method == 'POST':
        # Suportar tanto form normal quanto x-www-form-urlencoded via fetch API (para edição inline)
        try:
            chave = request.form.get('chave')
            pt_br = request.form.get('pt_BR')
            en = request.form.get('en')
            es = request.form.get('es')
            
            if not chave:
                flash_t('trans_key_not_provided', 'danger')
                return redirect(url_for('main.admin_traducoes'))
                
            translations = get_translations_dict()
            
            if chave not in translations:
                translations[chave] = {}
                
            translations[chave]['pt_BR'] = pt_br or chave
            translations[chave]['en'] = en or chave
            translations[chave]['es'] = es or chave
            
            if save_translations_dict(translations):
                # Se for requisição AJAX/Fetch
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                    return jsonify({'sucesso': True, 'mensagem': f'Tradução "{chave}" salva.'})
                flash_t('translation_saved_success', 'success', chave=chave)
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao escrever no arquivo.'}), 500
                flash_t('error_saving_json', 'danger')
                
        except Exception as e:
            logger.exception(f"Erro ao salvar tradução: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'sucesso': False, 'erro': str(e)}), 500
            flash_t('error_saving_with_msg', 'danger', error=str(e))
            
        return redirect(url_for('main.admin_traducoes'))
        
    try:
        translations = get_translations_dict()
        return render_template('admin_traducoes.html', translations=translations)
    except Exception as e:
        logger.exception(f"Erro ao carregar traduções: {str(e)}")
        flash_t('error_loading_translations', 'danger')
        return redirect(url_for('main.admin'))
