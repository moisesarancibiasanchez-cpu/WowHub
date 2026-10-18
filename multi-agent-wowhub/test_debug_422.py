"""Debug de CPs con HTTP 422"""
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
        max_concurrent=10, timeout=8.0, max_retries=0,
        use_hu_mapping=True,
        auth_email="maria@cafenorte.cl", auth_password="demo1234",
    )
    # Ejecutar solo los 5 primeros POST
    post_tcs = [tc for tc in test_cases if tc.get('method') in ('POST', 'PUT', 'PATCH')][:8]
    result = await runner.run_audit(post_tcs, run_id='debug-422-001', resume=False)
    print()
    for r in result.results:
        actual = (r.actual or '')[:200]
        print(f"  {r.cp_id:14s} {r.status.value:6s} HTTP {r.http_code}")
        print(f"    actual: {actual}")
        print()

asyncio.run(run())
