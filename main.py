import os
import requests
import threading
import json
import time
import hashlib
import subprocess
import unicodedata
import re
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import redis

import models
import schemas
from models import Base

# 1. CONFIGURAÇÕES GLOBAIS
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("AVISO: DATABASE_URL não definida ou vazia no ambiente. Usando valor padrão.")
    DATABASE_URL = "postgresql://user:password@preservacao_db:5432/preservacao_db"

MINIO_SERVICE_API_URL = os.environ.get("MINIO_SERVICE_API_URL", "http://storage_app:3003")
REDIS_HOST = os.environ.get('REDIS_HOST', 'redis_cache')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_QUEUE_NAME = 'ingest-queue'
NORMALIZED_OUTPUT_DIR = '/app/output_normalizado'
SIP_LOCATION_INSIDE_CONTAINER = '/app/temp_ingestao_sip'
MAPOTECA_SERVICE_URL = "http://mapoteca_app:3000/internal/processing-complete"

# 2. SETUP DA API FASTAPI E BANCO DE DADOS
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
app = FastAPI(title="Microsserviço de Gestão de Dados e Processamento")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. FUNÇÕES HELPER (LÓGICA DE PROCESSAMENTO)
EXTENSION_MAP = {'.pdf': 'pdf', '.doc': 'doc', '.docx': 'docx', '.odt': 'odt', '.txt': 'txt', '.xml': 'xml', '.rtf': 'rtf', '.jpg': 'jpg', '.jpeg': 'jpg', '.png': 'png', '.gif': 'gif', '.dwg': 'dwg'}

def sanitize_title(title: str) -> str:
    cleaned_title = title.lower().replace('/', '-')
    cleaned_title = unicodedata.normalize('NFKD', cleaned_title).encode('ascii', 'ignore').decode('ascii')
    cleaned_title = re.sub(r'[\s_]+', '_', cleaned_title)
    cleaned_title = re.sub(r'[^\w-]', '', cleaned_title)
    return cleaned_title

def sanitize_filename(filename):
    return filename

def calculate_checksum(file_path):
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        print(f"ERRO ao calcular checksum: {e}")
        return None

def identify_format_by_extension(filename):
    extension = os.path.splitext(filename)[1].lower()
    return EXTENSION_MAP.get(extension, 'outro')

def normalize_to_pdfa(file_path, output_dir):
    filename = os.path.basename(file_path)
    file_base, file_ext = os.path.splitext(filename)
    
    if file_ext.lower() == '.dwg':
        print(f"        - AVISO: A conversão do formato '.dwg' não é suportada nesta versão. Pulando normalização.")
        return None

    try:
        print(f"        - Normalizando documento para PDF com unoconv...")
        output_filepath = os.path.join(output_dir, f"{file_base}.pdf")
        command = ["unoconv", "-f", "pdf", "-o", output_filepath, file_path]
        subprocess.run(command, check=True, timeout=120)
        print(f"        - SUCESSO: Documento normalizado salvo como: {output_filepath}")
        return output_filepath
    except Exception as e:
        print(f"        - ERRO ao normalizar o arquivo {filename}: {e}")
        return None

def enviar_para_storage(file_path, bucket, key_prefix):
    try:
        filename = os.path.basename(file_path)
        print(f"        -> Enviando '{filename}' para o bucket '{bucket}' com prefixo '{key_prefix}'...")
        with open(file_path, 'rb') as f:
            files_payload = {'files': (filename, f)}
            data_payload = {'bucket': bucket, 'keyPrefix': key_prefix}
            response = requests.post(f"{MINIO_SERVICE_API_URL}/storage/upload", files=files_payload, data=data_payload, timeout=30)
            response.raise_for_status()
            print(f"        -> SUCESSO: Arquivo enviado para o storage.")
            return response.json()
    except requests.exceptions.RequestException as e:
        print(f"        -> ERRO: Falha ao enviar arquivo para o storage: {e}")
        if e.response is not None:
            print(f"        -> Status da Resposta: {e.response.status_code}")
            print(f"        -> Corpo da Resposta: {e.response.text}")
        return None

