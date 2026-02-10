#!/bin/bash

# Cria a pasta de cache localmente para não baixar as libs toda vez
mkdir -p .pip_cache

echo "🚀 Iniciando compilação com cache e Wine..."

docker run --security-opt apparmor=unconfined --rm --entrypoint /bin/bash \
-v "$(realpath ../NEXCore):/src/NEXCore" \
-v "$(pwd):/src/NEXCoreBin" \
-v "$(pwd)/.pip_cache:/root/.cache/pip" \
tobix/pywine:3.11 \
-c "cd /src/NEXCoreBin/ && \
    echo '📦 Verificando atualizações do PIP (Silencioso)...' && \
    wine python -m pip install --upgrade pip > /dev/null && \
    wine python -m pip install --upgrade pyinstaller pyinstaller-hooks-contrib > /dev/null && \
    echo '📦 Instalando requirements (usando cache)...' && \
    wine python -m pip install -r /src/NEXCore/requirements.txt && \
    echo '🔨 Compilando NEXCore...' && \
    wine python -m PyInstaller --noupx --clean --onefile --windowed \
    --add-data 'Z:/src/NEXCore/web;web' \
    --name 'NEXCore' \
    --icon '/src/NEXCore/web/assets/icon.png' \
    /src/NEXCore/main.py && \
    echo '🔐 Ajustando permissões dos arquivos gerados...' && \
    chown -R $(id -u):$(id -g) dist build NEXCore.spec .pip_cache"

echo "✅ Pronto! O executável está na pasta dist/."
