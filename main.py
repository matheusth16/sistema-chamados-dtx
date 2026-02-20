"""
Ponto de entrada para Google Cloud Run / Buildpacks.

O buildpack do Google Cloud procura main.py ou app.py para detectar e iniciar
a aplicação Python. Este arquivo expõe o app Flask para o comando padrão:
  gunicorn -b :$PORT main:app
"""
from run import app