def notificar_mapoteca(metadados: dict):
    try:
        print(f"    -> Notificando Mapoteca em {MAPOTECA_SERVICE_URL}...")
        response = requests.post(MAPOTECA_SERVICE_URL, json=metadados, timeout=15)
        response.raise_for_status()
        print(f"    -> SUCESSO: Mapoteca notificado!")
        return True
    except requests.exceptions.RequestException as e:
        print(f"    -> ERRO CRÍTICO: Falha ao notificar o Mapoteca: {e}")
        return False


# 4. LÓGICA DO CONSUMIDOR REDIS (BACKGROUND)
def run_redis_consumer():
    print("--- Thread do Consumidor Redis Iniciada ---")
    
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    print(f">>> Consumidor: Conectado ao Redis em {REDIS_HOST}:{REDIS_PORT}! Aguardando tarefas... <<<")

    while True:
        db = None
        try:
            item = r.brpop(REDIS_QUEUE_NAME, 0)
            data = json.loads(item[1].decode('utf-8'))
            
            transfer_id = data.get('transferId')
            ra = data.get('ra')
            pasta_id = data.get('pastaId')

            db = SessionLocal()
            
            prefixo_minio = ""
            if pasta_id:
                caminho_completo = []
                pasta_atual_id = pasta_id
                
                while pasta_atual_id:
                    pasta = db.query(models.TpPasta).filter(models.TpPasta.cod_id == pasta_atual_id).first()
                    if pasta:
                        caminho_completo.insert(0, pasta.nom_pasta)
                        pasta_atual_id = pasta.cod_pai
                    else:
                        print(f"    -> [PID: {transfer_id}] AVISO: Pasta ou um de seus pais com ID '{pasta_atual_id}' não foi encontrado.")
                        pasta_atual_id = None 
                
                if caminho_completo:
                    prefixo_minio = "/".join(caminho_completo)
                    print(f"    -> [PID: {transfer_id}] Caminho completo do MinIO construído: '{prefixo_minio}'")
            elif ra:
                prefixo_minio = ra
                print(f"    -> [PID: {transfer_id}] Usando 'ra' como pasta do MinIO: '{prefixo_minio}'")
            else:
                 print(f"    -> [PID: {transfer_id}] Nenhum 'pastaId' ou 'ra' fornecido. Salvando na raiz do bucket.")

            sip_directory = os.path.join(SIP_LOCATION_INSIDE_CONTAINER, transfer_id)
            
            print(f"\n[*] [PID: {transfer_id}] Nova tarefa recebida. RA: {ra}, PastaID: {pasta_id}")
            
            if not os.path.isdir(sip_directory):
                print(f"    -> [PID: {transfer_id}] ERRO CRÍTICO: Diretório do SIP não encontrado: {sip_directory}")
                notificar_mapoteca({"transferId": transfer_id, "status": "FAILED", "message": "Diretório de processamento não encontrado."})
                continue

            arquivos_originais_payload = []
            arquivos_preservados_payload = []
            processamento_falhou = False
            mensagem_de_falha = ""

            for original_filename in os.listdir(sip_directory):
                original_file_path = os.path.join(sip_directory, original_filename)
                if not os.path.isfile(original_file_path): continue
                
                sanitized_filename = sanitize_filename(original_filename)
                sanitized_file_path = os.path.join(sip_directory, sanitized_filename)
                
                if original_file_path != sanitized_file_path:
                    os.rename(original_file_path, sanitized_file_path)
                
                print(f"    -> [PID: {transfer_id}] Iniciando pipeline para o arquivo: '{sanitized_filename}'")
                
                print(f"        - [PID: {transfer_id}] Passo 1/4: Calculando checksum (SHA256)...")
                checksum = calculate_checksum(sanitized_file_path)
                if not checksum:
                    processamento_falhou = True
                    mensagem_de_falha = f"Falha ao calcular checksum para {sanitized_filename}"
                    print(f"        - [PID: {transfer_id}] ERRO: {mensagem_de_falha}")
                    break
                print(f"        - [PID: {transfer_id}] Checksum OK: {checksum[:10]}...")

                print(f"        - [PID: {transfer_id}] Passo 2/4: Enviando arquivo original para o storage...")
                upload_original_ok = enviar_para_storage(sanitized_file_path, 'originais', prefixo_minio)
                if not upload_original_ok:
                    processamento_falhou = True
                    mensagem_de_falha = f"Falha no upload do arquivo original {sanitized_filename}"
                    print(f"        - [PID: {transfer_id}] ERRO: {mensagem_de_falha}")
                    break
                
                caminho_minio_original = f"{prefixo_minio}/{sanitized_filename}" if prefixo_minio else sanitized_filename
                
                arquivos_originais_payload.append({
                    "nome": sanitized_filename,
                    "caminho_minio": caminho_minio_original,
                    "checksum": checksum,
                    "formato": identify_format_by_extension(sanitized_filename),
                })
                
                print(f"        - [PID: {transfer_id}] Passo 3/4: Tentando normalização para PDF...")
                normalized_file_path = normalize_to_pdfa(sanitized_file_path, NORMALIZED_OUTPUT_DIR)
                
                if normalized_file_path:
                    print(f"        - [PID: {transfer_id}] Passo 4/4: Enviando arquivo normalizado para o storage...")
                    upload_preservado_ok = enviar_para_storage(normalized_file_path, 'preservacoes', prefixo_minio)
                    if not upload_preservado_ok:
                        processamento_falhou = True
                        mensagem_de_falha = "Falha no upload do arquivo de preservação"
                        print(f"        - [PID: {transfer_id}] ERRO: {mensagem_de_falha}")
                        break
                    
                    nome_arquivo_normalizado = os.path.basename(normalized_file_path)
                    caminho_minio_preservacao = f"{prefixo_minio}/{nome_arquivo_normalizado}" if prefixo_minio else nome_arquivo_normalizado
                    
                    arquivos_preservados_payload.append({
                        "nome": nome_arquivo_normalizado,
                        "caminho_minio": caminho_minio_preservacao,
                        "checksum": calculate_checksum(normalized_file_path),
                        "formato": "pdf",
                    })
                else:
                    print(f"        - [PID: {transfer_id}] Passo 4/4: Nenhuma versão normalizada foi gerada. Pulando.")
            
            if not processamento_falhou:
                print(f"    -> [PID: {transfer_id}] Pipeline de arquivos concluída. Montando Pacote de Arquivamento (AIP)...")
                
                nome_completo_para_titulo = arquivos_originais_payload[0]['nome'] if arquivos_originais_payload else 'sem_titulo.tmp'
                titulo_final_base, _ = os.path.splitext(nome_completo_para_titulo)
                
                payload_para_gestao = {
                    "transfer_id": transfer_id,
                    "titulo": titulo_final_base,
                    "cod_pasta": pasta_id,
                    "originais": arquivos_originais_payload,
                    "preservados": arquivos_preservados_payload
                }

                print(f"    -> [PID: {transfer_id}] Registrando metadados do AIP no banco de dados...")
                url_criacao_aip = f"http://localhost:8000/aips/"
                response = requests.post(url_criacao_aip, json=payload_para_gestao)
                
                if response.status_code == 201:
                    print(f"    -> [PID: {transfer_id}] Metadados registrados com sucesso.")
                    notificar_mapoteca({"transferId": transfer_id, "status": "COMPLETED", "message": "Processamento concluído."})
                    print(f"[*] [PID: {transfer_id}] Tarefa finalizada com SUCESSO.")
                else:
                    mensagem_de_falha = f"Falha ao registrar metadados. Status: {response.status_code}, Resposta: {response.text}"
                    processamento_falhou = True

            if processamento_falhou:
                print(f"    -> [PID: {transfer_id}] ERRO: Ocorreu uma falha na pipeline.")
                notificar_mapoteca({"transferId": transfer_id, "status": "FAILED", "message": mensagem_de_falha})
                print(f"[*] [PID: {transfer_id}] Tarefa finalizada com FALHA. Motivo: {mensagem_de_falha}")

        except Exception as e:
            print(f"ERRO INESPERADO no consumidor para o PID {data.get('transferId', 'desconhecido')}: {e}")
            if 'data' in locals() and data.get('transferId'):
                notificar_mapoteca({"transferId": data.get('transferId'), "status": "FAILED", "message": f"Erro inesperado no worker: {e}"})
        
        finally:
            if db:
                db.close()
