"""MODO DESENVOLVEDOR (só para a prévia): lê no portal o "Requisição Nº" (requisição de empenho) de todos os
empenhos do ano e grava previa/requisicao_empenho.csv. Não mexe em data/ nem no site oficial.

Uso: python ferramentas/previa_req_empenho.py [ano]
"""
import csv, os, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'motor'))
import coleta  # noqa: E402

ano = int(sys.argv[1]) if len(sys.argv) > 1 else datetime.now().year
meses = range(1, (datetime.now().month if ano == datetime.now().year else 12) + 1)
dias = []
for m in meses:
    for r in coleta.tabelas_mes(ano, m)['emp']:
        c = r['c'] + [''] * 3
        if coleta.re.match(r'^\d\d/\d\d/\d{4}$', c[1]) and r.get('a'):
            dias.append((coleta.iso(c[1]), r['a']))
print(f'{len(dias)} dias com empenho em {ano}')

erros = []
def um(x):
    try:
        return [(e['n'], e.get('req', ''), x[0]) for e in coleta.ler_empenhos(coleta.pdf_texto(x[1], True))]
    except Exception as ex:  # um dia com erro não para o resto
        erros.append(f'{x[0]}: {ex}'); return []

with ThreadPoolExecutor(5) as ex:
    linhas = [l for ls in ex.map(um, dias) for l in ls]
vistos = {}
for n, req, d in linhas:
    if n not in vistos or (req and not vistos[n][0]):
        vistos[n] = (req, d)
saida = os.path.join(os.path.dirname(__file__), '..', 'previa', 'requisicao_empenho.csv')
os.makedirs(os.path.dirname(saida), exist_ok=True)
with open(saida, 'w', encoding='utf-8', newline='') as f:
    w = csv.writer(f); w.writerow(['empenho', 'requisicao_empenho', 'data'])
    for n, (req, d) in sorted(vistos.items(), key=lambda kv: int(kv[0])):
        w.writerow([n, req, d])
print(f'{len(vistos)} empenhos, {sum(1 for v in vistos.values() if v[0])} com requisição de empenho; {len(erros)} dias com erro')
for e in erros[:20]:
    print('  erro', e)
