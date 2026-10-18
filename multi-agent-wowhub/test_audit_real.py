"""Test end-to-end del Runner con mapping HU→endpoint y CPs reales"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
print(f'Total CPs cargados: {len(all_cps)}')
print(f'HUs distintas: {len(idx.by_hu_id.__self__._by_hu_id)}')
print()

# Tomar muestra: 5 CPs de HUs distintas
sample_hus = ['HU_01', 'HU_03', 'HU_15', 'HU_17', 'HU_37']
sample = []
for hu_id in sample_hus:
    cps_hu = idx.by_hu_id(hu_id)
    if cps_hu:
        # Tomar el primer CP functional de cada HU
        for cp in cps_hu:
            if cp.type == 'functional':
                sample.append(cp.to_http_test())
                break

print(f'Sample ({len(sample)} CPs de HUs mixtas):')
for cp in sample:
    print(f'  {cp["id"]:14s} hu_id={cp["hu_id"]:7s} type={cp["type"]:11s}')
print()

# Ejecutar contra Railway SIN auth (usando el mapping)
async def run_test():
    runner = CPRunner(max_concurrent=5, timeout=10.0, max_retries=1, use_hu_mapping=True)
    result = await runner.run_audit(sample, run_id='mapping-smoke-001', resume=False)
    print()
    print('=== RESULTADO AUDITORIA (con mapping HU->endpoint) ===')
    print(f'Run ID: {result.run_id}')
    print(f'Total: {result.total_cps}')
    print(f'PASS:  {result.passed}')
    print(f'FAIL:  {result.failed}')
    print(f'ERROR: {result.errors}')
    print(f'Coverage: {result.coverage_pct}%')
    print(f'Duration: {result.duration:.2f}s')
    print()
    print('Detalle por CP:')
    for r in result.results:
        print(f'  {r.cp_id:14s} -> {r.status.value:6s} HTTP {r.http_code} ({r.response_time}s)')

asyncio.run(run_test())
