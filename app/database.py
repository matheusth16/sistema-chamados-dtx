import firebase_admin
from firebase_admin import credentials, firestore
import os

# Carrega as credenciais do Firebase
# __file__ = app/database.py
# dirname uma vez = app/
# dirname duas vezes = raiz do projeto (sistema_chamados/)
cert_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials.json')
cred = credentials.Certificate(cert_path)

# Inicializa Firebase (se ainda não foi inicializado)
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

# Obtém o cliente Firestore
db = firestore.client()