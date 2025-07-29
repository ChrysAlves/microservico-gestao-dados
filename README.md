# Microsserviço de Gestão de Dados

## Visão Geral

O **Microsserviço de Gestão de Dados** é o "Arquivo Central de Informações" do sistema de preservação digital. Atua como o guardião de TODOS os metadados sobre SIPs, AIPs e DIPs, sendo a "fonte da verdade" para informações de preservação. Este serviço não interage diretamente com o Front-End - toda comunicação passa pelo Microsserviço Mapoteca, que atua como orquestrador central.

## Funcionalidades Principais

### 1. Registro de AIPs
- Recebe e armazena metadados de pacotes de informação arquivística
- Gerencia informações de arquivos originais e preservados
- Calcula e armazena checksums para integridade dos dados
- Mantém histórico de criação e modificação

### 2. Consulta de Localização
- Fornece informações de localização de arquivos para download
- Prioriza arquivos de preservação sobre originais
- Retorna metadados necessários para acesso aos arquivos no MinIO

## Arquitetura do Sistema

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│   Front-End     │───▶│   Microsserviço      │◄───│   Microsserviço │
│                 │    │     Mapoteca         │    │     MinIO       │
└─────────────────┘    │  (Orquestrador)      │    │                 │
                       └──────────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────────┐
                       │  Microsserviço de    │
                       │  Gestão de Dados     │◄─── Microsserviço de
                       │     (Este)           │     Processamento
                       └──────────────────────┘
                                │                           ▲
                                ▼                           │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   PostgreSQL    │    │   Microsserviço │
                       │ (preservacao_db)│    │   de Ingestão   │
                       └─────────────────┘    └─────────────────┘
```

## Comunicação com Outros Microsserviços

### 1. Microsserviço de Processamento (Python)
**Direção**: Processamento → Gestão de Dados

**Endpoint**: `POST /aips/`

**Função**: Após processar um SIP e criar o AIP, o microsserviço de processamento envia todos os metadados gerados para registro permanente

**Payload**:
```json
{
  "transfer_id": "unique-transfer-id",
  "originais": [
    {
      "nome": "documento.pdf",
      "caminho_minio": "originais/path/documento.pdf",
      "checksum": "sha256-hash",
      "formato": "application/pdf"
    }
  ],
  "preservados": [
    {
      "nome": "documento_preservado.pdf",
      "caminho_minio": "preservacoes/path/documento_preservado.pdf",
      "checksum": "sha256-hash",
      "formato": "application/pdf"
    }
  ]
}
```

### 2. Microsserviço Mapoteca (Orquestrador)
**Direção**: Mapoteca ↔ Gestão de Dados

**Endpoints**:
- `GET /aips/{transfer_id}/location` - Consulta localização para download
- `DELETE /aips/{transfer_id}` - Deleção lógica (marca como deletado)
- `PUT /aips/{transfer_id}/rename` - Renomeação de metadados

**Função**: O Mapoteca consulta metadados para operações de download, deleção lógica e renomeação. É o único microsserviço que o Front-End acessa diretamente.

**Resposta de Localização**:
```json
{
  "bucket": "preservacoes",
  "path": "preservacoes/path/documento_preservado.pdf",
  "filename": "documento_preservado.pdf"
}
```

### 3. Microsserviço de Ingestão (TypeScript)
**Direção**: Ingestão → Gestão de Dados (via Processamento)

**Função**: Recebe SIPs do Mapoteca e publica no Kafka para processamento. Não interage diretamente com o Gestão de Dados.

### 4. Microsserviço MinIO (TypeScript)
**Direção**: MinIO ↔ Mapoteca

**Função**: Gerencia armazenamento físico dos arquivos. Só pode ser acessado pelo Mapoteca, que coordena uploads, downloads e deleções físicas.

## Modelo de Dados

### AIP (Archival Information Package)
- `id`: Identificador único interno
- `transfer_id`: Identificador único do transfer
- `creation_date`: Data de criação do registro

### ArquivoOriginal
- `nome`: Nome do arquivo original
- `caminho_minio`: Caminho no storage MinIO
- `checksum`: Hash de integridade (SHA256)
- `formato`: Tipo MIME do arquivo

### ArquivoPreservacao
- `nome`: Nome do arquivo preservado
- `caminho_minio`: Caminho no storage MinIO
- `checksum`: Hash de integridade (SHA256)
- `formato`: Tipo MIME do arquivo


## API Endpoints

### POST /aips/
Registra um novo AIP no sistema (chamado pelo Microsserviço de Processamento).

**Status Code**: 201 Created

### GET /aips/{transfer_id}/location
Retorna a localização de um arquivo para download (chamado pelo Mapoteca).

**Status Code**: 200 OK | 404 Not Found

**Lógica de Priorização**:
1. Primeiro, busca arquivos no bucket `preservacoes`
2. Se não encontrar, busca no bucket `originais`
3. Retorna erro 404 se nenhum arquivo for encontrado

### DELETE /aips/{transfer_id}
Marca um AIP como deletado logicamente (chamado pelo Mapoteca).

**Status Code**: 200 OK | 404 Not Found

### PUT /aips/{transfer_id}/rename
Atualiza o nome/metadados de um AIP (chamado pelo Mapoteca).

**Status Code**: 200 OK | 404 Not Found

## Fluxos de Operação

### Fluxo de Upload (Ingestão)
1. **Front-End** → **Mapoteca**: Envia SIP
2. **Mapoteca** → **Ingestão**: Delega processamento inicial
3. **Ingestão** → **Processamento**: Processa SIP → AIP
4. **Processamento** → **Mapoteca**: Notifica sucesso do processamento
5. **Processamento** → **Gestão de Dados**: Registra metadados do AIP
6. **Mapoteca** → **MinIO**: Armazena AIP final

### Fluxo de Download
1. **Front-End** → **Mapoteca**: Solicita download
2. **Mapoteca** → **Gestão de Dados**: Consulta localização
3. **Gestão de Dados**: Retorna metadados e caminho MinIO
4. **Mapoteca** → **MinIO**: Recupera arquivo
5. **Mapoteca** → **Front-End**: Entrega arquivo

### Fluxo de Deleção
1. **Front-End** → **Mapoteca**: Solicita deleção
2. **Mapoteca** → **Gestão de Dados**: Deleção lógica (marca como deletado)
3. **Gestão de Dados**: Retorna lista de objetos MinIO para exclusão
4. **Mapoteca** → **MinIO**: Exclui arquivos físicos
5. **Mapoteca** → **Gestão de Dados**: Confirma deleção física

## Tratamento de Erros

- **500 Internal Server Error**: Erro ao salvar no banco de dados
- **404 Not Found**: AIP ou arquivos não encontrados
- **Rollback automático**: Em caso de falha na transação

## Logs e Monitoramento

O serviço registra logs detalhados para:
- Recebimento de novos AIPs
- Sucesso/falha no salvamento
- Consultas de localização
- Erros e exceções

## Considerações de Segurança

- Validação de dados via Pydantic schemas
- Transações de banco com rollback automático
- Sanitização de parâmetros de entrada
- Logs sem exposição de dados sensíveis