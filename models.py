# models.py (CORRIGIDO)

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class AIP(Base):
    __tablename__ = "aips"
    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(String, unique=True, index=True, nullable=False)
    creation_date = Column(DateTime, default=datetime.utcnow)
    
    arquivos_originais = relationship("ArquivoOriginal", back_populates="aip")
    arquivos_preservacao = relationship("ArquivoPreservacao", back_populates="aip")
    # A relação com 'eventos' foi removida daqui

class ArquivoOriginal(Base):
    __tablename__ = "arquivos_originais"
    id = Column(Integer, primary_key=True, index=True)
    aip_id = Column(Integer, ForeignKey("aips.id"))
    nome = Column(String, nullable=False)
    caminho_minio = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    algoritmo_checksum = Column(String, default="SHA256")
    formato = Column(String, nullable=False)
    
    aip = relationship("AIP", back_populates="arquivos_originais")

class ArquivoPreservacao(Base):
    __tablename__ = "arquivos_preservacao"
    id = Column(Integer, primary_key=True, index=True)
    aip_id = Column(Integer, ForeignKey("aips.id"))
    nome = Column(String, nullable=False)
    caminho_minio = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    algoritmo_checksum = Column(String, default="SHA256")
    formato = Column(String, nullable=False)
    
    aip = relationship("AIP", back_populates="arquivos_preservacao")

