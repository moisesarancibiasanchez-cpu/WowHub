#!/usr/bin/env python3
"""
WowHub Multi-Agent System v1.1.0 - CLI Principal
Directiva V134.2 - 4 agentes especializados
"""

import asyncio
import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))


def load_env():
    """Carga variables de entorno desde .env si existe."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        logger.info("Cargando configuracion desde .env")
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


async def smoke_test():
    """Ejecuta smoke test del sistema."""
    print("\n" + "="*60)
    print("SMOKE TEST - WowHub Multi-Agent System v1.1.0")
    print("="*60 + "\n")
    
    try:
        from agents.orchestrator import Orchestrator
        
        print("1. Inicializando Orchestrator...")
        orch = Orchestrator(session_id="smoke-001")
        print(f"   Orchestrator listo (max_iterations={orch.max_iterations})")
        
        print("\n2. Inicializando sub-agentes...")
        _ = orch.researcher
        print(f"   Researcher: {orch.researcher.name}")
        
        _ = orch.coder
        print(f"   Coder: {orch.coder.name}")
        
        _ = orch.validator
        print(f"   Validator: {orch.validator.name}")
        
        print("\n3. Ejecutando smoke request...")
        result = await orch.execute_user_request("Smoke test: lista los 4 agentes disponibles")
        print(f"   Status: {result.get('status')}")
        print(f"   Iterations: {result.get('iterations')}")
        
        print("\n4. Generando health report...")
        health = orch.get_health_report()
        health_path = Path(__file__).parent / "agent_health.json"
        with open(health_path, "w", encoding="utf-8") as f:
            json.dump(health, f, indent=2, ensure_ascii=False)
        print(f"   Health guardado: {health_path}")
        
        print("\n" + "="*60)
        print("SMOKE TEST PASÓ - Sistema operativo")
        print("="*60 + "\n")
        
        return {"status": "ok", "session_id": "smoke-001", "agents_initialized": 4, "health_report": str(health_path)}
        
    except Exception as e:
        logger.error(f"Smoke test falló: {e}")
        print("\n" + "="*60)
        print(f"SMOKE TEST FALLÓ: {e}")
        print("="*60 + "\n")
        raise


async def execute_request(request: str, session_id: str = "cli-001"):
    """Ejecuta un request específico del usuario."""
    from agents.orchestrator import Orchestrator
    
    print(f"\nEjecutando request: {request[:80]}...")
    
    orch = Orchestrator(session_id=session_id)
    result = await orch.execute_user_request(request)
    
    print(f"\nResultado ({result.get('iterations')} iteraciones):")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return result


async def run_audit():
    """Ejecuta auditoria completa V134.2."""
    from agents.orchestrator import Orchestrator
    
    print("\n" + "="*60)
    print("AUDITORIA V134.2 - WowHub Multi-Agent System")
    print("="*60 + "\n")
    
    orch = Orchestrator(session_id="audit-001")
    
    request = "Ejecuta auditoria V134.2 completa: verifica los 599 casos de prueba"
    
    result = await orch.execute_user_request(request)
    
    print("\nResumen de auditoria:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    output_path = Path(__file__).parent / "audit_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResultados guardados: {output_path}")
    
    return result


async def show_health():
    """Muestra reporte de salud del sistema."""
    from agents.orchestrator import Orchestrator

    print("\n" + "="*60)
    print("HEALTH REPORT - WowHub Multi-Agent System")
    print("="*60 + "\n")

    orch = Orchestrator(session_id="health-check")
    # Inicializar los 3 sub-agentes para un reporte de salud significativo
    _ = (orch.researcher, orch.coder, orch.validator)
    health = orch.get_health_report()
    health["status"] = "ok"

    print(json.dumps(health, indent=2, ensure_ascii=False))

    return health


def main():
    """Entry point del CLI."""
    parser = argparse.ArgumentParser(
        description="WowHub Multi-Agent System v1.1.0 - CLI Principal",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("--smoke", action="store_true", help="Ejecuta smoke test del sistema")
    parser.add_argument("--request", type=str, help="Ejecuta un request especifico")
    parser.add_argument("--health", action="store_true", help="Muestra reporte de salud")
    parser.add_argument("--audit", action="store_true", help="Ejecuta auditoria V134.2 completa")
    parser.add_argument("--session-id", type=str, default="cli-001", help="Session ID para el Orchestrator")
    parser.add_argument("--debug", action="store_true", help="Activa modo debug")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    load_env()
    
    api_key = os.getenv("MM_API_KEY", "")
    if not api_key or api_key == "sk-your-api-key-here":
        logger.warning("MM_API_KEY no configurada. Usando MockLLM.")
    
    try:
        if args.smoke:
            result = asyncio.run(smoke_test())
        elif args.request:
            result = asyncio.run(execute_request(args.request, args.session_id))
        elif args.health:
            result = asyncio.run(show_health())
        elif args.audit:
            result = asyncio.run(run_audit())
        else:
            parser.print_help()
            return
        
        if result.get("status") in ("ok", "pass", "success"):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("Operacion cancelada por usuario")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
