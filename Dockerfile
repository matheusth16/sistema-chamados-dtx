FROM python:3.11-slim

WORKDIR /app

# Instalar dependências de sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Variáveis de ambiente
ENV FLASK_APP=run.py
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Comando para iniciar a aplicação
CMD exec gunicorn --bind 0.0.0.0:${PORT} --workers 4 --threads 2 --worker-class gthread --worker-tmp-dir /dev/shm --timeout 120 run:app