# 5. STARTUP DA APLICAÇÃO E ENDPOINTS DA API
@app.on_event("startup")
def on_startup():
    print("API Iniciando...")
    Base.metadata.create_all(bind=engine)
    print("Tabelas prontas.")
    
    redis_thread = threading.Thread(target=run_redis_consumer)
    redis_thread.daemon = True
    redis_thread.start()
    print("Thread do consumidor Redis iniciada em background.")

@app.post("/aips/", status_code=201)
def criar_registro_aip(payload: schemas.AIPCreate, db: Session = Depends(get_db)):
    try:
        db_aip = models.TpAip(
            cod_id=payload.transfer_id, 
            nom_titulo=payload.titulo,
            cod_pasta=payload.cod_pasta
        )

        for arquivo_data in payload.originais:
            db.add(models.TpArquivoOriginal(
                aip=db_aip,
                nom_arquivo=arquivo_data.nome,
                dsc_caminho_minio=arquivo_data.caminho_minio,
                num_checksum=arquivo_data.checksum,
                sig_formato=arquivo_data.formato
            ))

        for arquivo_data in payload.preservados:
            db.add(models.TpArquivoPreservacao(
                aip=db_aip,
                nom_arquivo=arquivo_data.nome,
                dsc_caminho_minio=arquivo_data.caminho_minio,
                num_checksum=arquivo_data.checksum,
                sig_formato=arquivo_data.formato
            ))
        
        db.add(db_aip)
        db.commit()
        db.refresh(db_aip)
        return {"message": "AIP registrado com sucesso!", "aip_id": db_aip.cod_id}
    except Exception as e:
        print(f"\n!!!!!!!!!! ERRO DETALHADO AO SALVAR NO BANCO !!!!!!!!!!")
        print(f"Tipo do Erro: {type(e)}")
        print(f"Argumentos do Erro: {e.args}")
        print(f"Erro Completo: {e}")
        print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno ao salvar o AIP: {e}")

