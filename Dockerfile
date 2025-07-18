# Dockerfile para o Microsserviço de Gestão de Dados

FROM python:3.9-slim-bullseye

WORKDIR /app

# Instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Expõe a porta que a API irá usar e define o comando para iniciar o servidor
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]