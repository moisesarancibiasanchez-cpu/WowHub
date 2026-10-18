"""Test del mapping HU -> endpoint"""
import sys
sys.path.insert(0, '.')
from runner.hu_endpoint_map import HU_ENDPOINTS, resolve_hu_endpoint, mapping_coverage
import re
from pathlib import Path

# 1. Listar HUs del documento
text = Path(r'..\WowHub_GIT\docs\TEST_CASES_V134_2.md').read_text(encoding='utf-8')
hus_doc = sorted(set(re.findall(r'^##\s+(HU_\d+)', text, re.MULTILINE)))

# 2. Cobertura del mapping
cov = mapping_coverage(hus_doc)
mapped_n = cov['mapped']
total_n = cov['total_hus']
pct = cov['coverage_pct']
unmapped = cov['unmapped']
print(f'Cobertura del mapping: {pct}% ({mapped_n}/{total_n} HUs)')
print(f'HUs sin mapear: {unmapped}')

# 3. Probar resolve_hu_endpoint para cada tipo
print()
print('Resolucion de endpoints (sample):')
for hu in ['HU_01', 'HU_03', 'HU_15', 'HU_17', 'HU_37', 'HU_49']:
    for t in ['F', 'S', 'N', 'R']:
        r = resolve_hu_endpoint(hu, t)
        method = r['method']
        path = r['path']
        status = r['expected_status']
        auth = r['requires_auth']
        print(f'  {hu:7s} type={t}  {method:5s} {path:55s} -> {status} (auth={auth})')
    print()
