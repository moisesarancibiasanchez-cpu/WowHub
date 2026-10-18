"""Test runner con CPs reales del documento V134.2"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
print(f'Total CPs cargados: {len(all_cps)}')

# Tomar 5 CPs reales para un test rapido
subset = [cp.to_http_test() for cp in all_cps[:5]]
for cp in subset:
    cid = cp['id']
    method = cp['method']
    path = cp['path']
    status = cp['expected_status']
    print(f'  {cid:14s} {method:6s} {path:50s} status={status}')

# Ejecutar contra Railway (todos iran a /health que es el fallback)
async def run_test():
    runner = CPRunner(max_concurrent=3, timeout=10.0, max_retries=1)
    result = await runner.run_audit(subset, run_id='smoke-real-cps', resume=False)
    print()
    print('=== RESULTADO AUDITORIA ===')
    print(f'Run ID: {result.run_id}')
    print(f'Total: {result.total_cps}')
    print(f'PASS:  {result.passed}')
    print(f'FAIL:  {result.failed}')
    print(f'ERROR: {result.errors}')
    print(f'Coverage: {result.coverage_pct}%')
    print(f'Duration: {result.duration:.2f}s')
    for r in result.results:
        print(f'  {r.cp_id:14s} -> {r.status.value:6s} HTTP {r.http_code} ({r.response_time}s)')

asyncio.run(run_test())
