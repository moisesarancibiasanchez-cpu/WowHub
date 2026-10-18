"""Auditoria V134.2 por chunks con pausas para evitar rate-limit"""
import sys, asyncio, time
sys.path.insert(0, '.')
for mod in list(sys.modules.keys()):
    if 'cp_index' in mod or 'cp_runner' in mod or 'hu_endpoint_map' in mod or 'fixtures' in mod or 'runner' in mod:
        del sys.modules[mod]
from runner.cp_index import CPIndex
from runner.cp_runner import CPRunner, TestCaseResult
from collections import Counter

idx = CPIndex(doc_path=r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').load(force_reparse=True)
all_cps = idx.all()
test_cases = [cp.to_http_test() for cp in all_cps]
print(f'Total CPs: {len(test_cases)}')

CHUNK_SIZE = 60
PAUSE_BETWEEN = 60  # segundos

async def run_chunked():
    runner = CPRunner(
        max_concurrent=8, timeout=8.0, max_retries=1,
        use_hu_mapping=True,
        auth_email="maria@cafenorte.cl", auth_password="demo1234",
    )

    # Hacer login UNA VEZ al inicio
    token = await runner.login()
    print(f'Login OK: {bool(token)}')
    print()

    all_results = []
    chunks = [test_cases[i:i + CHUNK_SIZE] for i in range(0, len(test_cases), CHUNK_SIZE)]
    n_chunks = len(chunks)
    print(f'Total chunks: {n_chunks} (size={CHUNK_SIZE}, pausa entre={PAUSE_BETWEEN}s)')
    print('=' * 60)

    t_start = time.time()
    for i, chunk in enumerate(chunks, 1):
        chunk_start = time.time()
        run_id = f'chunked-{i:03d}'
        result = await runner.run_audit(chunk, run_id=run_id, resume=False, auth_token=token)
        chunk_pass = result.passed
        chunk_fail = result.failed
        chunk_total = result.total_cps
        chunk_dur = time.time() - chunk_start

        print(f'Chunk {i}/{n_chunks} ({chunk_total} CPs):  PASS={chunk_pass}  FAIL={chunk_fail}  dur={chunk_dur:.1f}s')

        # Mostrar distribucion de fallos del chunk
        fail_codes = Counter()
        for r in result.results:
            if r.status.value == 'fail' and r.http_code:
                fail_codes[r.http_code] += 1
        if fail_codes:
            top = ', '.join(f'HTTP {c}: {n}' for c, n in sorted(fail_codes.items(), key=lambda x: -x[1])[:5])
            print(f'  Fallos: {top}')

        all_results.extend(result.results)

        # Pausa entre chunks (excepto el ultimo)
        if i < n_chunks:
            print(f'  Pausa {PAUSE_BETWEEN}s...')
            await asyncio.sleep(PAUSE_BETWEEN)
            print()

    total_dur = time.time() - t_start
    print()
    print('=' * 60)
    print('AUDITORIA V134.2 COMPLETA (chunked)')
    print('=' * 60)
    total = len(all_results)
    passed = sum(1 for r in all_results if r.status.value == 'pass')
    failed = sum(1 for r in all_results if r.status.value == 'fail')
    errors = sum(1 for r in all_results if r.status.value == 'error')
    coverage = round(passed / max(total, 1) * 100, 1)
    print(f'Total:     {total}')
    print(f'PASS:      {passed} ({coverage}%)')
    print(f'FAIL:      {failed}')
    print(f'ERROR:     {errors}')
    print(f'Duration:  {total_dur:.1f}s ({total_dur/60:.1f} min)')
    print()

    # Distribucion final
    pass_codes = Counter()
    fail_codes = Counter()
    for r in all_results:
        if r.status.value == 'pass' and r.http_code:
            pass_codes[r.http_code] += 1
        elif r.status.value == 'fail' and r.http_code:
            fail_codes[r.http_code] += 1
        elif r.status.value == 'error':
            fail_codes['network'] += 1

    print('PASS por HTTP code:')
    for code, n in sorted(pass_codes.items(), key=lambda x: -x[1]):
        print(f'  HTTP {code}: {n}')
    print()
    print('FAIL por HTTP code:')
    for code, n in sorted(fail_codes.items(), key=lambda x: -x[1]):
        print(f'  HTTP {code}: {n}')

asyncio.run(run_chunked())
