# Service Verification Guide

## Overview

Este documento explica cómo verificar que todos los servicios del Backlog Toolkit están funcionando correctamente.

## Services Overview

El toolkit ejecuta 3 servicios principales:

1. **LiteLLM Proxy** (puerto 8000) - Proxy de modelos con routing inteligente
2. **RAG Server** (puerto 8001) - Búsqueda semántica de código
3. **Ollama** (puerto 11434) - Modelos locales (opcional)

## Quick Verification

### Script de Verificación Rápida

```bash
# Verificar todos los servicios
./scripts/services/status-services.sh
```

### Verificación Manual

```bash
# 1. Verificar procesos
ps aux | grep -E "litellm|server.py|ollama" | grep -v grep

# 2. Verificar puertos
lsof -i :8000,8001,11434 | grep LISTEN

# 3. Health checks
curl -s http://localhost:8000/health -H "Authorization: Bearer $LITELLM_MASTER_KEY"
curl -s http://localhost:8001/health
curl -s http://localhost:11434/api/version
```

## LiteLLM Proxy (Port 8000)

### Check de Salud

```bash
# Cargar master key
source ~/.backlog-toolkit-env

# Verificar health
curl -s http://localhost:8000/health \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.'
```

**Respuesta esperada:**
```json
{
  "healthy_endpoints": [...],
  "unhealthy_endpoints": [],
  "healthy_count": 3,
  "unhealthy_count": 0
}
```

### Listar Modelos

```bash
curl -s http://localhost:8000/v1/models \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.data[] | {id, created}'
```

**Modelos configurados:**
- `cheap` - Claude 3.5 Haiku (AWS Bedrock)
- `balanced` - Claude 3.5 Sonnet (AWS Bedrock)
- `frontier` - Claude 3 Opus (AWS Bedrock)

### Test de Completions

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cheap",
    "messages": [{"role": "user", "content": "Say hello"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'
```

### Logs

```bash
# Ver logs en tiempo real
tail -f ~/.backlog-toolkit/services/logs/litellm.log

# Ver últimos errores
grep -i error ~/.backlog-toolkit/services/logs/litellm.log | tail -20
```

### Troubleshooting

#### Error: "Authentication Error, No api key passed in"

**Causa**: No estás incluyendo el master key en la petición.

**Solución**:
```bash
# Asegúrate de tener el master key cargado
source ~/.backlog-toolkit-env
echo $LITELLM_MASTER_KEY

# Incluye el header Authorization
curl -H "Authorization: Bearer $LITELLM_MASTER_KEY" ...
```

#### Error: "Missing Anthropic API Key"

**Causa**: Los modelos están configurados para Anthropic API directa pero usas Bedrock.

**Solución**: Verifica que `~/.config/litellm/config.yaml` usa modelos Bedrock:
```yaml
model_list:
  - model_name: cheap
    litellm_params:
      model: bedrock/anthropic.claude-3-5-haiku-20241022-v1:0
      aws_region_name: os.environ/AWS_REGION
```

## RAG Server (Port 8001)

### Check de Salud

```bash
curl -s http://localhost:8001/health | jq '.'
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "collection_count": 0
}
```

### Estadísticas

```bash
curl -s http://localhost:8001/stats | jq '.'
```

**Respuesta:**
```json
{
  "collection_name": "codebase",
  "document_count": 0,
  "metadata": {
    "description": "Codebase embeddings for RAG"
  }
}
```

### Test de Indexación

```bash
# Indexar un documento
curl -s -X POST http://localhost:8001/index \
  -H "Content-Type: application/json" \
  -d '{
    "documents": ["function hello() { return \"world\"; }"],
    "metadatas": [{"file": "example.ts", "line": 1}],
    "ids": ["example_ts_1"]
  }' | jq '.'
```

**Respuesta esperada:**
```json
{
  "indexed": 1,
  "collection_count": 1
}
```

### Test de Búsqueda

```bash
# Buscar documentos
curl -s -X POST http://localhost:8001/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "hello function",
    "n_results": 5
  }' | jq '.results.documents'
```

**Respuesta esperada:**
```json
[
  [
    "function hello() { return \"world\"; }"
  ]
]
```

### Logs

```bash
# Ver logs
tail -f ~/.backlog-toolkit/services/logs/rag.log

