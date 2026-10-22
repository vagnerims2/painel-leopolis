#!/usr/bin/env python3
"""Painel de Empenhos Leópolis — junta a coleta nova ao histórico e gera os CSVs do painel.

Uso: python3 build.py MASTER.json COLETA.json SAIDA_DIR [itens_requisicoes.csv]
- MASTER.json pode não existir (primeira carga); é reescrito com o histórico atualizado.
"""
import csv, json, os, re, sys, unicodedata, statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

master_p, coleta_p, out = sys.argv[1], sys.argv[2], sys.argv[3]
req_p = sys.argv[4] if len(sys.argv) > 4 else None
os.makedirs(out, exist_ok=True)
M = json.load(open(master_p, encoding='utf-8')) if os.path.exists(master_p) else {'empenhos': {}, 'liquidacoes': {}, 'pagamentos': {}}
N = json.load(open(coleta_p, encoding='utf-8'))

# ---------- merge ----------
# requisição de empenho dos empenhos lidos antes de o robô guardar esse campo (levantada no portal em 21/10/2026)
_sem_req = {}
for _p in (os.path.join(os.path.dirname(os.path.abspath(master_p)), '..', 'semente', 'requisicao_empenho.csv'),
           os.path.join(os.path.dirname(os.path.abspath(__file__)), 'semente', 'requisicao_empenho.csv')):
    if os.path.exists(_p):
        _sem_req = {r['empenho']: r['requisicao_empenho'] for r in csv.DictReader(open(_p, encoding='utf-8'))}; break
for _n, _e in M['empenhos'].items():
    if 'req' not in _e and _n in _sem_req: _e['req'] = _sem_req[_n]
for e in N['empenhos']:
    old = M['empenhos'].get(e['n'])
    if old and not e['items'] and old.get('items'): e['items'] = old['items']
    if old and not e.get('req') and old.get('req'): e['req'] = old['req']
    e['col'] = N['gerado'][:10]  # data em que o relatório deste empenho foi lido
    M['empenhos'][e['n']] = e
for l in N['liquidacoes']:
    o = M['liquidacoes'].get(l['n'])
    if o and o.get('nf') and l.get('nf') and l['nf'] not in o['nf']: l['nf'] = o['nf'] + '; ' + l['nf']
    M['liquidacoes'][l['n']] = l
for p in N['pagamentos']: M['pagamentos'][p['n']] = p
M['mov'], M['saldo'], M['fontes'] = N['mov'], N['saldo'], N['fontes']
M.setdefault('docs', {})
for x in N.get('docs', []):
    M['docs'][x.get('id') or f"L{x['l']}-{x['nr']}-{x['v']}"] = x
M['atualizado'] = N['gerado']
json.dump(M, open(master_p, 'w', encoding='utf-8'), ensure_ascii=False)

hoje = date.fromisoformat(N['gerado'][:10])
E, L, P = M['empenhos'], M['liquidacoes'], M['pagamentos']

def norm(s): return unicodedata.normalize('NFD', s or '').encode('ascii', 'ignore').decode().upper().strip()
def nforn(s): return re.sub(r'\s+', ' ', norm(re.sub(r'\s*\d{11}$', '', re.sub(r'^[\d.]+\s+', '', s or ''))))[:40].strip()
def modal(l):
    m = re.sub(r'\s*\d+/\d{4}\s*$', '', l or ''); m = re.sub(r'\s*-\s*Uso até.*$', '', m, flags=re.I).strip()
    return 'Pregão eletrônico' if re.match(r'^Pregão\s*-\s*Eletrônico', m, re.I) else (m or 'Não informado')
def licit(l):
    n = re.search(r'(\d+/\d{4})\s*$', l or ''); return (modal(l) + (' ' + n[1] if n else '')).strip()
def sec(s): return re.sub(r'^SECRETARIA MUNIC(IPAL)?\.? DE ', '', s or '', flags=re.I).strip()
def days(a, b): return (date.fromisoformat(b) - date.fromisoformat(a)).days

# fonte: dotação -> código, código -> nome
fonte_nome = {f['cod']: f['fonte'] for f in M['fontes']}
dot_fonte = {}
# o nº da dotação muda de um ano para outro: só vale a liquidação cuja fonte tem o mesmo nome da do empenho de 2026
_fd_dot = {e['dot']: norm(e.get('fdesc', ''))[:40] for e in E.values() if e.get('dot')}
for x in L.values():
    if x.get('dot') and x.get('fcod') and x.get('fdesc') and _fd_dot.get(x['dot']) == norm(x['fdesc'])[:40]: dot_fonte[x['dot']] = x['fcod']
