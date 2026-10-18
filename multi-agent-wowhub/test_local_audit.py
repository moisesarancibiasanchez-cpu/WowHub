"""Audit V134.2 contra MOCK SERVER LOCAL (sin rate limit)"""
import sys, asyncio, time
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'fixtures' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner
from collections import Counter

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
test_cases = [cp.to_http_test() for cp in all_cps]
print(f'Total CPs: {len(test_cases)}')
print(f'Target: http://127.0.0.1:8000 (mock server, sin rate limit)')
print()

async def run():
    runner = CPRunner(
        max_concurrent=2,                # <-- REDUCIDO para no throttlear
        timeout=5.0,
        max_retries=1,
        use_hu_mapping=True,
        railway_url="http://127.0.0.1:8000",  # <-- apunta al mock
        auth_email="maria@cafenorte.cl",
        auth_password="demo1234",
    )

    t_start = time.time()
    result = await runner.run_audit(test_cases, run_id='local-mock-001', resume=False)
    total_dur = time.time() - t_start

    print()
    print('=' * 60)
    print('AUDITORIA V134.2 vs MOCK LOCAL (localhost:8000)')
    print('=' * 60)
    print(f'Total:     {result.total_cps}')
    print(f'PASS:      {result.passed} ({result.coverage_pct}%)')
    print(f'FAIL:      {result.failed}')
    print(f'ERROR:     {result.errors}')
    print(f'Duration:  {total_dur:.1f}s')

    pass_codes = Counter()
    fail_codes = Counter()
    for r in result.results:
        if r.status.value == 'pass' and r.http_code:
            pass_codes[r.http_code] += 1
        elif r.status.value == 'fail' and r.http_code:
            fail_codes[r.http_code] += 1
        elif r.status.value == 'error':
            fail_codes['network'] += 1

    print()
    print('PASS por HTTP code:')
    for code, n in sorted(pass_codes.items(), key=lambda x: -x[1]):
        print(f'  HTTP {code}: {n}')
    print()
    print('FAIL por HTTP code:')
    for code, n in sorted(fail_codes.items(), key=lambda x: -x[1]):
        print(f'  HTTP {code}: {n}')

    # Muestra de los primeros 5 fallos para entender
    print()
    print('Sample de fallos (5):')
    fails = [r for r in result.results if r.status.value == 'fail'][:5]
    for r in fails:
        actual = (r.actual or '').replace('\n', ' ')[:180]
        print(f"  {r.cp_id:14s} HTTP {r.http_code}  {actual}")

asyncio.run(run())
