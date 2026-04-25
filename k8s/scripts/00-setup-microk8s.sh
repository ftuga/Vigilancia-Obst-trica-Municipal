#!/usr/bin/env bash
# Bootstrap del cluster MicroK8s + addons. Idempotente.
# Requiere sudo en algunos pasos.

set -euo pipefail

require_systemd() {
    if [[ "$(ps -p 1 -o comm= 2>/dev/null)" != "systemd" ]]; then
        echo "ERROR: systemd no está corriendo. En WSL2 habilitar con:"
        echo "  echo -e '[boot]\\nsystemd=true' | sudo tee /etc/wsl.conf"
        echo "  Luego desde PowerShell: wsl --shutdown"
        exit 1
    fi
}

install_microk8s() {
    if command -v microk8s &>/dev/null; then
        echo "MicroK8s ya instalado: $(microk8s version 2>/dev/null | head -1 || echo '?')"
        return
    fi
    echo "Instalando MicroK8s 1.30/stable..."
    sudo snap install microk8s --classic --channel=1.30/stable
}

setup_user_group() {
    if ! groups "$USER" | grep -q microk8s; then
        echo "Agregando $USER al grupo microk8s..."
        sudo usermod -a -G microk8s "$USER"
        echo "Reabrir terminal o ejecutar 'newgrp microk8s' antes de continuar."
        exit 0
    fi
}

fix_git_safe_directory() {
    if ! sudo -n true 2>/dev/null; then
        echo "Necesito sudo para configurar git safe.directory (bug snap wrapper). Pidiendo password..."
    fi
    sudo git config --global --add safe.directory '*' || true
    git config --global --add safe.directory '*' || true
}

enable_addon() {
    local addon=$1
    if microk8s status --format=short 2>/dev/null | grep -q "^addons:enabled:.*$(echo "$addon" | cut -d: -f1)"; then
        echo "Addon $addon ya enabled."
        return
    fi
    echo "Enabling $addon..."
    microk8s enable "$addon"
}

main() {
    require_systemd
    install_microk8s
    setup_user_group
    fix_git_safe_directory

    microk8s status --wait-ready

    enable_addon community
    enable_addon dns
    enable_addon ingress
    enable_addon hostpath-storage
    enable_addon helm3
    enable_addon "metallb:10.64.140.43-10.64.140.49"
    enable_addon registry
    enable_addon observability
    enable_addon argocd

    echo
    echo "Cluster listo. Validación:"
    microk8s kubectl get nodes
    echo
    microk8s kubectl get pods -A | head -20
}

main "$@"
