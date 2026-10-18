"""Test con endpoints publicos (sin auth)"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner
from runner.hu_endpoint_map import HU_ENDPOINTS, resolve_hu_endpoint

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
print(f'Total CPs cargados: {len(all_cps)}')
print()

# Filtrar HUs con endpoints publicos (no requieren auth)
public_hus = [hu for hu, m in HU_ENDPOINTS.items() if not m.get('requires_auth', True)]
print(f'HUs con endpoints publicos: {len(public_hus)}')
print()

# Tomar 1 CP functional por cada HU publica
sample = []
for hu_id in public_hus[:8]:  # 8 HUs publicas
    cps_hu = idx.by_hu_id(hu_id)
    for cp in cps_hu:
        if cp.type == 'functional':
            sample.append(cp.to_http_test())
            break

print(f'Sample de CPs publicos ({len(sample)} CPs):')
for cp in sample:
    resolved = resolve_hu_endpoint(cp['hu_id'], cp['id'][-1])
    print(f"  {cp['id']:14s} hu_id={cp['hu_id']:7s} -> {resolved['method']:5s} {resolved['path']:50s} (expected {resolved['expected_status']})")
print()

async def run_test():
    runner = CPRunner(max_concurrent=5, timeout=10.0, max_retries=1, use_hu_mapping=True)
    result = await runner.run_audit(sample, run_id='public-smoke-001', resume=False)
    print()
    print('=== RESULTADO ===')
    print(f"PASS:  {result.passed}")
    print(f"FAIL:  {result.failed}")
    print(f"ERROR: {result.errors}")
    print(f"Coverage: {result.coverage_pct}%")
    print()
    for r in result.results:
        print(f"  {r.cp_id:14s} {r.status.value:6s} HTTP {r.http_code} ({r.response_time}s)")

asyncio.run(run_test())
