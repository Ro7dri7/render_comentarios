#!/usr/bin/env bash
# playwright.sh
set -euxo pipefail

# Instalar dependencias del sistema
playwright install-deps chromium

# Instalar Chromium
playwright install chromium