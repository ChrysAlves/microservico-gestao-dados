# Sistema de Gestão de Dados e Processamento

## Descrição

Microsserviço para gestão de metadados e processamento de arquivos no sistema de preservação digital. Combina API REST síncrona e worker Redis assíncrono

Este serviço atua como o núcleo do sistema de preservação, recebendo arquivos através de filas Redis, processando-os (sanitização, cálculo de checksums, normalização para PDF/A), armazenando no MinIO e registrando todos os metadados no PostgreSQL. Também fornece uma API REST para consulta, renomeação e deleção lógica dos pacotes arquivísticos (AIPs), além de gerenciar uma estrutura hierárquica de pastas para organização dos documentos.

## Tecnologias

- Python/FastAPI
- PostgreSQL
- Redis
- MinIO
- unoconv

## Arquitetura

```
┌──────────────┐      ┌────────────────────┐      ┌────────────────┐
│  🌐 Cliente  │─────▶│   🏗️ Gestão Dados │◀────▶│ 📦 MinIO       │
└──────────────┘      │   (FastAPI+Redis)  │      │   Storage      │
                      └─────────┬──────────┘      └────────────────┘
                                │
                                ▼
                      ┌────────────────────┐
                      │ 🐘 PostgreSQL      │
                      │   Database         │
                      └────────────────────┘
```

## Fluxo de Processamento

```
    🚀 INÍCIO
       │
       ▼
┌─────────────────┐
│ 📨 Recebe       │
│ mensagem Redis  │
└─────────┬───────┘
          │
          ▼
     ❓ Válido?
      ╱       ╲
   Sim╱         ╲Não
     ╱           ╲
    ▼             ▼
┌─────────────┐ ┌─────────────┐
│ 🧹 Sanitiza │ │ ❌ Log erro │
│  arquivos   │ │ e descarta  │
└─────┬───────┘ └─────────────┘
      │
      ▼
┌─────────────┐
│ 🔐 Calcula  │
│   SHA256    │
└─────┬───────┘
      │
      ▼
  📄 Normalizar?
    ╱       ╲
 Sim╱         ╲Não
   ╱           ╲
  ▼             ▼
┌─────────────┐  │
│ 🔄 Converte │  │
│ para PDF/A  │  │
└─────┬───────┘  │
      │          │
      ▼          ▼
┌─────────────────┐
│ ⬆️  Upload para │
│     MinIO       │
└─────────┬───────┘
          │
          ▼
┌─────────────────┐
│ 💾 Registra     │
│ metadados no BD │
└─────────┬───────┘
          │
          ▼
       🏁 FIM
```

## Fluxo de Renomeação de Pasta

```
    🚀 INÍCIO
       │
       ▼
┌─────────────────┐
│ 📝 Recebe novo  │
│ nome da pasta   │
└─────────┬───────┘
          │
          ▼
   🔍 Pasta existe?
      ╱       ╲
   Não╱         ╲Sim
     ╱           ╲
    ▼             ▼
┌─────────────┐ ┌─────────────────┐
│ ❌ Retorna  │ │ 🔍 Nome já      │
│   erro 404  │ │ existe no pai?  │
└─────────────┘ └─────────┬───────┘
                          │
                          ▼
                     ❓ Conflito?
                      ╱       ╲
                   Sim╱         ╲Não
                     ╱           ╲
                    ▼             ▼
                ┌─────────────┐ ┌─────────────────┐
                │ ❌ Retorna  │ │ 🔄 Atualiza     │
                │   erro 409  │ │ caminhos MinIO  │
                └─────────────┘ └─────────┬───────┘
                                          │
                                          ▼
                                ┌─────────────────┐
                                │ 💾 Salva novo   │
                                │ nome no BD      │
                                └─────────┬───────┘
                                          │
                                          ▼
                                       🏁 FIM
```

## Fluxo de Criação de Pasta

```
    🚀 INÍCIO
       │
       ▼
┌─────────────────┐
│ 📝 Recebe dados │
│ da nova pasta   │
└─────────┬───────┘
          │
          ▼
   🔍 Nome já existe
      no mesmo pai?
      ╱       ╲
   Sim╱         ╲Não
     ╱           ╲
    ▼             ▼
┌─────────────┐ ┌─────────────────┐
│ ❌ Retorna  │ │ 💾 Cria pasta   │
│   erro 409  │ │ no banco        │
└─────────────┘ └─────────┬───────┘
                          │
                          ▼
                       🏁 FIM
```

## API Endpoints

### AIPs (Archival Information Packages)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/aips` | Lista todos os AIPs |
| `GET` | `/aips/{id}/details` | Detalhes de um AIP |
| `GET` | `/aips/{id}/location` | Localização do arquivo |
| `POST` | `/aips/` | Registra novo AIP |
| `PUT` | `/aips/{id}/rename` | Renomeia AIP |
| `POST` | `/aips/{id}/logical-delete` | Marca para deleção |

### Pastas (Estrutura Hierárquica)
| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/pastas/` | Lista todas as pastas |
| `GET` | `/pastas/{id}` | Detalhes de uma pasta |
| `POST` | `/pastas/` | Cria nova pasta |
| `PUT` | `/pastas/{id}` | Renomeia pasta |
| `DELETE` | `/pastas/{id}` | Deleta pasta e conteúdo |

## Modelo de Dados

### AIP
- `transfer_id`: Identificador único (PK)
- `titulo`: Nome descritivo editável
- `cod_pasta`: Referência à pasta (FK)
- `creation_date`: Data de criação
- `deleted_at`: Data de deleção lógica

### Pasta
- `cod_id`: Identificador único (PK)
- `nom_pasta`: Nome da pasta
- `cod_pai`: Referência à pasta pai (FK)
- `creation_date`: Data de criação

### Arquivo (Original/Preservação)
- `nome`: Nome sanitizado
- `caminho_minio`: Path no MinIO
- `checksum`: Hash SHA256
- `formato`: Tipo do arquivo
- `aip_id`: Referência ao AIP (FK)

## Execução

```bash
./start.sh
```

Inicia:
- unoconv listener (porta 2002)
- FastAPI server (porta 8000)
- Redis worker (background)

## Configuração

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/preservacao_db
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
UNOCONV_HOST=localhost
UNOCONV_PORT=2002
```

## Troubleshooting

| Problema | Solução |
|----------|---------|
| Worker não processa | Verificar `REDIS_URL` |
| Conversão falha | Executar `unoconv --listener` |
| Upload falha | Verificar credenciais MinIO |
| API não responde | Verificar porta 8000 |