por_nome = defaultdict(set)
for c, nm in fonte_nome.items(): por_nome[norm(nm.split(' - ', 1)[-1])[:40]].add(c)
for x in list(L.values()):
    if x.get('fcod') and x.get('fdesc'): por_nome[norm(x['fdesc'])[:40]].add(x['fcod'])
def fonte_de(e):
    c = dot_fonte.get(e.get('dot', ''))
    if c is None:
        cs = por_nome.get(norm(e.get('fdesc', ''))[:40], set())
        if len(cs) == 1: c = next(iter(cs))
    if c is not None: return fonte_nome.get(c, f"{c} - {e.get('fdesc', '')}".strip(' -'))
    return e.get('fdesc', '')

# ---------- código completo da despesa (8 níveis, ex.: 3.3.90.14.14.01) ----------
# o relatório de pagamento traz o código completo; o de empenho só até o 6º nível (3.3.90.14.14.0)
_cod_emp, _cod_desc = {}, defaultdict(lambda: defaultdict(int))
for p in P.values():
    e = E.get(p.get('e'))
    if p.get('el') and e and (not p.get('ano') or p['ano'] == str(hoje.year)) and p['el'].startswith(e['el'][:-1]):
        _cod_emp[e['n']] = p['el']; _cod_desc[(e['el'], norm(e.get('eld', '')))][p['el']] += 1
def codigo_de(e):
    c = _cod_emp.get(e['n'])
    if c: return c
    op = _cod_desc.get((e['el'], norm(e.get('eld', ''))))
    return max(op, key=op.get) if op else e['el']

# ---------- por empenho ----------
liq_e, pag_e = defaultdict(list), defaultdict(list)
# o empenho de cada liquidação: o relatório do empenho lista as liquidações dele e é a fonte mais segura
# (coletas antigas pegavam o nº da ordem de compra no lugar do empenho em parte das liquidações)
_dono = {}
for _n, _e in E.items():
    for _m in _e['movs']:
        if _m['k'].startswith('Liquida'): _dono.setdefault(_m['n'], _n)
liq_relink = 0
for l in L.values():
    d = _dono.get(l['n'])
    if d and d != l['e']: l['e'] = d; liq_relink += 1
# liquidações e pagamentos de restos a pagar (empenhos de anos anteriores) vêm com o mesmo número de
# empenhos de 2026; só contam para o empenho de 2026 quando a dotação é a mesma
def _mesma_dot(x):
    e = E.get(x['e']); return bool(e) and (not x.get('dot') or not e.get('dot') or x['dot'] == e['dot'])
def _do_empenho(l):
    """a liquidação é deste empenho de 2026? (senão é de restos a pagar com o mesmo número)"""
    e = E.get(l['e'])
    if not e: return False
    if _dono.get(l['n']) == l['e']: return True              # está no relatório do empenho
    # o relatório do empenho já era posterior e não a lista → é de restos a pagar. Só vale para liquidação com
    # 8+ dias de antecedência: o portal às vezes publica liquidações com alguns dias de atraso (ex.: 8693/8860)
    col = e.get('col', '')[:10]
    if col and l['d'] < col and (date.fromisoformat(col) - date.fromisoformat(l['d'])).days > 7: return False
    return _mesma_dot(l)                                        # liquidação mais nova que o relatório: confere a dotação
liq_ok = set()
for l in L.values():
    if _do_empenho(l): liq_e[l['e']].append(l); liq_ok.add(l['n'])
for p in P.values():
    if p.get('ano') and p['ano'] != str(hoje.year): continue   # pagamento de restos a pagar
    if (p.get('l') in liq_ok) if p.get('l') else _mesma_dot(p): pag_e[p['e']].append(p)
# nomes de produto completos: coletas antigas guardavam só a última linha do nome (ex.: "MTR" em vez de
# "PAPEL HIGIENICO FOLHA DUPLA - 30 MTR"); completa pelo relatório de requisições do Equiplano quando houver
_req0 = defaultdict(list)
if req_p and os.path.exists(req_p):
    for x in csv.DictReader(open(req_p, encoding='utf-8')):
        for en in re.split(r'\s*,\s*', x['empenhos']):
            if en: _req0[en].append(x)
