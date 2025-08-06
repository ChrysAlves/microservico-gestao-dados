

echo "Iniciando listener do unoconv em segundo plano..."
unoconv --listener &

sleep 5

echo "Iniciando servidor da API FastAPI e consumidor Redis..."
uvicorn main:app --host 0.0.0.0 --port 8000