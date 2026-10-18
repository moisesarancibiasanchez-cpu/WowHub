"""Auditoria completa con mapping HU->endpoint"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
print(f'Total CPs a ejecutar: {len(all_cps)}')

# Convertir todos los CPs al formato HTTP
test_cases = [cp.to_http_test() for cp in all_cps]
print(f'Test cases preparados: {len(test_cases)}')

# Distribucion por HU
from collections import Counter
hus_count = Counter([tc['hu_id'] for tc in test_cases if tc.get('hu_id')])
print(f'HUs cubiertas: {len(hus_count)}')
print()

async def run_full_audit():
    runner = CPRunner(max_concurrent=15, timeout=8.0, max_retries=1, use_hu_mapping=True)
    result = await runner.run_audit(test_cases, run_id='audit-full-with-mapping-001', resume=False)
    print()
    print('=' * 60)
    print('AUDITORIA V134.2 COMPLETA (con mapping HU->endpoint)')
    print('=' * 60)
    print(f"Run ID:         {result.run_id}")
    print(f"Total CPs:      {result.total_cps}")
    print(f"PASS:           {result.passed}")
    print(f"FAIL:           {result.failed}")
    print(f"ERROR:          {result.errors}")
    print(f"Coverage:       {result.coverage_pct}%")
    print(f"Duration:       {result.duration:.1f}s")
    print(f"LLM calls saved: {result.llm_calls_saved}")
    print()
    # Distribucion de FAILs
    from collections import Counter
    fail_codes = Counter()
    for r in result.results:
        if r.status.value == 'fail' and r.http_code:
            fail_codes[r.http_code] += 1
        elif r.status.value == 'error':
            fail_codes['network_error'] += 1
    print("Distribucion de fallos por HTTP code:")
    for code, n in sorted(fail_codes.items(), key=lambda x: str(x[0])):
        print(f"  HTTP {code}: {n}")
    print()
    # Top 10 fallos con detalle
    print("Primeros 10 fallos:")
    fail_results = [r for r in result.results if r.status.value == 'fail'][:10]
    for r in fail_results:
        msg = (r.error_msg or r.actual or '')[:80]
        print(f"  {r.cp_id:14s} HTTP {r.http_code}  {msg}")

asyncio.run(run_full_audit())
