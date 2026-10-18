#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para forzar redeploy en Railway via GitHub Actions
"""

import requests
import json

GITHUB_REPO = "moisesarancibiasanchez-cpu/WowHub"
GITHUB_API = "https://api.github.com"

def check_github_actions():
    """Verifica si hay workflows de GitHub Actions."""
    r = requests.get(f"{GITHUB_API}/repos/{GITHUB_REPO}/actions/workflows")
    if r.status_code == 200:
        workflows = r.json().get("workflows", [])
        print(f"[OK] GitHub Actions - {len(workflows)} workflows:")
        for w in workflows:
            print(f"  - {w.get('name')} ({w.get('state')})")
        return workflows
    else:
        print(f"[WARN] No se pudo acceder a GitHub Actions: {r.status_code}")
        return []

def check_railway_deploy():
    """Verifica estado de deploy en Railway."""
    r = requests.get("https://wowhub-api-production.up.railway.app/health")
    if r.status_code == 200:
        print(f"[OK] Railway API: {r.json()}")
    return r.json() if r.status_code == 200 else None

def create_deployment_dispatch():
    """Intenta crear un dispatch de deployment via GitHub API."""
    print("\n[INFO] Para forzar redeploy, usar Railway CLI:")
    print("  railway up --prod")
    print("\nO hacer un commit vazio:")
    print("  git commit --allow-empty -m 'force redeploy'")
    print("  git push origin main")

def main():
    print("=" * 60)
    print("WOWHUB - OPCIONES DE DEPLOY")
    print("=" * 60)
    
    print("\n[1] Verificando Railway...")
    health = check_railway_deploy()
    
    print("\n[2] Verificando GitHub Actions...")
    workflows = check_github_actions()
    
    print("\n[3] Opciones de correccion:")
    print("-" * 60)
    print("""
OPCION A: Railway CLI (si esta instalado)
-----------------------------------------
  railway login
  railway connect wowhub-api
  railway run alembic upgrade head

OPCION B: Redeploy automatico
-----------------------------------------
  1. Hacer un commit vazio:
     git commit --allow-empty -m "force redeploy for migrations"
  2. Push a GitHub:
     git push origin main
  3. Railway detectara el push y hara redeploy
  4. Las migraciones se ejecutaran automaticamente

OPCION C: Railway Dashboard
-----------------------------------------
  1. Ir a: https://railway.app/dashboard
  2. Seleccionar proyecto wowhub-api
  3. Ir a Database -> wowhub -> Queries
  4. Ejecutar migration_fix_railway.sql

OPCION D: Crear endpoint temporal
-----------------------------------------
  1. Agregar codigo de migration_endpoint.py a la API
  2. Deployar cambios
  3. POST /api/v1/migrate/run
""")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
