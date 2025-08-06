from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ArquivoBase(BaseModel):
    nome: str
    caminho_minio: str
    checksum: str
    formato: str

class RenamePayload(BaseModel):
    novo_titulo: str

class ArquivoOriginalCreate(ArquivoBase):
    pass

class ArquivoPreservacaoCreate(ArquivoBase):
    pass

class AIPCreate(BaseModel):
    transfer_id: str
    titulo: str
    cod_pasta: Optional[str] = None 
    originais: List[ArquivoOriginalCreate]
    preservados: List[ArquivoPreservacaoCreate] = [] 

class LocationResponse(BaseModel):
    bucket: str
    path: str
    filename: str

class FileToDelete(BaseModel):
    bucket: str
    path: str

class LogicalDeleteResponse(BaseModel):
    message: str
    filesToDelete: List[FileToDelete]

class FileDetails(BaseModel):
    id: int
    nome: str
    formato: str
    tipo: str  
    tamanho_bytes: int
    ultima_modificacao: datetime

class AipDetailsResponse(BaseModel):
    transfer_id: str
    titulo: Optional[str] = None
    data_criacao: datetime
    cod_pasta: Optional[str] = None 
    arquivos: List[FileDetails]
    
class PastaBase(BaseModel):
    nom_pasta: str

class PastaCreate(PastaBase):
    cod_pai: Optional[str] = None 

class Pasta(PastaBase):
    cod_id: str
    cod_pai: Optional[str] = None 

    class Config:
        from_attributes = True

class AipInFolder(BaseModel):
    cod_id: str
    nom_titulo: str
    dhs_creation: datetime

    class Config:
        from_attributes = True
class PastaUpdate(BaseModel):
    nom_pasta: str


class PastaResumida(BaseModel):
    cod_id: str
    nom_pasta: str
    cod_pai: Optional[str] = None

    class Config:
        from_attributes = True

class AipInFolder(BaseModel):
    cod_id: str
    nom_titulo: str
    dhs_creation: datetime

    class Config:
        from_attributes = True


class PastaDetails(Pasta): 
    aips: List[AipInFolder] = []
    filhas: List[PastaResumida] = [] 