@app.post("/aips/{transfer_id}/logical-delete", response_model=schemas.LogicalDeleteResponse)
def logical_delete_aip(transfer_id: str, db: Session = Depends(get_db)):
    aip = db.query(models.TpAip).filter(models.TpAip.cod_id == transfer_id, models.TpAip.dhs_deleted == None).first()
    if not aip:
        raise HTTPException(status_code=404, detail="AIP não encontrado ou já marcado para deleção.")
    
    files_to_delete = [{"bucket": "originais", "path": arq.dsc_caminho_minio} for arq in aip.arquivos_originais] + \
                      [{"bucket": "preservacoes", "path": arq.dsc_caminho_minio} for arq in aip.arquivos_preservacao]
    
    aip.dhs_deleted = datetime.utcnow()
    db.commit()
    return {"message": "Item marcado para deleção com sucesso.", "filesToDelete": files_to_delete}

@app.get("/aips/{transfer_id}/location", response_model=schemas.LocationResponse)
def get_item_location(transfer_id: str, db: Session = Depends(get_db)):
    aip = db.query(models.TpAip).filter(models.TpAip.cod_id == transfer_id, models.TpAip.dhs_deleted == None).first()
    if not aip: raise HTTPException(status_code=404, detail="AIP não encontrado.")
    
    arquivo_para_baixar = db.query(models.TpArquivoPreservacao).filter(models.TpArquivoPreservacao.cod_aip == aip.cod_id).first()
    bucket_name = "preservacoes"
    if not arquivo_para_baixar:
        arquivo_para_baixar = db.query(models.TpArquivoOriginal).filter(models.TpArquivoOriginal.cod_aip == aip.cod_id).first()
        bucket_name = "originais"
    if not arquivo_para_baixar:
        raise HTTPException(status_code=404, detail="Nenhum arquivo associado a este AIP foi encontrado")
        
    _, file_extension = os.path.splitext(arquivo_para_baixar.nom_arquivo)
    base_name_from_title, _ = os.path.splitext(aip.nom_titulo)
    sanitized_base_name = sanitize_title(base_name_from_title)
    download_filename = f"{sanitized_base_name}{file_extension}"
    
    return schemas.LocationResponse(bucket=bucket_name, path=arquivo_para_baixar.dsc_caminho_minio, filename=download_filename)

@app.put("/aips/{transfer_id}/rename", status_code=200)
def rename_aip(transfer_id: str, payload: schemas.RenamePayload, db: Session = Depends(get_db)):
    aip = db.query(models.TpAip).filter(models.TpAip.cod_id == transfer_id, models.TpAip.dhs_deleted == None).first()
    if not aip:
        raise HTTPException(status_code=404, detail="AIP não encontrado.")
    
    sanitized_title = sanitize_title(payload.novo_titulo)
    aip.nom_titulo = sanitized_title
    db.commit()
    db.refresh(aip)
    return {"message": "Item renomeado com sucesso.", "novo_titulo": aip.nom_titulo}

