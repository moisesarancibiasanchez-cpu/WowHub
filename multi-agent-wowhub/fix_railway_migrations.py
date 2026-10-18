#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de correccion de migraciones para Railway
Ejecuta las migraciones que fallaron en produccion
"""

import requests
import json
import sys

BASE_URL = "https://wowhub-api-production.up.railway.app"
API_PREFIX = "/api/v1"

def login():
    r = requests.post(
        f"{BASE_URL}{API_PREFIX}/auth/login",
        json={"email": "maria@cafenorte.cl", "password": "demo1234"}
    )
    if r.status_code != 200:
        print(f"[ERROR] Login failed: {r.status_code} - {r.text}")
        return None
    return r.json()["access_token"]

def verify_endpoints(token):
    print("\n[2] Verificando estado actual...")
    
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_URL}{API_PREFIX}/tenants/me", headers=headers)
    if r.status_code != 200:
        print(f"[ERROR] No se pudo obtener tenant info")
        return None
    
    tenant_id = r.json()["id"]
    print(f"Tenant ID: {tenant_id}")
    
    endpoints_to_test = [
        ("customers", f"/tenants/{tenant_id}/customers"),
        ("orders", f"/tenants/{tenant_id}/orders"),
        ("products", f"/tenants/{tenant_id}/products"),
    ]
    
    results = {}
    for name, path in endpoints_to_test:
        r = requests.get(f"{BASE_URL}{API_PREFIX}{path}", headers=headers, timeout=10)
        status = "OK" if r.status_code == 200 else "FAIL"
        print(f"  [{status}] {name}: {r.status_code}")
        if r.status_code >= 400:
            error = r.json().get("detail", "")[:100]
            print(f"      Error: {error}")
        results[name] = r.status_code == 200
    
    return results

def create_migration_script():
    sql = """-- ============================================================
-- MIGRACIONES CORRECTIVAS PARA RAILWAY
-- WowHub - Correccion de endpoints rotos
-- Fecha: 2026-10-15
-- ============================================================

-- 1. CORRECCION DEL ENUM order_status
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'recibido';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'confirmado';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'en_preparacion';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'listo';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'entregado';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'cancelado';
        ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'pagado';
        RAISE NOTICE 'Enum order_status actualizado';
    ELSE
        RAISE NOTICE 'Tipo order_status no existe';
    END IF;
END $$;

-- 2. AGREGAR COLUMNAS RFM A customers
ALTER TABLE customers ADD COLUMN IF NOT EXISTS rfm_segment VARCHAR(40) NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS r_score INTEGER NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS f_score INTEGER NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS m_score INTEGER NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS rfm_cell VARCHAR(8) NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS rfm_updated_at VARCHAR(40) NULL;

-- 3. VERIFICACION
SELECT 'customers columns:' as info, column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'customers' 
AND column_name LIKE 'rfm_%';
"""
    
    # Path relativo al script (portable entre maquinas/perfiles)
    from pathlib import Path
    script_dir = Path(__file__).parent
    path = script_dir / "migration_fix_railway.sql"
    with open(path, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"[OK] Script SQL guardado: {path}")
    return str(path)

def main():
    print("=" * 60)
    print("WOWHUB - CORRECCION DE MIGRACIONES RAILWAY")
    print("=" * 60)
    
    print("\n[1] Autenticando...")
    token = login()
    if not token:
        print("[ERROR] No se pudo autenticar")
        sys.exit(1)
    print("[OK] Autenticacion exitosa")
    
    print("\n[2] Verificando estado actual...")
    results = verify_endpoints(token)
    
    print("\n[3] Generando script de migracion...")
    script_path = create_migration_script()
    
    print("\n" + "=" * 60)
    print("INSTRUCCIONES DE CORRECCION")
    print("=" * 60)
    print("""
OPCIONES DE EJECUCION:

1. Railway Dashboard:
   - Ir a: https://railway.app/dashboard
   - Proyecto 'wowhub-api' -> Database -> Queries
   - Ejecutar el script migration_fix_railway.sql

2. Railway CLI:
   railway connect wowhub-api
   railway run psql -c "..."

3. Redeploy (automático):
   - Push a main para activar redeploy
   - Alembic ejecutara upgrade head

4. Si tiene acceso DB:
   - psql $DATABASE_URL -f migration_fix_railway.sql
""")
    
    if results:
        print("\nEstado actual de endpoints:")
        for name, ok in results.items():
            print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