nomes_corrigidos = 0
for n, e in E.items():
    for i in e['items']:
        b = norm(i['p'])
        for x in _req0.get(n, []):
            try: vu = float(x['valor_unitario'] or 0)
            except ValueError: continue
            a = norm(x['produto'])
            if abs(vu - float(i['vu'] or 0)) < 0.006 and b and a != b and b in a:
                i['p'] = x['produto']; nomes_corrigidos += 1; break
TIPOS_EST = (('Estorno de Empenho', 'Empenho anulado'), ('Anula', 'Empenho anulado'), ('Estorno de Liquida', 'Liquidação estornada'), ('Estorno de Pagamento', 'Pagamento estornado'))
def _estornos(e, pags):
    """[(descrição, valor, data)] dos estornos e anulações deste empenho"""
    out = []
    for m in e['movs']:
        for chave, nome in TIPOS_EST:
            if m['k'].lower().startswith(chave.lower()):
                out.append((nome, abs(m['v']), m['d'])); break
    if not any(x[0] == 'Pagamento estornado' for x in out):
        out += [('Pagamento estornado', p['v'], p['d']) for p in pags if p.get('est')]
    return out
def _fmt_est(lst):
    br = lambda v: f"R$ {v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    return '; '.join(f"{nome} {br(v)}" + (f" em {'/'.join(reversed(d.split('-')))}" if d else '') for nome, v, d in sorted(lst, key=lambda x: x[2] or '9'))
# itens que não batem com o valor do empenho (o portal às vezes devolve a página de itens de outro empenho):
# saem dos relatórios de produto e o dia do empenho é relido nas próximas rodadas
def _itens_ok(e):
    its = e.get('items') or []
    if not its: return True
    s, v = sum(float(i.get('vt') or 0) for i in its), float(e.get('v') or 0)
    return abs(s - v) <= max(0.05, 0.005 * v)
itens_suspeitos = {n for n, e in E.items() if not _itens_ok(e)}
rows = {}
for n, e in E.items():
    anul = sum(abs(m['v']) for m in e['movs'] if re.match(r'Estorno de Empenho|Anula', m['k'], re.I))
    liqs = {l['n']: (l['d'], l['v']) for l in liq_e[n]}
    for m in e['movs']:
        if m['k'].startswith('Liquida') and m['n'] not in liqs: liqs[m['n']] = (m['d'], m['v'])
    liq_est = sum(abs(m['v']) for m in e['movs'] if re.match(r'Estorno de Liquida', m['k'], re.I))
    liquidado = max(0.0, sum(v for _, v in liqs.values()) - liq_est)
    pago_bruto = sum(p['v'] for p in pag_e[n] if not p.get('est'))
    est_pag = max(sum(p['v'] for p in pag_e[n] if p.get('est')), sum(abs(m['v']) for m in e['movs'] if re.match(r'Estorno de Pagamento', m['k'], re.I)))
    pago = max(0.0, pago_bruto - est_pag)
    d1 = min((d for d, _ in liqs.values()), default='')
    dp = max((p['d'] for p in pag_e[n]), default='')
    prods = [] if n in itens_suspeitos else list(dict.fromkeys(i['p'] for i in e['items']))
    rows[n] = dict(empenho=n, data=e['d'], tipo=e['tipo'], fornecedor=re.sub(r'^[\d.]+\s+', '', e['forn']), secretaria=sec(e['sec']),
        licitacao=licit(e['lic']), modalidade=modal(e['lic']), contrato=e.get('contrato', ''), natureza='.'.join(e['el'].split('.')[:4]), subelemento=codigo_de(e),
        tipo_despesa=e['eld'], dotacao=e.get('dot', ''), fonte=fonte_de(e), valor=round(e['v'], 2), anulado=round(anul, 2), liquidado=round(liquidado, 2), pago=round(pago, 2),
        primeira_liquidacao=d1, ultimo_pagamento=dp, requisicao_empenho=e.get('req', ''), produtos=('; '.join(prods) or e.get('hist', ''))[:180], _g=(e['d'], nforn(e['forn'])),
        _anul_movs=round(anul, 2), _est=_estornos(e, pag_e[n]))

