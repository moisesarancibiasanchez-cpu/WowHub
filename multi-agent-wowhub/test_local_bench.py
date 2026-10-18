"""Benchmark del mock local con diferentes niveles de concurrencia"""
import sys, asyncio, time
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'fixtures' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
test_cases = [cp.to_http_test() for cp in idx.all()]

async def bench(concurrency, label):
    runner = CPRunner(
        max_concurrent=concurrency,
        timeout=5.0, max_retries=1,
        use_hu_mapping=True,
        railway_url="http://127.0.0.1:8000",
        auth_email="maria@cafenorte.cl", auth_password="demo1234",
    )
    t0 = time.time()
    r = await runner.run_audit(test_cases, run_id=f'bench-{concurrency}', resume=False)
    dur = time.time() - t0
    rate = r.total_cps / dur
    print(f'  concurrency={concurrency:2d}  PASS={r.passed:3d}/{r.total_cps} ({r.coverage_pct}%)  dur={dur:.2f}s  rate={rate:.0f} CPs/s')

async def main():
    print(f'Total CPs: {len(test_cases)}  vs mock local sin rate limit')
    print()
    for c in [1, 2, 5, 10, 25]:
        await bench(c, f'c{c}')

asyncio.run(main())
