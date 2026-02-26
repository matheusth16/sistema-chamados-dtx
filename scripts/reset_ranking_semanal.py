import os
import sys
import logging
from termcolor import colored

# Adicionar a raiz do projeto ao sys.path para importações absolutas
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database import db
from app.models_usuario import Usuario
from config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def resetar_ranking_semanal():
    """
    Zera o exp_semanal de todos os usuários.
    Deve ser executado via cron/scheduler toda segunda-feira de madrugada.
    """
    print(colored("Iniciando reset do Ranking Semanal (Gamificação)...", "cyan"))
    
    try:
        # Busca todos os usuários
        usuarios_ref = db.collection('usuarios')
        docs = usuarios_ref.stream()
        
        batch = db.batch()
        usuarios_atualizados = 0
        batch_count = 0
        
        for doc in docs:
            user_data = doc.to_dict()
            gamification = user_data.get('gamification', {})
            
            # Se o usuário não tem exp_semanal ou já é 0, ignora para economizar writes no Firestore
            if gamification.get('exp_semanal', 0) > 0:
                user_ref = usuarios_ref.document(doc.id)
                # Atualiza apenas o campo exp_semanal dentro do mapa gamification
                batch.update(user_ref, {'gamification.exp_semanal': 0})
                
                usuarios_atualizados += 1
                batch_count += 1
                
                # Firestore permite até 500 operações por batch
                if batch_count >= 500:
                    batch.commit()
                    print(colored(f"Batch comitado: {batch_count} usuários (Total até agora: {usuarios_atualizados})", "yellow"))
                    batch = db.batch()
                    batch_count = 0
                    
        # Commita qualquer restante
        if batch_count > 0:
            batch.commit()
            print(colored(f"Último batch comitado: {batch_count} usuários.", "yellow"))
            
        print(colored(f"Sucesso! {usuarios_atualizados} usuários tiveram o EXP Semanal resetado.", "green"))
        return True

    except Exception as e:
        logger.exception("Falha ao resetar o ranking semanal:")
        print(colored(f"Erro: {str(e)}", "red"))
        return False


if __name__ == '__main__':
    from app import criar_app
    app = criar_app()
    with app.app_context():
        # Confirmação antes de rodar manualmente (em produção o cron ignora isso caso não tenha pseudo-tty, 
        # mas por segurança é bom)
        if '--force' not in sys.argv:
            resp = input(colored("Tem certeza que deseja ZERAR o ranking semanal de todos os usuários? (s/N): ", "yellow"))
            if resp.lower() not in ['s', 'sim', 'y', 'yes']:
                print(colored("Operação cancelada.", "red"))
                sys.exit(0)
                
        resetar_ranking_semanal()