# reconcilia com o saldo a pagar oficial (fornecedor + data): anulações posteriores
saldo_g = defaultdict(float)
for s in M['saldo']: saldo_g[(s['d'], nforn(s['f']))] += s['v']
grp = defaultdict(list)
for r in rows.values(): grp[r['_g']].append(r)
diverg = []
for g, rs in grp.items():
    calc = sum(max(0, r['valor'] - r['anulado'] - r['pago']) for r in rs); S = saldo_g.get(g, 0.0)
    extra = calc - S
    if extra > 0.5:
        for r in sorted(rs, key=lambda r: -(r['valor'] - r['anulado'] - r['liquidado'])):
            cab = max(0, r['valor'] - r['anulado'] - max(r['liquidado'], r['pago']))
            t = min(cab, extra); r['anulado'] = round(r['anulado'] + t, 2); extra -= t
            if extra <= 0.5: break
        if extra > 0.5:  # liquidado mas não pago acima do saldo: provável pagamento não lido
            for r in rs:
                cab = max(0, r['valor'] - r['anulado'] - r['pago']); t = min(cab, extra); r['pago'] = round(r['pago'] + t, 2); extra -= t
    elif extra < -0.5: diverg.append((g, round(-extra, 2)))
    for r in rs: r['grupo_saldo'] = f"{g[0]} {g[1]}" if S > 0 else ''; r['saldo_grupo_portal'] = round(S, 2)

for r in rows.values():
    est = list(r.pop('_est')); a0 = r.pop('_anul_movs')
    if r['anulado'] - a0 > 0.5:   # anulação vista pelo saldo do portal, sem a nota no relatório do empenho
        est.append(('Empenho anulado', round(r['anulado'] - a0, 2), ''))
    r['estornos'] = _fmt_est(est); r['valor_estornado'] = round(sum(v for _, v, _ in est), 2)
    liquido = r['valor'] - r['anulado']
    r['falta_liquidar'] = round(max(0, liquido - r['liquidado']), 2)
    r['liquidado_nao_pago'] = round(max(0, min(r['liquidado'], liquido) - r['pago']), 2)
    r['saldo_a_pagar'] = round(r['falta_liquidar'] + r['liquidado_nao_pago'], 2)
    r['situacao'] = 'Anulado' if liquido < 0.01 else ('Pago' if r['saldo_a_pagar'] < 0.01 else ('Falta liquidar' if r['falta_liquidar'] >= 0.01 and r['liquidado'] < 0.01 else ('Liquidado em parte' if r['falta_liquidar'] >= 0.01 else 'Liquidado, a pagar')))
    r['dias'] = days(r['data'], hoje.isoformat())
    r['dias_ate_liquidar'] = days(r['data'], r['primeira_liquidacao']) if r['primeira_liquidacao'] else ''
    r['dias_ate_pagar'] = days(r['data'], r['ultimo_pagamento']) if r['ultimo_pagamento'] and r['situacao'] == 'Pago' else ''
    r.pop('_g')

cols = ['empenho', 'data', 'tipo', 'fornecedor', 'secretaria', 'licitacao', 'modalidade', 'contrato', 'natureza', 'subelemento', 'tipo_despesa', 'dotacao', 'fonte',
        'valor', 'anulado', 'liquidado', 'pago', 'falta_liquidar', 'liquidado_nao_pago', 'saldo_a_pagar', 'situacao', 'dias', 'primeira_liquidacao', 'dias_ate_liquidar',
        'ultimo_pagamento', 'dias_ate_pagar', 'grupo_saldo', 'saldo_grupo_portal', 'produtos', 'estornos', 'valor_estornado', 'requisicao_empenho']
R = sorted(rows.values(), key=lambda r: (r['data'], int(r['empenho'])), reverse=True)
def wcsv(name, rs, cs):
    with open(os.path.join(out, name), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cs, extrasaction='ignore'); w.writeheader(); w.writerows(rs)
wcsv('empenhos.csv', R, cols)

