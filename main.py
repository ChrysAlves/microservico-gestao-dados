import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import models
import schemas
from models import Base

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://user:admin123@localhost:5432/preservacao_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
app = FastAPI(title="Microsserviço de Gestão de Dados")

@app.on_event("startup")
def on_startup():
    print("Verificando e criando tabelas do banco de dados, se necessario...") # sem ç
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
        return {"message": "AIP registrado com sucesso!", "aip_id": db_aip.id} # sem ç e ã
    except Exception as e:
        db.rollback()
        print(f"ERRO ao salvar AIP: {e}")

        raise HTTPException(status_code=500, detail="Erro interno ao salvar o AIP.")
    

@app.get("/aips/{transfer_id}/location", response_model=schemas.LocationResponse)
def get_item_location(transfer_id: str, db: Session = Depends(get_db)):
    """
    Retorna a localização de um arquivo para download.
    Prioriza o arquivo de preservação. Se não existir, retorna o original.
    """
    print(f"Buscando localização para o AIP com Transfer ID: {transfer_id}")

    MINIO_BUCKET = os.environ.get("MINIO_BUCKET_NAME", "preservacao") 
    if not MINIO_BUCKET:
        raise HTTPException(status_code=500, detail="Nome do bucket MinIO não configurado no servidor.")

    aip = db.query(models.AIP).filter(models.AIP.transfer_id == transfer_id).first()
    if not aip:
        print(f"AIP com Transfer ID {transfer_id} não encontrado.")
        raise HTTPException(status_code=404, detail="AIP não encontrado")

    arquivo_para_baixar = db.query(models.ArquivoPreservacao).filter(models.ArquivoPreservacao.aip_id == aip.id).first()
    
    if not arquivo_para_baixar:
        print(f"Nenhum arquivo de preservação encontrado para o AIP {aip.id}. Buscando arquivo original.")
        arquivo_para_baixar = db.query(models.ArquivoOriginal).filter(models.ArquivoOriginal.aip_id == aip.id).first()

    if not arquivo_para_baixar:
        print(f"Nenhum arquivo (preservação ou original) encontrado para o AIP {aip.id}.")
        raise HTTPException(status_code=404, detail="Nenhum arquivo associado a este AIP foi encontrado")
    
    print(f"Arquivo selecionado para download: {arquivo_para_baixar.nome}")

    return schemas.LocationResponse(
        bucket=MINIO_BUCKET,
        path=arquivo_para_baixar.caminho_minio,
        filename=arquivo_para_baixar.nome
    )