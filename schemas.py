from pydantic import BaseModel
from typing import List, Optional

class ArquivoBase(BaseModel):
    nome: str
    caminho_minio: str
    checksum: str
    formato: str

class ArquivoOriginalCreate(ArquivoBase):
    pass

class ArquivoPreservacaoCreate(ArquivoBase):
    pass

class AIPCreate(BaseModel):
    transfer_id: str
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