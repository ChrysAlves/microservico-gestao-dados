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