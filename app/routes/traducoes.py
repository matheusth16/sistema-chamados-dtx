"""Rotas de administração de traduções globais JSON. Apenas para admins."""
import logging
from flask import render_template, request, redirect, url_for, flash, jsonify, Response
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
                flash('Chave de tradução não informada.', 'danger')
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
                flash(f'Tradução para "{chave}" salva com sucesso.', 'success')
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                    return jsonify({'sucesso': False, 'erro': 'Erro ao escrever no arquivo.'}), 500
                flash('Erro ao salvar o arquivo json.', 'danger')
                
        except Exception as e:
            logger.exception(f"Erro ao salvar tradução: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
                return jsonify({'sucesso': False, 'erro': str(e)}), 500
            flash(f'Erro ao salvar: {str(e)}', 'danger')
            
        return redirect(url_for('main.admin_traducoes'))
        
    try:
        translations = get_translations_dict()
        return render_template('admin_traducoes.html', translations=translations)
    except Exception as e:
        logger.exception(f"Erro ao carregar traduções: {str(e)}")
        flash('Erro ao carregar lista de traduções.', 'danger')
        return redirect(url_for('main.admin'))
