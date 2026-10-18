"""Diagnostico de 422: que campos faltan"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'fixtures' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
test_cases = [cp.to_http_test() for cp in all_cps]

async def run():
    runner = CPRunner(
        max_concurrent=5, timeout=8.0, max_retries=0,
        use_hu_mapping=True,
        auth_email="maria@cafenorte.cl", auth_password="demo1234",
    )
    result = await runner.run_audit(test_cases, run_id='diag-422-final', resume=False)
    print()
    print(f'Total: {result.total_cps}  PASS: {result.passed}  FAIL: {result.failed}  Coverage: {result.coverage_pct}%')
    print()
    print('--- Sample de 422 (10) ---')
    fails_422 = [r for r in result.results if r.status.value == 'fail' and r.http_code == 422][:10]
    for r in fails_422:
        actual = (r.actual or '').replace('\n', ' ')[:250]
        print(f"  {r.cp_id:14s} HTTP {r.http_code}")
        print(f"    {actual}")
        print()

asyncio.run(run())
