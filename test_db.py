import sqlalchemy
import traceback

# USE EXATAMENTE A MESMA STRING DE CONEXÃO DO SEU main.py
DATABASE_URL = "postgresql://user:password@localhost:5432/preservacao_db?client_encoding=utf8"

print("--- INICIANDO TESTE DE CONEXÃO DIRETA ---")
print(f"Tentando conectar com a URL: {DATABASE_URL}")

try:
    # Tenta criar a 'engine' e estabelecer uma conexão
    engine = sqlalchemy.create_engine(DATABASE_URL)
    connection = engine.connect()

    print("\n✅ SUCESSO! Conexão com o banco de dados estabelecida.")

    # Opcional: Faz uma consulta simples para garantir
    result = connection.execute(sqlalchemy.text("SELECT version()"))
    for row in result:
        print(f"Versão do PostgreSQL: {row[0]}")

    connection.close()
    print("\nConexão fechada com sucesso.")

except Exception as e:
    print("\n❌ FALHA! Ocorreu um erro ao tentar conectar.")
    print("\n--- Detalhes do Erro ---")
    # Imprime o erro detalhado para análise
    traceback.print_exc()

print("\n--- FIM DO TESTE ---")