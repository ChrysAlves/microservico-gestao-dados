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
    # --- ALTERAÇÃO 3: Adicionar a relação inversa para eventos ---
    eventos = relationship("EventoPreservacao", back_populates="aip")

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

class EventoPreservacao(Base):
    __tablename__ = "eventos_preservacao"
    id = Column(Integer, primary_key=True, index=True)
    # --- ALTERAÇÃO 1: Mudar a chave estrangeira para apontar para 'aips' ---
    aip_id = Column(Integer, ForeignKey("aips.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    tipo_evento = Column(String, nullable=False)
    detalhes = Column(Text)
    
    # --- ALTERAÇÃO 2: Mudar a relação para apontar para a classe 'AIP' ---
    aip = relationship("AIP", back_populates="eventos")