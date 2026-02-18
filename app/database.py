import firebase_admin
from firebase_admin import credentials, firestore
import os

# Inicializa Firebase com autenticação automática
# No Cloud Run, usa Google Cloud Application Default Credentials
# Em desenvolvimento local, pode usar credentials.json se existir
try:
    firebase_admin.get_app()
except ValueError:
    cert_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials.json')
    
    # Tenta usar credentials.json se existir (desenvolvimento local)
    if os.path.exists(cert_path):
        cred = credentials.Certificate(cert_path)
        firebase_admin.initialize_app(cred)
    else:
        # Usa autenticação automática do Google Cloud (Cloud Run, Cloud Functions, etc)
        firebase_admin.initialize_app()

# Obtém o cliente Firestore
db = firestore.client()