# Em ../gestao-dados/models.py

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

class TpPasta(Base):
    __tablename__ = "tp_pastas"
    cod_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom_pasta = Column(String, nullable=False)
    cod_pai = Column(String, ForeignKey("tp_pastas.cod_id"), nullable=True)
    
    filhas = relationship("TpPasta", back_populates="pai")
    pai = relationship("TpPasta", back_populates="filhas", remote_side=[cod_id])
    aips = relationship("TpAip", back_populates="pasta")

    __table_args__ = (
        UniqueConstraint('nom_pasta', 'cod_pai', name='uq_pasta_pai_nome'),
    )

class TpAip(Base):
    __tablename__ = "tp_aips"
    
    cod_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nom_titulo = Column(String, nullable=False)
    nom_ra = Column(String, nullable=True)
    
    dhs_creation = Column(DateTime, default=datetime.utcnow)
    dhs_deleted = Column(DateTime, nullable=True, default=None)

    cod_pasta = Column(String, ForeignKey("tp_pastas.cod_id"), nullable=True)
    pasta = relationship("TpPasta", back_populates="aips")

    arquivos_originais = relationship("TpArquivoOriginal", back_populates="aip")
    arquivos_preservacao = relationship("TpArquivoPreservacao", back_populates="aip")

class TpArquivoOriginal(Base):
    __tablename__ = "tp_arquivos_originais"
    cod_original = Column(Integer, primary_key=True, index=True)
    cod_aip = Column(String, ForeignKey("tp_aips.cod_id"))
    nom_arquivo = Column(String, nullable=False)
    dsc_caminho_minio = Column(String, nullable=False)
    num_checksum = Column(String, nullable=False)
    sig_formato = Column(String, nullable=False)
    
    aip = relationship("TpAip", back_populates="arquivos_originais")

class TpArquivoPreservacao(Base):
    __tablename__ = "tp_arquivos_preservacao"
    cod_preservacao = Column(Integer, primary_key=True, index=True)
    cod_aip = Column(String, ForeignKey("tp_aips.cod_id"))
    nom_arquivo = Column(String, nullable=False)
    dsc_caminho_minio = Column(String, nullable=False)
    num_checksum = Column(String, nullable=False)
    sig_formato = Column(String, nullable=False)
    
    aip = relationship("TpAip", back_populates="arquivos_preservacao")