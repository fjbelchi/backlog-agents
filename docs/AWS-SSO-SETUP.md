# Using AWS SSO with Backlog Toolkit

## Overview

El toolkit ahora soporta **credenciales temporales de AWS SSO**, las mismas que usas para Claude Code.

## Cómo Funciona

Cuando ejecutas `aws sso login`, AWS CLI:
1. Guarda tokens SSO en `~/.aws/sso/cache/`
2. Genera credenciales temporales en `~/.aws/cli/cache/`
3. Estas credenciales incluyen:
   - AccessKeyId (ASIA...)
   - SecretAccessKey
   - SessionToken
   - Expiration (válido ~8-12 horas)

LiteLLM (via boto3) puede usar estas credenciales automáticamente.

## Setup

### 1. Configura tu perfil SSO (ya lo tienes)

Tu `~/.aws/config` ya tiene:

```ini
[profile cc]
sso_session = cc
sso_account_id = 817807756991
sso_role_name = ClaudeAccess
region = eu-west-1

[sso-session cc]
sso_start_url = https://d-9066270955.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access
```

### 2. Login con SSO

```bash
aws sso login --profile cc
```

Esto abre el navegador para autenticarte y guarda las credenciales temporales.

### 3. Usa ese perfil con el toolkit

```bash
# Opción 1: Variable de entorno
export BACKLOG_AWS_PROFILE=cc
./scripts/services/start-services.sh

# Opción 2: En una sola línea
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh

# Opción 3: Usar AWS_PROFILE (también funciona)
export AWS_PROFILE=cc
./scripts/services/start-services.sh
```

## Verificar que Funciona

```bash
# 1. Login con SSO
aws sso login --profile cc

# 2. Verificar que tienes acceso
aws sts get-caller-identity --profile cc

# 3. Iniciar servicios con SSO
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh
```

Deberías ver:

```
[INFO] Detected SSO profile: cc
[✓] SSO credentials loaded for profile: cc
[✓] AWS region: eu-west-1
```

## Renovación Automática

Las credenciales SSO expiran después de varias horas. Cuando expiren:

1. El script te avisará:
   ```
   [!] SSO credentials expired
   [INFO] Try running: aws sso login --profile cc
   ```

2. Ejecuta el login nuevamente:
   ```bash
   aws sso login --profile cc
   ```

3. Reinicia los servicios:
   ```bash
   ./scripts/services/restart-services.sh
   ```

## Configuración en .backlog-toolkit-env

Puedes agregar esto a tu archivo `~/.backlog-toolkit-env`:

```bash
# AWS SSO Profile para Backlog Toolkit
export BACKLOG_AWS_PROFILE=cc

# O simplemente
export AWS_PROFILE=cc
```

Luego solo necesitas:

```bash
# Login (cuando expire)
aws sso login --profile cc

# Iniciar servicios (usa el perfil del env)
./scripts/services/start-services.sh
```

## Ventajas de SSO vs Credenciales Estáticas

### SSO (Recomendado para uso con Claude Code)
✅ Usa las mismas credenciales que Claude Code
✅ Credenciales temporales (más seguras)
✅ Renovación centralizada via SSO
✅ No necesitas crear IAM users adicionales
✅ Permisos gestionados por tu organización

### Credenciales Estáticas
✅ No expiran (hasta que las rotes manualmente)
✅ No requieren re-login
✅ Más simple para desarrollo local
❌ Menos seguras
❌ Requieren crear IAM users

## Troubleshooting

### "Failed to load SSO credentials"

**Causa**: No has hecho login o las credenciales expiraron.

**Solución**:
```bash
aws sso login --profile cc
```

### "Profile 'cc' has no static credentials"

**Mensaje esperado**: Esto es normal para perfiles SSO. El script intentará obtener credenciales temporales automáticamente.

### Las credenciales expiran frecuentemente

**Normal**: Las credenciales SSO típicamente duran 8-12 horas.

**Solución**: Haz login de nuevo cuando expire:
```bash
aws sso login --profile cc
```

### LiteLLM no puede acceder a Bedrock

**Verificar**:
```bash
# 1. Verificar que el perfil funciona
aws bedrock list-foundation-models --profile cc --region us-east-1

# 2. Ver qué credenciales está usando
aws sts get-caller-identity --profile cc

# 3. Verificar permisos
# Tu rol debe tener: AmazonBedrockFullAccess
```

## Permisos Necesarios

Tu rol SSO (ClaudeAccess) debe tener permisos para:
- `bedrock:InvokeModel`
- `bedrock:InvokeModelWithResponseStream`
- `bedrock:ListFoundationModels`

Pídele a tu administrador de AWS que agregue la política `AmazonBedrockFullAccess` al rol si no lo tiene.

## Modo Offline / Sin SSO

Si necesitas trabajar sin SSO (ej: en un entorno CI/CD), crea credenciales estáticas:

1. Consulta `docs/AWS-CREDENTIALS.md`
2. Usa variables de entorno o credenciales estáticas
3. El toolkit soporta ambos métodos

## Resumen Rápido

```bash
# Setup inicial (una vez)
aws configure sso  # Si aún no tienes SSO configurado

# Login (cada vez que expire)
aws sso login --profile cc

# Usar con toolkit
BACKLOG_AWS_PROFILE=cc ./scripts/services/start-services.sh

# O agregar al env file
echo 'export BACKLOG_AWS_PROFILE=cc' >> ~/.backlog-toolkit-env
./scripts/services/start-services.sh
```

## Próximos Pasos

1. ✅ Haz `aws sso login --profile cc`
2. ✅ Configura `BACKLOG_AWS_PROFILE=cc`
3. ✅ Inicia los servicios
4. ✅ Trabaja normalmente
5. 🔄 Re-login cuando expire (recibirás aviso)

¡Listo! Ahora puedes usar las mismas credenciales SSO que usas para Claude Code.
