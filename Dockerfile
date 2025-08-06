# Imagem base oficial do Python 3.9, baseada em Debian 12 (Bookworm)
FROM python:3.9-slim-bookworm

# Define o ambiente como não-interativo
ENV DEBIAN_FRONTEND=noninteractive

# Adiciona o diretório de pacotes do sistema ao path do Python para o 'uno'
ENV PYTHONPATH "${PYTHONPATH}:/usr/lib/python3/dist-packages"

# Instalar as dependências do sistema, incluindo a ferramenta dos2unix
RUN apt-get update && \
    apt-get install -y \
        libreoffice \
        unoconv \
        python3-uno \
        postgresql-client \
        dos2unix \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# O resto do Dockerfile
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Converte os scripts para o formato Unix e os torna executáveis
COPY start.sh .
RUN dos2unix start.sh
RUN chmod +x start.sh

COPY wait-for-postgres.sh .
RUN dos2unix wait-for-postgres.sh
RUN chmod +x wait-for-postgres.sh

EXPOSE 8000

CMD ["./wait-for-postgres.sh", "preservacao_db", "./start.sh"]