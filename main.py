import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import models
import schemas
from models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:password@preservacao_db:5432/preservacao_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
app = FastAPI(title="Microsserviço de Gestão de Dados")

@app.on_event("startup")
def on_startup():
    print("Verificando e criando tabelas do banco de dados, se necessário...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas prontas.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/aips/", status_code=201)
def criar_registro_aip(payload: schemas.AIPCreate, db: Session = Depends(get_db)):
    print(f"--- AIP Recebido para Registro (Transfer ID: {payload.transfer_id}) ---")
    
    db_aip = models.AIP(transfer_id=payload.transfer_id)
    
    # Itera sobre a lista de arquivos originais
    for arquivo_data in payload.originais:
        db_arquivo_original = models.ArquivoOriginal(
            aip=db_aip, **arquivo_data.model_dump()
        )
        db.add(db_arquivo_original)

    # Itera sobre a lista de arquivos de preservação
    for arquivo_data in payload.preservados:
        db_arquivo_preservacao = models.ArquivoPreservacao(
            aip=db_aip, **arquivo_data.model_dump()
        )
        db.add(db_arquivo_preservacao)

    try:
        db.add(db_aip)
        db.commit()
        db.refresh(db_aip)
        print(f"--- AIP salvo com sucesso! ID: {db_aip.id} ---")
        return {"message": "AIP registrado com sucesso!", "aip_id": db_aip.id}
    except Exception as e:
        db.rollback()
        print(f"ERRO ao salvar AIP: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar o AIP.")