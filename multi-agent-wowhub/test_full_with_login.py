"""Auditoria V134.2 con auto-login"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
test_cases = [cp.to_http_test() for cp in all_cps]
print(f'Total CPs: {len(test_cases)}')

# Credenciales de demo (maria@cafenorte.cl / demo1234 - del seed)
async def run():
    # Sin auto-login primero para ver el baseline
    runner = CPRunner(
        max_concurrent=10,
        timeout=8.0,
        max_retries=1,
        use_hu_mapping=True,
        auth_email="maria@cafenorte.cl",
        auth_password="demo1234",
    )
    result = await runner.run_audit(test_cases, run_id='audit-login-001', resume=False)
    print()
    print('=' * 60)
    print('AUDITORIA V134.2 CON AUTO-LOGIN')
    print('=' * 60)
    print(f"Total:  {result.total_cps}")
    print(f"PASS:   {result.passed}")
    print(f"FAIL:   {result.failed}")
    print(f"ERROR:  {result.errors}")
    print(f"Coverage: {result.coverage_pct}%")
    print(f"Duration: {result.duration:.1f}s")
    print()
    from collections import Counter
    fail_codes = Counter()
    pass_codes = Counter()
    for r in result.results:
        if r.status.value == 'pass' and r.http_code:
            pass_codes[r.http_code] += 1
        elif r.status.value == 'fail' and r.http_code:
            fail_codes[r.http_code] += 1
        elif r.status.value == 'error':
            fail_codes['network_error'] += 1
    print("PASS por HTTP code:")
    for code, n in sorted(pass_codes.items(), key=lambda x: str(x[0])):
        print(f"  HTTP {code}: {n}")
    print()
    print("FAIL por HTTP code:")
    for code, n in sorted(fail_codes.items(), key=lambda x: str(x[0])):
        print(f"  HTTP {code}: {n}")

asyncio.run(run())
