#!/usr/bin/env bash
set -euxo pipefail

# Instalar dependencias del sistema
playwright install-deps

# Instalar TODOS los navegadores (o al menos chromium)
playwright install