@app.get("/aips/{transfer_id}/details", response_model=schemas.AipDetailsResponse)
def get_aip_details(transfer_id: str, db: Session = Depends(get_db)):
    aip = db.query(models.TpAip).filter(models.TpAip.cod_id == transfer_id, models.TpAip.dhs_deleted == None).first()
    if not aip:
        raise HTTPException(status_code=404, detail="AIP não encontrado.")
    
    lista_arquivos_detalhados = []
    todos_arquivos = [("original", arq) for arq in aip.arquivos_originais] + [("preservacao", arq) for arq in aip.arquivos_preservacao]
    
    for tipo, arquivo_db in todos_arquivos:
        try:
            bucket = "originais" if tipo == "original" else "preservacoes"
            metadata_url = f"{MINIO_SERVICE_API_URL}/storage/metadata"
            payload = {"bucket": bucket, "path": arquivo_db.dsc_caminho_minio}
            response = requests.post(metadata_url, json=payload, timeout=10)
            response.raise_for_status()
            metadata_storage = response.json()
            lista_arquivos_detalhados.append({
                "id": arquivo_db.cod_original if tipo == "original" else arquivo_db.cod_preservacao,
                "nome": arquivo_db.nom_arquivo,
                "formato": arquivo_db.sig_formato,
                "tipo": tipo,
                "tamanho_bytes": metadata_storage.get("size", 0),
                "ultima_modificacao": metadata_storage.get("lastModified")
            })
        except requests.exceptions.RequestException as e:
            print(f"ERRO ao buscar metadados do storage: {e}")
            lista_arquivos_detalhados.append({
                "id": arquivo_db.cod_original if tipo == "original" else arquivo_db.cod_preservacao,
                "nome": arquivo_db.nom_arquivo,
                "formato": arquivo_db.sig_formato,
                "tipo": tipo,
                "tamanho_bytes": 0,
                "ultima_modificacao": datetime.utcnow().isoformat()
            })
            
    return {
        "transfer_id": aip.cod_id,
        "titulo": aip.nom_titulo,
        "cod_pasta": aip.cod_pasta, 
        "data_criacao": aip.dhs_creation,
        "arquivos": lista_arquivos_detalhados
    }

@app.get("/aips", response_model=List[schemas.AipDetailsResponse])
def get_all_aips(db: Session = Depends(get_db)):
    aips = db.query(models.TpAip).filter(models.TpAip.dhs_deleted == None).all()
    lista_de_aips_detalhados = []
    for aip in aips:
        detalhes_aip = get_aip_details(aip.cod_id, db)
        lista_de_aips_detalhados.append(detalhes_aip)
    return lista_de_aips_detalhados

@app.post("/pastas/", response_model=schemas.Pasta, status_code=201)
def criar_pasta(pasta: schemas.PastaCreate, db: Session = Depends(get_db)):

    db_pasta_existente = db.query(models.TpPasta).filter(
        models.TpPasta.nom_pasta == pasta.nom_pasta,
        models.TpPasta.cod_pai == pasta.cod_pai
    ).first()

    if db_pasta_existente:
        raise HTTPException(status_code=409, detail="Uma pasta com este nome já existe neste local.")
    
    db_pasta = models.TpPasta(nom_pasta=pasta.nom_pasta, cod_pai=pasta.cod_pai)
    db.add(db_pasta)
    db.commit()
    db.refresh(db_pasta)
    return db_pasta

@app.get("/pastas/", response_model=List[schemas.Pasta])
def listar_pastas(db: Session = Depends(get_db)):
    pastas = db.query(models.TpPasta).all()
    return pastas

@app.get("/pastas/{pasta_id}", response_model=schemas.PastaDetails)
def listar_conteudo_da_pasta(pasta_id: str, db: Session = Depends(get_db)):
    pasta = db.query(models.TpPasta).filter(models.TpPasta.cod_id == pasta_id).first()
    
    if not pasta:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")
    
    return pasta

