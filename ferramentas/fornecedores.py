"""Cadastro de fornecedores (telefone e e-mail) para o painel, independente da requisição.

Junta o contato de cada fornecedor que aparece na planilha "Espelho Fornecedores" (data/planilha.json), pelo código do
fornecedor no Equiplano (ex.: 13868-1) e pelo nome. Fica guardado em data/fornecedores.json e só é atualizado, nunca
apagado: se o fornecedor sair da planilha, o contato continua. Vale o contato da requisição mais recente.
Também liga cada empenho do portal ao código do fornecedor, pela base do ano do Equiplano (requisição -> empenho).

Uso: python ferramentas/fornecedores.py [pasta data]
"""
import csv, json, os, re, sys, unicodedata
from datetime import datetime, timezone, timedelta

D = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data')
P = lambda n: os.path.join(D, n)


def nome_chave(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'^C[OÓ]DIGO NOME\s+\S+\s+', '', s)
    s = re.sub(r'^[\d./-]+\s+', '', s)               # CNPJ de MEI no começo do nome
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()[:28]


def dt(d):
    m = re.match(r'(\d\d)/(\d\d)/(\d{4})', d or '')
    return f'{m[3]}-{m[2]}-{m[1]}' if m else ''


def main():
    try:
        base = json.load(open(P('fornecedores.json'), encoding='utf-8'))
    except Exception:
        base = {'fornecedores': {}}
    F = base.get('fornecedores', {})
    linhas = json.load(open(P('planilha.json'), encoding='utf-8')).get('linhas', [])
    for l in sorted(linhas, key=lambda l: dt(l.get('d'))):
        if not (l.get('t') or l.get('em')) or not l.get('f'):
            continue
        k = l.get('c') or 'N:' + nome_chave(l['f'])
        x = F.setdefault(k, {'c': l.get('c', ''), 'nome': l['f'].strip()})
        x['nome'] = l['f'].strip()
        if l.get('t'): x['t'] = l['t']
        if l.get('em'): x['em'] = l['em'].strip()
        x['desde'] = dt(l.get('d')) or x.get('desde', '')
        x.setdefault('nomes', [])
        nk = nome_chave(l['f'])
        if nk not in x['nomes']: x['nomes'].append(nk)
    # código do fornecedor de cada empenho, pela base do ano (requisição de compra -> empenho)
    emp_cod = {}
    try:
        ano = json.load(open(P('requisicoes_ano.json'), encoding='utf-8'))['reqs']
        for q in ano.values():
            for m in q['m']:
                if m[0] == 'EM' and q.get('c'): emp_cod[m[1].lstrip('0')] = q['c']
            nk = nome_chave(q.get('f'))
            if q.get('c') in F and nk not in F[q['c']].setdefault('nomes', []): F[q['c']]['nomes'].append(nk)
    except Exception:
        pass
    por_nome = {}
    for k, x in F.items():
        for nk in x.get('nomes', []): por_nome.setdefault(nk, k)
    out = {'atualizado': datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M'),
           'fonte': 'Planilha "Espelho Fornecedores" (contato da requisição mais recente de cada fornecedor); empenho -> código pelo relatório do ano do Equiplano.',
           'fornecedores': F, 'por_nome': por_nome, 'empenho_codigo': emp_cod}
    json.dump(out, open(P('fornecedores.json'), 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'Fornecedores: {len(F)} com contato; {len(emp_cod)} empenhos ligados a código.')


if __name__ == '__main__':
    main()