# ---------- itens ----------
_RE_MED = re.compile(r'(\d+(?:[.,]\d+)?)\s*(ML|LITROS?|LTS?|L|KG|GRAMAS?|GRS?|G|MG|MCG)\b')
_RE_QTD = re.compile(r'\b(?:C/|COM|CONTENDO|CX\.?\s*(?:C/|COM)?)\s*(\d{1,5})\s*(UN|UND|UNID|UNIDADES|FOLHAS|FLS|ROLOS|PARES|PCS?|PECAS|SACHES?|ENVELOPES|COMPRIMIDOS|CAPSULAS|TIRAS|FRASCOS)\b')
def medidas(*textos):
    """medidas de embalagem citadas no nome/descrição (5 L, 800 ml, 500 g, caixa c/ 100): o mesmo produto em embalagens
    diferentes não pode ser comparado pelo preço unitário"""
    t = re.sub(r'\s+', ' ', norm(' '.join(x or '' for x in textos)))
    m = {}
    for n, u in _RE_MED.findall(t):
        try:
            v = float(n.replace('.', '').replace(',', '.')) if re.match(r'^\d{1,3}(\.\d{3})+$', n) else float(n.replace(',', '.'))
        except ValueError:
            continue
        u = {'LITRO': 'L', 'LITROS': 'L', 'LT': 'L', 'LTS': 'L', 'GRAMA': 'G', 'GRAMAS': 'G', 'GR': 'G', 'GRS': 'G'}.get(u, u)
        if u == 'L': v, u = v * 1000, 'ML'
        if u == 'KG': v, u = v * 1000, 'G'
        if v > 0: m[f'{v:g}{u}'] = (v, u)
    for n, u in _RE_QTD.findall(t):
        if int(n) > 1: m[f'X{int(n)}'] = (int(n), 'X')
    rot = []
    for k, (v, u) in sorted(m.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        if u == 'ML': rot.append(f'{v / 1000:g} L'.replace('.', ',') if v >= 1000 else f'{v:g} ml')
        elif u == 'G': rot.append(f'{v / 1000:g} kg'.replace('.', ',') if v >= 1000 else f'{v:g} g')
        elif u == 'X': rot.append(f'c/ {v:g}')
        else: rot.append(f'{v:g} {u.lower()}')
    return ' '.join(sorted(m)), ' · '.join(rot)
_RE_EMB = re.compile(r'\b(GAL[AÃ]O|REFIL|FRASCO|BOMBONA|BALDE|LATA|PACOTE|PCT|CAIXA|CX|FARDO|SACO|ROLO|POTE|TUBO|AMPOLA|BISNAGA|GARRAFA|SACHE|ENVELOPE|BOLSA|EMBALAGEM)\b[^,;]{0,25}?\d+(?:[.,]\d+)?\s*(?:ML|LITROS?|LTS?|L|KG|GRAMAS?|GRS?|G|UN|UNIDADES|FOLHAS)?\b', re.I)
def rotulo_embalagem(nome, desc):
    """rótulo curto da embalagem para mostrar na tela: medidas do nome do produto ou de trechos como 'GALÃO 5 L'"""
    trechos = [nome or ''] + [x.group(0) for x in _RE_EMB.finditer(norm(desc or ''))]
    return medidas(*trechos)[1]

req = defaultdict(list)
if req_p and os.path.exists(req_p):
    for x in csv.DictReader(open(req_p, encoding='utf-8')):
        for en in re.split(r'\s*,\s*', x['empenhos']):
            if en: req[en].append(x)
itens = []
for n, e in E.items():
    r = rows[n]
    if n in itens_suspeitos: continue
    for k, i in enumerate(e['items']):
        q_liq = ''
        for x in req.get(n, []):
            a, b = norm(x['produto']), norm(i['p'])
            if a[:18] == b[:18] or a.startswith(b) or b.startswith(a): q_liq = x['qtd_liquidada']; break
        # chave de comparação de preço: código do catálogo (ou o nome) + unidade + medidas da embalagem.
        # Itens ainda não relidos com a descrição completa ficam sem chave (não entram na comparação).
        cmp_, emb = '', ''
        if i.get('det'):
            mk = medidas(i['p'], i.get('c', ''))[0]; emb = rotulo_embalagem(i['p'], i.get('c', ''))
            base = ('COD ' + i['cod']) if i.get('cod') else re.sub(r'[^A-Z0-9]+', ' ', norm(i['p'])).strip()
            cmp_ = f"{base}|{norm(i.get('u', ''))}|{mk}"
        itens.append(dict(chave=f"{n}-{k+1}", empenho=n, data=e['d'], fornecedor=r['fornecedor'], secretaria=r['secretaria'], licitacao=r['licitacao'],
            produto=i['p'], marca=i['m'], quantidade=i['q'], valor_unitario=round(i['vu'], 4), valor_total=round(i['vt'], 2), qtd_liquidada_equiplano=q_liq, situacao=r['situacao'],
            unidade=i.get('u', ''), codigo=i.get('cod', ''), embalagem=emb, comparar=cmp_, descricao=(i.get('c') or '')[:160]))
itens.sort(key=lambda x: (x['data'], int(x['empenho'])), reverse=True)
wcsv('itens.csv', itens, list(itens[0].keys()) if itens else ['chave'])

# ---------- pagamentos (um por linha, pela data do pagamento; inclui restos a pagar) ----------
ANO_ATUAL = max((e['d'] for e in E.values() if e.get('d')), default=str(date.today()))[:4]
pags = []
for p in P.values():
    r = rows.get(p.get('e')) if p.get('ano') == str(ANO_ATUAL) else None
    v = round(p['v'], 2) * (-1 if p.get('est') else 1)
    pags.append(dict(pagamento=p['n'], data=p['d'], empenho=p.get('e', ''), ano_empenho=p.get('ano', ''), liquidacao=p.get('l', ''),
        valor=v, estorno='Sim' if p.get('est') else '', fornecedor=(r['fornecedor'] if r else re.sub(r'^[\d./-]+\s+', '', p.get('forn', ''))),
        secretaria=(r['secretaria'] if r else sec(p.get('sec', ''))), fonte=p.get('fcod', ''), elemento=p.get('el', ''),
        historico=((r['produtos'] if r else p.get('hist', '')) or '')[:220]))
# estornos de pagamento: a nota de estorno não vem no relatório de pagamentos do dia, mas aparece no relatório do
# empenho. Entra como linha negativa na data do estorno, ligada ao pagamento estornado (mesmo valor, data anterior).
estornos_pag = 0
for n, e in E.items():
    if any(p.get('est') for p in pag_e[n]): continue
    usados = set()
    for m in sorted((m for m in e['movs'] if re.match(r'Estorno de Pagamento', m['k'], re.I)), key=lambda m: m['d']):
        v = abs(m['v'])
        orig = max((p for p in pag_e[n] if not p.get('est') and p['n'] not in usados and abs(p['v'] - v) < 0.01 and p['d'] <= m['d']),
                   key=lambda p: (p['d'], int(p['n'])), default=None)
        if orig: usados.add(orig['n'])
        r = rows[n]
        pags.append(dict(pagamento='', data=m['d'], empenho=n, ano_empenho=str(ANO_ATUAL), liquidacao=(orig or {}).get('l', ''), valor=-round(v, 2), estorno='Sim',
            estorna_pagamento=(orig or {}).get('n', ''), fornecedor=r['fornecedor'], secretaria=r['secretaria'], fonte=(orig or {}).get('fcod', ''),
            elemento=(orig or {}).get('el', ''), historico=(r['produtos'] or '')[:220]))
        estornos_pag += 1
pags.sort(key=lambda x: (x['data'], int(x['pagamento'] or 0)), reverse=True)
wcsv('pagamentos.csv', pags, ['pagamento', 'data', 'empenho', 'ano_empenho', 'liquidacao', 'valor', 'estorno', 'estorna_pagamento', 'fornecedor', 'secretaria', 'fonte', 'elemento', 'historico'])

# ---------- movimento diário ----------
mov = []
for d, m in sorted(M['mov'].items()):
    mov.append(dict(data=d, empenhado=round(m.get('emp', 0), 2), estornado=round(m.get('est', 0), 2), empenhado_liquido=round(m.get('emp', 0) - m.get('est', 0), 2),
        liquidado=round(m.get('liq', 0) - m.get('liqEst', 0) + m.get('liqRp', 0), 2), pago=round(m.get('pag', 0) - m.get('pagEst', 0) + m.get('pagRp', 0), 2)))
wcsv('movimento.csv', mov, ['data', 'empenhado', 'estornado', 'empenhado_liquido', 'liquidado', 'pago'])

# ---------- liquidações recentes (com documento fiscal) ----------
lim = (hoje - timedelta(days=45)).isoformat()
lr = []
for l in sorted(L.values(), key=lambda x: (x['d'], int(x['n'])), reverse=True):
    if l['d'] < lim: continue
    rp = not _do_empenho(l); r = {} if rp else rows.get(l['e'], {})
    lr.append(dict(liquidacao=l['n'], data=l['d'], empenho=(l['e'] + ' (restos a pagar)') if rp else l['e'], fornecedor=r.get('fornecedor', '') or ('Empenho de exercício anterior' if rp else ''), secretaria=r.get('secretaria', ''), tipo_despesa=r.get('tipo_despesa', ''),
        fonte=fonte_nome.get(l.get('fcod', ''), l.get('fdesc', '')), valor=round(l['v'], 2), documento=l.get('nf', ''), vencimento=l.get('venc', ''),
        pago='Sim' if any(p['l'] == l['n'] and not p.get('est') for p in pag_e[l['e']]) else 'Não'))
# estornos de liquidação (vêm só no relatório do empenho): linha negativa na data do estorno; a liquidação estornada
# (mesmo valor, data anterior) fica marcada como "Estornada" em vez de "A pagar"
estornos_liq = 0
por_n = {x['liquidacao']: x for x in lr}
for n, e in E.items():
    usados = set()
    for m in sorted((m for m in e['movs'] if re.match(r'Estorno de Liquida', m['k'], re.I)), key=lambda m: m['d']):
        if m['d'] < lim: continue
        v = abs(m['v'])
        orig = max((l for l in liq_e[n] if l['n'] not in usados and abs(l['v'] - v) < 0.01 and l['d'] <= m['d']), key=lambda l: (l['d'], int(l['n'])), default=None)
        if orig:
            usados.add(orig['n'])
            if orig['n'] in por_n: por_n[orig['n']]['pago'] = 'Estornada'
        r = rows.get(n, {})
        lr.append(dict(liquidacao=(orig or {}).get('n', ''), data=m['d'], empenho=n, fornecedor=r.get('fornecedor', ''), secretaria=r.get('secretaria', ''), tipo_despesa=r.get('tipo_despesa', ''),
            fonte=fonte_nome.get((orig or {}).get('fcod', ''), (orig or {}).get('fdesc', '')), valor=-round(v, 2), documento='Estorno da liquidação', vencimento='', pago='Estornada'))
        estornos_liq += 1
lr.sort(key=lambda x: (x['data'], int(x['liquidacao'] or 0)), reverse=True)
wcsv('liquidacoes.csv', lr, ['liquidacao', 'data', 'empenho', 'fornecedor', 'secretaria', 'tipo_despesa', 'fonte', 'valor', 'documento', 'vencimento', 'pago'])

# ---------- saldo por fonte (oficial) ----------
# ---------- documentos fiscais (link do PDF no portal e chave de acesso) ----------
dr = []
for x in M.get('docs', {}).values():
    l = L.get(x['l']) if x.get('ano') == str(hoje.year) else None
    emp = l['e'] if l and x['l'] in liq_ok else ''
    dr.append(dict(id=x['id'], liquidacao=x['l'], data_liquidacao=x['dl'], empenho=emp, fornecedor=x['f'], cpf_cnpj=x.get('doc', ''), tipo=x['tipo'], numero=x['nr'],
                   serie=x['serie'], data_documento=x['dd'], valor=round(x['v'], 2), chave=x['chave'], link=x.get('link', ''), restos_a_pagar='Sim' if x.get('ano') != str(hoje.year) else ''))
dr.sort(key=lambda r: (r['data_liquidacao'], int(r['liquidacao'] or 0) if str(r['liquidacao']).isdigit() else 0), reverse=True)
wcsv('notas.csv', dr, ['id', 'liquidacao', 'data_liquidacao', 'empenho', 'fornecedor', 'cpf_cnpj', 'tipo', 'numero', 'serie', 'data_documento', 'valor', 'chave', 'link', 'restos_a_pagar'])
wcsv('saldo_fontes.csv', sorted([dict(fonte=f['fonte'], codigo=f['cod'], saldo_a_pagar=round(f['v'], 2)) for f in M['fontes']], key=lambda x: -x['saldo_a_pagar']), ['fonte', 'codigo', 'saldo_a_pagar'])

# ---------- dotações: saldo atual e necessidade do mês ----------
mes_atual = hoje.strftime('%Y-%m'); ult6 = []
y, m = hoje.year, hoje.month
for _ in range(6):
    m -= 1
    if m == 0: y, m = y - 1, 12
    ult6.append(f"{y}-{m:02d}")
dots = defaultdict(list)
for e in E.values():
    if e.get('dot'): dots[e['dot']].append(e)
drows = []
for dot, es in dots.items():
    es.sort(key=lambda e: (e['d'], int(e['n'])))
    u = es[-1]; r = rows[u['n']]
    pm = defaultdict(float)
    for e in es: pm[e['d'][:7]] += e['v'] - sum(abs(x['v']) for x in e['movs'] if re.match(r'Estorno de Empenho', x['k'], re.I))
    meses_com = sum(1 for k in ult6 if pm.get(k, 0) > 0)
    vals = [pm.get(k, 0) for k in ult6]
    media = statistics.median(vals)  # mediana: compras pontuais grandes não distorcem
    corrente = r['natureza'].startswith('3.')
    no_mes = pm.get(mes_atual, 0)
    necessidade = max(0, media - no_mes)
    # anulações de empenhos desta dotação depois do último empenho devolvem saldo que o relatório ainda não mostra
    devolvido = sum(abs(x['v']) for e in es for x in e['movs'] if re.match(r'Estorno de Empenho|Anula', x['k'], re.I) and x['d'] > u['d'])
    saldo = u['sat'] + devolvido
    falta_mes = max(0, necessidade - saldo); sobra = max(0, saldo - necessidade)
    prox = max(0, media - sobra)
    drows.append(dict(dotacao=dot, secretaria=r['secretaria'], natureza=r['natureza'], subelemento=r['subelemento'], tipo_despesa=r['tipo_despesa'], fonte=r['fonte'],
        saldo_atual=round(saldo, 2), ultimo_empenho=u['n'], data_ultimo=u['d'], empenhado_ano=round(sum(pm.values()), 2), media_mensal=round(media, 2),
        meses_com_empenho=meses_com, empenhado_mes=round(no_mes, 2), recorrente='Sim' if meses_com >= 4 and corrente else 'Não',
        falta_fechar_mes=round(falta_mes, 2), precisa_proximo_mes=round(prox, 2), total_suplementar=round(falta_mes + prox, 2),
        meses=' | '.join(f"{k[5:]}/{k[2:4]}: {pm.get(k, 0):.0f}" for k in reversed(ult6))))
drows.sort(key=lambda x: (-x['total_suplementar'], x['secretaria']))
wcsv('dotacoes.csv', drows, list(drows[0].keys()) if drows else ['dotacao'])

# ---------- alertas (para notificar só o que é novo) ----------
parados = {}
for r in R:
    if r['tipo'] == 'Ordinário' and r['liquidado'] == 0 and r['saldo_a_pagar'] > 0 and r['dias'] >= 10:
        parados[r['empenho']] = dict(faixa=30 if r['dias'] >= 30 else 20 if r['dias'] >= 20 else 10, dias=r['dias'], fornecedor=r['fornecedor'], valor=r['saldo_a_pagar'], produto=r['produtos'][:60])
dot_mes = {d['dotacao']: dict(secretaria=d['secretaria'], tipo=d['tipo_despesa'], fonte=d['fonte'], falta=d['falta_fechar_mes'], proximo=d['precisa_proximo_mes'])
           for d in drows if d['recorrente'] == 'Sim' and d['falta_fechar_mes'] > 0}
alertas = dict(gerado=N['gerado'], parados=parados, dot_mes=dot_mes)
ant_p = os.path.join(os.path.dirname(os.path.abspath(master_p)), 'alertas.json')
ant = json.load(open(ant_p, encoding='utf-8')) if os.path.exists(ant_p) else {'parados': {}, 'dot_mes': {}}
novos_parados = [dict(empenho=k, **v) for k, v in parados.items() if ant['parados'].get(k, {}).get('faixa', 0) < v['faixa']]
novas_dot = [dict(dotacao=k, **v) for k, v in dot_mes.items() if k not in ant['dot_mes']]
json.dump(alertas, open(ant_p, 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(dict(novos_parados=sorted(novos_parados, key=lambda x: -x['dias']), novas_dotacoes=novas_dot,
               suplementar=[d for d in drows if d['recorrente'] == 'Sim' and d['total_suplementar'] > 0]),
          open(os.path.join(out, 'novidades.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------- resumo ----------
tot_saldo_portal = sum(s['v'] for s in M['saldo'])
calc_saldo = sum(r['saldo_a_pagar'] for r in R)
resumo = dict(estornos_pagamento=estornos_pag, estornos_liquidacao=estornos_liq, itens_suspeitos=len(itens_suspeitos),
    reler_itens=sorted({E[n]['d'] for n in itens_suspeitos if E[n].get('d')}), liquidacoes_religadas=liq_relink, nomes_corrigidos=nomes_corrigidos, gerado=N['gerado'], empenhos=len(R), itens=len(itens), liquidacoes_recentes=len(lr), dotacoes=len(drows),
    saldo_portal=round(tot_saldo_portal, 2), saldo_calculado=round(calc_saldo, 2), grupos_divergentes=len(diverg),
    empenhado_ano=round(sum(m['empenhado_liquido'] for m in mov), 2), empenhos_valor=round(sum(r['valor'] - r['anulado'] for r in R), 2),
    alertas_parados=len(parados), alertas_novos=len(novos_parados), dotacoes_nao_fecham_mes=len(dot_mes), dotacoes_novas=len(novas_dot))
json.dump(resumo, open(os.path.join(out, 'resumo.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps(resumo, ensure_ascii=False))