@app.delete("/pastas/{pasta_id}", status_code=200)
def deletar_pasta_e_conteudo(pasta_id: str, db: Session = Depends(get_db)):
    pasta_principal = db.query(models.TpPasta).filter(models.TpPasta.cod_id == pasta_id).first()
    if not pasta_principal:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    pastas_para_deletar_ids = {pasta_id}
    pastas_a_verificar = [pasta_id]

    while pastas_a_verificar:
        id_pai_atual = pastas_a_verificar.pop(0)
        filhas = db.query(models.TpPasta).filter(models.TpPasta.cod_pai == id_pai_atual).all()
        for filha in filhas:
            pastas_para_deletar_ids.add(filha.cod_id)
            pastas_a_verificar.append(filha.cod_id)

    aips_para_deletar = db.query(models.TpAip).filter(models.TpAip.cod_pasta.in_(pastas_para_deletar_ids)).all()
    
    arquivos_no_minio_para_deletar = []
    for aip in aips_para_deletar:
        aip.dhs_deleted = datetime.utcnow()
        for arq in aip.arquivos_originais:
            arquivos_no_minio_para_deletar.append({"bucket": "originais", "path": arq.dsc_caminho_minio})
        for arq in aip.arquivos_preservacao:
            arquivos_no_minio_para_deletar.append({"bucket": "preservacoes", "path": arq.dsc_caminho_minio})

    db.query(models.TpPasta).filter(models.TpPasta.cod_id.in_(pastas_para_deletar_ids)).delete(synchronize_session=False)

    db.commit()

    return {
        "message": f"Pasta e todo o seu conteúdo marcados para deleção. {len(arquivos_no_minio_para_deletar)} arquivos a serem removidos do storage.",
        "filesToDelete": arquivos_no_minio_para_deletar
    }

def get_caminho_completo(pasta_id: str, db: Session):
    caminho = []
    pasta_atual_id = pasta_id
    while pasta_atual_id:
        p = db.query(models.TpPasta).filter(models.TpPasta.cod_id == pasta_atual_id).first()
        if p:
            caminho.insert(0, p.nom_pasta)
            pasta_atual_id = p.cod_pai
        else:
            break
    return "/".join(caminho)

@app.put("/pastas/{pasta_id}", status_code=200)
def renomear_pasta(pasta_id: str, payload: schemas.PastaUpdate, db: Session = Depends(get_db)):
    pasta_para_renomear = db.query(models.TpPasta).filter(models.TpPasta.cod_id == pasta_id).first()
    if not pasta_para_renomear:
        raise HTTPException(status_code=404, detail="Pasta não encontrada.")

    pasta_existente = db.query(models.TpPasta).filter(
        models.TpPasta.nom_pasta == payload.nom_pasta,
        models.TpPasta.cod_pai == pasta_para_renomear.cod_pai
    ).first()
    if pasta_existente:
        raise HTTPException(status_code=409, detail="Uma pasta com este nome já existe neste local.")

    nome_antigo = pasta_para_renomear.nom_pasta
    caminho_pai = get_caminho_completo(pasta_para_renomear.cod_pai, db) if pasta_para_renomear.cod_pai else ""
    
    prefixo_antigo = f"{caminho_pai}/{nome_antigo}" if caminho_pai else nome_antigo
    prefixo_novo = f"{caminho_pai}/{payload.nom_pasta}" if caminho_pai else payload.nom_pasta
    

    aips_afetados = db.query(models.TpAip).filter(models.TpAip.cod_pasta == pasta_id).all()
    
    operacoes_de_movimentacao = []
    
    for aip in aips_afetados:
        for arq in aip.arquivos_originais:
            caminho_antigo = arq.dsc_caminho_minio
            caminho_novo = caminho_antigo.replace(prefixo_antigo, prefixo_novo, 1)
            operacoes_de_movimentacao.append({"bucket": "originais", "source": caminho_antigo, "destination": caminho_novo})
            arq.dsc_caminho_minio = caminho_novo
        for arq in aip.arquivos_preservacao:
            caminho_antigo = arq.dsc_caminho_minio
            caminho_novo = caminho_antigo.replace(prefixo_antigo, prefixo_novo, 1)
            operacoes_de_movimentacao.append({"bucket": "preservacoes", "source": caminho_antigo, "destination": caminho_novo})
            arq.dsc_caminho_minio = caminho_novo

    pasta_para_renomear.nom_pasta = payload.nom_pasta
    
    db.commit()

    return {
        "message": "Pasta renomeada no banco de dados. Execute as seguintes movimentações no storage.",
        "moveOperations": operacoes_de_movimentacao
    }