"""Debug detallado de CPs 422 - muestra el body enviado vs el error"""
import sys, asyncio
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'fixtures' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner
from runner.fixtures import get_body, list_fixtures
from runner.hu_endpoint_map import resolve_hu_endpoint

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
test_cases = [cp.to_http_test() for cp in all_cps]
print(f'Total CPs: {len(test_cases)}')
print(f'Fixtures registrados: {len(list_fixtures())}')
print()

async def run():
    runner = CPRunner(
        max_concurrent=8, timeout=8.0, max_retries=0,
        use_hu_mapping=True,
        auth_email="maria@cafenorte.cl", auth_password="demo1234",
    )
    # Solo los 15 primeros POST/PUT
    post_cps = [cp for cp in all_cps if cp.id.endswith(('-F', '-S', '-N', '-R'))]
    # Filtrar solo los que por HU requieren POST
    post_hus = ['HU_01', 'HU_03', 'HU_05', 'HU_15', 'HU_23', 'HU_24']
    sample = [cp for cp in post_cps if cp.hu_id in post_hus][:12]
    sample_tcs = [cp.to_http_test() for cp in sample]

    for tc in sample_tcs:
        cp_type = tc['id'][-1]
        resolved = resolve_hu_endpoint(tc['hu_id'], cp_type)
        body = get_body(resolved['method'], resolved['path'], {}, cp_type)
        print(f"  {tc['id']:14s} {resolved['method']:5s} {resolved['path']:50s}")
        print(f"    expected={resolved['expected_status']}  body={str(body)[:150]}")

    print()
    print('--- Ejecutando ---')
    result = await runner.run_audit(sample_tcs, run_id='debug-fixtures-001', resume=False)
    print()
    print(f'PASS: {result.passed}/{result.total_cps}')
    for r in result.results:
        if r.status.value == 'fail':
            print(f'  {r.cp_id:14s} HTTP {r.http_code}  {(r.actual or "")[:200]}')

asyncio.run(run())
