"""Copia os CSVs gerados pelo build.py para data/ do site, sem dados internos.
Uso: python3 atualizar_dados.py <pasta_saida_do_build> <pasta_do_repositorio> "<DD/MM/AAAA HH:MM>" """
import csv, os, shutil, sys
saida, repo, quando = sys.argv[1], sys.argv[2], sys.argv[3]
dst = os.path.join(repo, 'data'); os.makedirs(dst, exist_ok=True)
for n in ['empenhos', 'movimento', 'liquidacoes', 'saldo_fontes', 'dotacoes']:
    shutil.copy(os.path.join(saida, n + '.csv'), os.path.join(dst, n + '.csv'))
if os.path.exists(os.path.join(saida, 'notas.csv')):
    shutil.copy(os.path.join(saida, 'notas.csv'), os.path.join(dst, 'notas.csv'))
rows = list(csv.DictReader(open(os.path.join(saida, 'itens.csv'), encoding='utf-8')))
campos = [k for k in (rows[0].keys() if rows else []) if k != 'qtd_liquidada_equiplano']
with open(os.path.join(dst, 'itens.csv'), 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore', lineterminator='\n'); w.writeheader(); w.writerows(rows)
open(os.path.join(dst, 'atualizado.txt'), 'w').write(quando + '\n')
print('ok', len(rows), 'itens')