# Ver últimos errores
grep -i error ~/.backlog-toolkit/services/logs/rag.log | tail -20
```

### Troubleshooting

#### Error: "Connection refused"

**Causa**: El servidor RAG no está corriendo.

**Solución**:
```bash
# Iniciar RAG server
./scripts/services/start-services.sh
# O manualmente
python3 /Users/fbelchi/github/backlog-agents/scripts/rag/server.py --port 8001 &
```

#### Error: "Import error: chromadb"

**Causa**: Falta instalar dependencias.

**Solución**:
```bash
pip install flask chromadb sentence-transformers
```

## Ollama (Port 11434) - Opcional

### Check de Salud

```bash
curl -s http://localhost:11434/api/version | jq '.'
```

### Listar Modelos

```bash
ollama list
```

### Test de Generación

```bash
curl -s http://localhost:11434/api/generate \
  -d '{
    "model": "llama2",
    "prompt": "Why is the sky blue?",
    "stream": false
  }' | jq '.response'
```

## Verificación Completa

### Script de Test

Crea un script para verificar todo:

```bash
#!/bin/bash
# test-all-services.sh

source ~/.backlog-toolkit-env

echo "=== LiteLLM Health ==="
curl -s http://localhost:8000/health \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" | jq '.healthy_count, .unhealthy_count'

echo ""
echo "=== RAG Health ==="
curl -s http://localhost:8001/health | jq '.status'

echo ""
echo "=== Ollama (if installed) ==="
curl -s http://localhost:11434/api/version 2>/dev/null | jq '.version' || echo "Not installed"

echo ""
echo "=== Process Status ==="
echo "LiteLLM: $(pgrep -f 'litellm --config' > /dev/null && echo '✓ Running' || echo '✗ Not running')"
echo "RAG: $(pgrep -f 'server.py' > /dev/null && echo '✓ Running' || echo '✗ Not running')"
echo "Ollama: $(pgrep -f 'ollama' > /dev/null && echo '✓ Running' || echo '✗ Not running')"
```

Hazlo ejecutable y úsalo:

```bash
chmod +x test-all-services.sh
./test-all-services.sh
```

## Iniciar/Detener Servicios

### Iniciar Todos

```bash
# Con SSO credentials
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh

# O simplemente (usa env file)
./scripts/services/start-services.sh
```

### Detener Todos

```bash
./scripts/services/stop-services.sh
```

### Reiniciar

```bash
./scripts/services/restart-services.sh
```

### Estado

```bash
./scripts/services/status-services.sh
```

## Puertos Usados

| Servicio | Puerto | Protocolo | Auth Required |
|----------|--------|-----------|---------------|
| LiteLLM | 8000 | HTTP | Sí (master key) |
| RAG | 8001 | HTTP | No |
| Ollama | 11434 | HTTP | No |

## Archivos de Configuración

| Servicio | Config | Logs | PIDs |
|----------|--------|------|------|
| LiteLLM | `~/.config/litellm/config.yaml` | `~/.backlog-toolkit/services/logs/litellm.log` | `~/.backlog-toolkit/services/pids/litellm.pid` |
| RAG | N/A | `~/.backlog-toolkit/services/logs/rag.log` | `~/.backlog-toolkit/services/pids/rag.pid` |

## Variables de Entorno

Las credenciales y configuración están en `~/.backlog-toolkit-env`:

```bash
# AWS SSO Credentials (auto-cargadas)
export AWS_ACCESS_KEY_ID='...'
export AWS_SECRET_ACCESS_KEY='...'
export AWS_SESSION_TOKEN='...'
export AWS_REGION='eu-west-1'

# LiteLLM Master Key
export LITELLM_MASTER_KEY='sk-litellm-...'

# Opcional: Profile específico
export BACKLOG_AWS_PROFILE='cc'
```

## Próximos Pasos

Una vez verificados los servicios:

1. **Usar LiteLLM** en tus aplicaciones:
   ```python
   import openai

   openai.api_base = "http://localhost:8000/v1"
   openai.api_key = "sk-litellm-..."

   response = openai.ChatCompletion.create(
       model="cheap",
       messages=[{"role": "user", "content": "Hello"}]
   )
   ```

2. **Indexar tu codebase** en RAG:
   ```bash
   # Ver scripts en scripts/rag/ para indexación automática
   ```

3. **Integrar con skills**:
   - Los skills del toolkit usan automáticamente estos servicios
   - Ver `docs/skills/` para ejemplos

## Documentación Relacionada

- [AWS SSO Setup](./AWS-SSO-SETUP.md)
- [AWS Credentials](./AWS-CREDENTIALS.md)
- [Service Startup Guide](./SERVICE-STARTUP-GUIDE.md)
- [Troubleshooting](./TROUBLESHOOTING.md)
