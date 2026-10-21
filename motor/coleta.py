"""Coleta do Portal da Transparência de Leópolis (Equiplano) — versão Python do coleta.js.
Gera o mesmo JSON que o build.py usa.

Uso como módulo:  coletar(desde='2026-10-13', liq_desde='2026-10-13') -> dict
"""
import re, zlib, time, html, hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests
import urllib3

ORIGEM = 'https://leopolispr.equiplano.com.br:7300'
BASE = ORIGEM + '/transparencia/'
ENT = 300

SESSAO = requests.Session()
SESSAO.headers['User-Agent'] = 'Mozilla/5.0 (Painel de Empenhos Leopolis)'
_VERIFICA_SSL = True


def get(url, binario=False):
    """GET com 3 tentativas; se o certificado do portal falhar, tenta sem verificar (só leitura de dados públicos)."""
    global _VERIFICA_SSL
    for i in range(3):
        try:
            r = SESSAO.get(url, timeout=60, verify=_VERIFICA_SSL)
            r.raise_for_status()
            return r.content if binario else r.content.decode(r.encoding or 'utf-8', 'replace')
        except requests.exceptions.SSLError:
            if _VERIFICA_SSL:
                _VERIFICA_SSL = False
                urllib3.disable_warnings()
                continue
            raise
        except Exception:
            if i == 2:
                raise
            time.sleep(1.5)


# ---------- utilidades ----------
def num(s):
    s = str(s or '').strip()
    neg = (s.startswith('(') and s.endswith(')')) or s.startswith('-')
    t = re.sub(r'[()\-]', '', s).replace('.', '').replace(',', '.')
    try:
        v = float(t)
    except ValueError:
        return 0.0
    return -v if neg else v

def iso(d):
    return '-'.join(reversed(d.split('/')))

def is_num(s):
    return bool(re.match(r'^\(?-?[\d.]+,\d{2}\)?$', str(s).strip()))

def sem_cpf(t):
    return re.sub(r'\d{3}\.\d{3}\.\d{3}-\d{2}', '', t)


class _Tabela(HTMLParser):
    """Lê as linhas de <table>: texto das células e o primeiro link de cada linha."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.linhas, self._linha, self._cel, self._dentro_cel, self._link = [], None, [], False, None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self._linha, self._link = [], None
        elif tag in ('td', 'th') and self._linha is not None:
            self._dentro_cel, self._cel = True, []
        elif tag == 'a' and self._linha is not None and self._link is None:
            href = dict(attrs).get('href')
            if href:
                self._link = href
    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._linha is not None and self._dentro_cel:
            self._linha.append(re.sub(r'\s+', ' ', ''.join(self._cel)).strip()); self._dentro_cel = False
        elif tag == 'tr' and self._linha is not None:
            self.linhas.append({'c': self._linha, 'a': self._link}); self._linha = None
    def handle_data(self, data):
        if self._dentro_cel:
            self._cel.append(data)

def tabela(url):
    p = _Tabela(); p.feed(get(url))
    for l in p.linhas:
        if l['a']:
            l['a'] = urljoin(url, html.unescape(l['a']))
    return p.linhas


# ---------- PDF ----------
_RE_STREAM = re.compile(rb'[^d]stream\r?\n')
_RE_TOK = re.compile(r'1 0 0 1 (-?[\d.]+) (-?[\d.]+) Tm|/F\d+ ([\d.]+) Tf|\(((?:\\.|[^\\)])*)\)Tj')

def _inflar(b):
    d = zlib.decompressobj()
    try:
        return d.decompress(b).decode('latin1')
    except zlib.error:
        return ''

def pdf_texto(url, com_posicao=False):
    buf = get(url, binario=True); res = []
    for m in _RE_STREAM.finditer(buf):
        st = m.end(); ini = buf.rfind(b'<<', 0, m.start()); dic = buf[max(0, ini):m.start()]
        ml = re.search(rb'/Length\s+(\d+)', dic); n = int(ml.group(1)) if ml else 0
        if b'Flate' not in dic or b'Image' in dic:
            continue
        res.append(_inflar(buf[st:st + n]))
    raw = '\n'.join(res)
    desesc = lambda t: re.sub(r'\\([()\\])', r'\1', t)
    if com_posicao:
        T, x, f = [], 0.0, 0.0
        for mm in _RE_TOK.finditer(raw):
            if mm.group(1) is not None:
                x = float(mm.group(1))
            elif mm.group(3) is not None:
                f = float(mm.group(3))
            else:
                t = desesc(mm.group(4))
                if t:
                    T.append({'t': sem_cpf(t), 'x': x, 'f': f})
        return T
    toks = [desesc(t) for t in re.findall(r'\(((?:\\.|[^\\)])*)\)Tj', raw)]
    return sem_cpf(' ¦ '.join(t for t in toks if t))


# ---------- leitores dos relatórios ----------
def itens_pos(b):
    """itens do empenho com o nome completo do produto (o nome pode ocupar várias linhas: x = 40, fonte 8)"""
    b = [{**k, 't': k['t'].strip()} for k in b if k['t'].strip()]
    itens, nome, i = [], [], 0
    while i < len(b):
        k = b[i]
        if k['x'] == 40 and k['f'] == 8 and not is_num(k['t']):
            nome.append(k['t']); i += 1; continue
        if nome and 150 < k['x'] < 330 and not is_num(k['t']) and i + 3 < len(b) and is_num(b[i + 1]['t']) and is_num(b[i + 2]['t']) and is_num(b[i + 3]['t']):
            itens.append({'p': ' '.join(nome), 'm': k['t'], 'vu': num(b[i + 1]['t']), 'q': num(b[i + 2]['t']), 'vt': num(b[i + 3]['t'])}); i += 4; nome = []; continue
        if nome and is_num(k['t']) and i + 2 < len(b) and is_num(b[i + 1]['t']) and is_num(b[i + 2]['t']):
            itens.append({'p': ' '.join(nome), 'm': '', 'vu': num(k['t']), 'q': num(b[i + 1]['t']), 'vt': num(b[i + 2]['t'])}); i += 3; nome = []; continue
        nome = []; i += 1
    return itens

def _idx(tk, v):
    try:
        return tk.index(v)
    except ValueError:
        return -1

def ler_empenhos(T):
    t = ' ¦ '.join(k['t'] for k in T)
    # as páginas "NOTA DE ESTORNO DE EMPENHO" no fim do relatório não são empenhos do dia: corta o bloco nelas
    blocos, corta = [], False
    for i, k in enumerate(T):
        if k['t'] == 'EMPENHO' and i > 0:
            blocos.append([]); corta = False
        elif re.match(r'^NOTA DE (ESTORNO|ANULA)', k['t'].strip()):
            corta = True
        elif blocos and not corta:
            blocos[-1].append(k)
    out = {}
    for nb, b0 in enumerate(re.split(r'¦ EMPENHO ¦', t)[1:]):
        b = re.split(r'¦ NOTA DE (?:ESTORNO|ANULA)', b0)[0]
        tk = [s.strip() for s in b.split(' ¦ ')]
        iE = _idx(tk, 'Emitido em')
        if iE < 0 or iE + 1 >= len(tk):
            continue
        try:
            nE = str(int(tk[iE + 1]))
        except ValueError:
            continue
        iT = _idx(tk, 'Tipo')
        lic = ' '.join(x for x in (tk[:iT] if iT > 0 else []) if not re.match(r'^\d+$', x) or len(x) > 3)
        lic = re.sub(r'^\d+\s+', '', lic).strip()
        iA = _idx(tk, 'Aditivo'); contrato = tk[iA + 1] if iA >= 0 and iA + 1 < len(tk) and re.match(r'^\d+/\d{4}$', tk[iA + 1]) else ''
        iF = _idx(tk, 'Fornecedor')
        iEl = next((i for i, x in enumerate(tk) if re.match(r'^\d\.\d\.\d\d\.\d\d\.\d\d\.\d$', x)), -1)
        iUn = next((i for i, x in enumerate(tk) if re.match(r'^\d{2}\.\d{3}$', x)), -1)
        iDot = next((i for i, x in enumerate(tk) if iEl >= 0 and iEl < i <= iEl + 5 and re.match(r'^\d{6}$', x)), -1)
        def g(k):
            i = _idx(tk, k); return num(tk[i + 1]) if i >= 0 and i + 1 < len(tk) else 0
        movs = []
        for i in range(len(tk) - 3):
            if re.match(r'^\d{4,6}$', tk[i]) and re.match(r'^\d\d/\d\d/\d{4}$', tk[i + 1]) and is_num(tk[i + 2]) and re.match(r'^(Liquida|Estorno|Anula)', tk[i + 3]):
                movs.append({'n': str(int(tk[i])), 'd': iso(tk[i + 1]), 'v': num(tk[i + 2]), 'k': tk[i + 3]})
        itens = []; iP = _idx(tk, 'Valor Total')
        if iP >= 0:
            i = iP + 1
            while i < len(tk) - 4:
                if not is_num(tk[i]) and not is_num(tk[i + 1]) and is_num(tk[i + 2]) and is_num(tk[i + 3]) and is_num(tk[i + 4]):
                    itens.append({'p': tk[i], 'm': tk[i + 1], 'vu': num(tk[i + 2]), 'q': num(tk[i + 3]), 'vt': num(tk[i + 4])}); i += 5
                else:
                    i += 1
        itp = itens_pos(blocos[nb]) if nb < len(blocos) else []
        if len(itp) >= len(itens):
            itens = itp
        hist = ''; iD = _idx(tk, 'Data de')
        if iD >= 0:
            hist = ' '.join(x for x in tk[iD + 1:] if not re.match(r'^(Produto|Marca|UM|Valor|Quantidade|Valor Total|Município de Leópolis - PR)$', x)
                            and not re.match(r'^\d{4,6}$', x) and not re.match(r'^\d\d/\d\d/\d{4}$', x) and not is_num(x)
                            and not re.match(r'^(Liquida|Estorno|Anula)', x) and not re.match(r'^(CNPJ|RUA|Fone|Página)', x))[:200]
        at = lambda i: tk[i] if 0 <= i < len(tk) else ''
        e = {'n': nE, 'd': iso(at(iE + 3)), 'tipo': at(iE + 2), 'lic': lic, 'contrato': contrato, 'forn': at(iF + 1) if iF >= 0 else '',
             'sec': at(iUn - 1) if iUn > 0 else '', 'unid': (at(iUn) + ' ' + at(iUn + 1)) if iUn > 0 else '', 'prog': at(iUn + 3) if iUn > 0 else '',
             'el': at(iEl) if iEl >= 0 else '', 'eld': at(iEl + 1) if iEl >= 0 else '', 'dot': at(iDot) if iDot > 0 else '', 'fdesc': at(iDot + 1) if iDot > 0 else '',
             'sant': g('Saldo anterior'), 'v': g('Valor empenhado'), 'sat': g('Saldo atual'), 'movs': movs, 'items': itens, 'hist': hist,
             'req': str(int(at(iE + 4))) if re.match(r'^\d{1,7}$', at(iE + 4)) else ''}  # Requisição Nº = requisição de empenho
        if nE not in out:
            out[nE] = e
        else:
            o = out[nE]; o['items'] += itens
            for mv in movs:
                if not any(z['n'] == mv['n'] and z['k'] == mv['k'] for z in o['movs']):
                    o['movs'].append(mv)
            if not o['hist'] and hist:
                o['hist'] = hist
            if not o.get('req') and e['req']:
                o['req'] = e['req']
    return list(out.values())

def ler_liquidacoes(t, dia):
    out = []
    for b in re.split(r'¦ LIQUIDAÇÃO ¦', t)[1:]:
        tk = [s.strip() for s in b.split(' ¦ ')]
        iR, iE = _idx(tk, 'Requisição'), _idx(tk, 'Empenho Nº')
        if iR < 0 or iE < 0:
            continue
        iEl = next((i for i, x in enumerate(tk) if re.match(r'^\d\.\d\.\d\d\.\d\d\.\d\d\.\d$', x)), -1)
        iC, iD = _idx(tk, 'Classificação da despesa'), _idx(tk, 'Documentos fiscais')
        at = lambda i: tk[i] if 0 <= i < len(tk) else ''
        nf = ''
        if iD >= 0:
            z = tk[iD + 11:iD + 17]
            tipo = z[1] if len(z) > 1 else ''
            tipo = re.sub(r'^Nota Fiscal Eletrônica.*$', 'NF-e', tipo); tipo = re.sub(r'^Nota Fiscal de Serviço Eletrônica.*$', 'NFS-e', tipo)
            nf = tipo + (' nº ' + z[5] if len(z) > 5 and re.match(r'^\d+$', z[5]) else '')
        def g(k):
            i = _idx(tk, k); return num(tk[i + 1]) if i >= 0 and i + 1 < len(tk) else 0
        eN = at(iE + 2) if re.match(r'^\d{6}$', at(iE + 2)) else at(iE + 1)  # com ordem de compra vêm dois números: o segundo é o empenho
        try:
            n, e = str(int(at(iR + 1))), str(int(eN))
        except ValueError:
            continue
        iV = _idx(tk, 'Vencimento')
        out.append({'n': n, 'd': dia, 'e': e, 'v': g('Valor liquidado'), 'nf': nf, 'venc': iso(at(iV + 1)) if iV >= 0 else '',
                    'dot': at(iC + 1) if iC >= 0 and re.match(r'^\d{5,6}$', at(iC + 1)) else '',
                    'fcod': str(int(at(iEl + 2))) if iEl >= 0 and re.match(r'^\d{3,5}$', at(iEl + 2)) else '', 'fdesc': at(iEl + 3) if iEl >= 0 else ''})
    return out

def ler_pagamentos(t, dia):
    out = []
    for b in re.split(r'¦ PAGAMENTO ¦', t)[1:]:
        tk = [s.strip() for s in b.split(' ¦ ')]
        iP = _idx(tk, 'Previsão Nº')
        if iP < 0:
            continue
        nn = [x for x in tk if re.match(r'^\d+ / \d{4}$', x)]
        iEl = next((i for i, x in enumerate(tk) if re.match(r'^\d\.\d\.\d\d\.\d\d\.\d\d\.\d\d$', x)), -1)
        iV = _idx(tk, 'Valor'); dot = fcod = ''
        for i in range(len(tk) - 2):
            if re.match(r'^\d{6}$', tk[i]) and re.match(r'^\d{5}$', tk[i + 2]):
                dot, fcod = tk[i], str(int(tk[i + 2])); break
        try:
            n = str(int(tk[iP + 1]))
        except (ValueError, IndexError):
            continue
        out.append({'n': n, 'd': dia, 'e': str(int(nn[0].split(' / ')[0])) if nn else '', 'l': str(int(nn[1].split(' / ')[0])) if len(nn) > 1 else '',
                    'ano': nn[0].split(' / ')[1] if nn else '', 'v': num(tk[iV + 1]) if iV >= 0 and iV + 1 < len(tk) else 0,
                    'dot': dot, 'fcod': fcod, 'el': tk[iEl] if iEl >= 0 else '', 'est': bool(re.search('ESTORNO', ' '.join(tk[:3]), re.I))})
    return out


# ---------- coleta ----------
# ---------- documentos fiscais (notas) ----------
def post_json(url, dados):
    """POST (mesma consulta que a própria página do portal faz para paginar a tabela)"""
    global _VERIFICA_SSL
    for i in range(3):
        try:
            r = SESSAO.post(url, data=dados, timeout=180, verify=_VERIFICA_SSL)
            r.raise_for_status(); return r.json()
        except requests.exceptions.SSLError:
            if _VERIFICA_SSL:
                _VERIFICA_SSL = False; urllib3.disable_warnings(); continue
            raise
        except Exception:
            if i == 2: raise
            time.sleep(2)

def ler_documentos(desde, ate, ano=None, avisar=print):
    """Relação de documentos fiscais por data de liquidação: PDF anexado no portal, chave de acesso da NF-e e link da NFS-e."""
    ano = ano or datetime.now().year
    br = lambda d: '/'.join(reversed(d.split('-')))
    url = f'{BASE}relacaoDocumentosFiscais/listaRelacaoDocumentosFiscaisAjax'
    out, ini = [], datetime.fromisoformat(desde)
    fim_total = datetime.fromisoformat(ate)
    while ini <= fim_total:   # um mês por vez
        prox = (ini.replace(day=1) + timedelta(days=32)).replace(day=1)
        fim = min(fim_total, prox - timedelta(days=1))
        start = 0
        while True:
            d = post_json(url, {'formulario.tpFiltroRelacaoDocFiscais': '1', 'formulario.codEntidade': str(ENT), 'formulario.codFornecedor': '',
                                'formulario.idOrgao': '', 'formulario.idUnidade': '', 'formulario.dtInicial': br(ini.strftime('%Y-%m-%d')),
                                'formulario.dtFinal': br(fim.strftime('%Y-%m-%d')), 'draw': '1', 'start': str(start), 'length': '1000'})['paginacao']
            regs = d.get('registros') or []
            for x in regs:
                ch = (x.get('chaveAcessoNfe') or '').strip()
                tipo = re.sub(r'<[^>]+>', ' ', x.get('tpDocFiscal') or '').strip()
                tipo = 'NF-e' if ch and tipo.startswith('Chave') else re.sub(r'\s+', ' ', re.sub(r'\d{44}|\bLink\b', '', tipo)).strip()
                out.append({'id': str(x.get('idFornecedorDoc') or ''), 'f': x.get('nmFornecedor') or '', 'doc': x.get('docFornecedor') or '',
                            'ano': str(x.get('exercicoLiquidacao') or ''), 'l': str(x.get('nrLiquidacao') or ''), 'dl': (x.get('dtLiquidacao') or '')[:10],
                            'tipo': tipo, 'chave': ch, 'serie': x.get('serieDocFiscal') or '', 'nr': str(x.get('nrDocumento') or ''),
                            'dd': (x.get('dtDoc') or '')[:10], 'v': float(x.get('vlDoc') or 0), 'link': x.get('link') or ''})
            start += len(regs)
            if not regs or start >= int(d.get('quantidadeTotal') or 0):
                break
        ini = fim + timedelta(days=1)
    if len(out) > 200:
        avisar(f'{len(out)} documentos fiscais lidos de {br(desde)} a {br(ate)}.')
    return out

def _q(ano):
    return f'formulario.codEntidade={ENT}&formulario.exercicio={ano}'

def tabelas_mes(ano, m):
    """as três tabelas diárias do mês (empenhado, liquidado, pago)"""
    q = _q(ano); r = {}
    r['emp'] = tabela(f'{BASE}despesaEmpenhada/listaData?{q}&formulario.nrMes={m}')
    r['liq'] = tabela(f'{BASE}despesaLiquidada/listaData?{q}&formulario.nrMes={m}')
    r['pag'] = tabela(f'{BASE}despesaPaga/listaDespesaPagaPorDia?{q}&formulario.nrMes={m}')
    return r

def assinatura(ano=None):
    """um resumo das tabelas do mês atual e do anterior: se não mudou, não há lançamento novo no portal"""
    hoje = datetime.now(); ano = ano or hoje.year
    partes = []
    for m in sorted({max(1, hoje.month - 1), hoje.month}):
        t = tabelas_mes(ano, m)
        for k in ('emp', 'liq', 'pag'):
            partes += ['|'.join(l['c']) for l in t[k] if re.match(r'^\d\d/\d\d/\d{4}$', (l['c'] + ['', ''])[1])]
    fon = tabela(f'{BASE}despesaEmpenhadaAPagar/listaDespesaEmpenhadaAPagarPorAno?{_q(ano)}')
    partes += ['|'.join(l['c']) for l in fon]
    return hashlib.sha1('\n'.join(partes).encode('utf-8')).hexdigest(), '\n'.join(partes)

def coletar(desde, liq_desde=None, ano=None, avisar=print, mov_anterior=None, emp_conhecido=None,
            saldo_anterior=None, emp_por_liq_dia=None, dias_extra=None, docs_desde=None):
    """mov_anterior: o 'mov' da coleta passada; qualquer dia cujo total mudou no portal é relido,
    mesmo que seja anterior a 'desde' (o portal às vezes publica lançamentos com data retroativa)"""
    ano = ano or datetime.now().year; liq_desde = liq_desde or desde; mov_anterior = mov_anterior or {}
    meses = list(range(1, (datetime.now().month if datetime.now().year == ano else 12) + 1))
    res = {'gerado': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z'), 'params': {'desde': desde, 'liqDesde': liq_desde},
           'mov': {}, 'empenhos': [], 'liquidacoes': [], 'pagamentos': [], 'saldo': [], 'fontes': [], 'erros': []}
    dias = {'emp': [], 'liq': [], 'pag': []}
    avisar('Lendo as tabelas diárias…')
    with ThreadPoolExecutor(3) as ex:
        for t in ex.map(lambda m: tabelas_mes(ano, m), meses):
            for r in t['emp']:
                c = r['c'] + [''] * 6
                if re.match(r'^\d\d/\d\d/\d{4}$', c[1]):
                    d = iso(c[1]); res['mov'].setdefault(d, {}).update(emp=num(c[3]), est=num(c[4])); dias['emp'].append((d, r['a']))
            for r in t['liq']:
                c = r['c'] + [''] * 6
                if re.match(r'^\d\d/\d\d/\d{4}$', c[1]):
                    d = iso(c[1]); res['mov'].setdefault(d, {}).update(liq=num(c[2]), liqEst=num(c[3]), liqRp=num(c[4]) - num(c[5])); dias['liq'].append((d, r['a']))
            for r in t['pag']:
                c = r['c'] + [''] * 6
                if re.match(r'^\d\d/\d\d/\d{4}$', c[1]):
                    d = iso(c[1]); res['mov'].setdefault(d, {}).update(pag=num(c[2]), pagEst=num(c[3]), pagRp=num(c[4]) - num(c[5])); dias['pag'].append((d, r['a']))

    CAMPOS = {'emp': ('emp', 'est'), 'liq': ('liq', 'liqEst'), 'pag': ('pag', 'pagEst')}
    def mudou(tipo, d):
        if tipo == 'emp' and emp_conhecido is not None:
            # soma dos empenhos já guardados naquele dia x total do portal: diferença = empenho faltando
            return abs((res['mov'].get(d, {}).get('emp') or 0) - emp_conhecido.get(d, 0)) > 0.005
        if not mov_anterior:
            return False
        a, n = mov_anterior.get(d, {}), res['mov'].get(d, {})
        return any(abs((a.get(k) or 0) - (n.get(k) or 0)) > 0.005 for k in CAMPOS[tipo])
    def escolher(tipo, inicio):
        sel = [x for x in dias[tipo] if x[0] >= inicio or mudou(tipo, x[0]) or (tipo == 'emp' and x[0] in reler)]
        extra = sorted({x[0] for x in sel if x[0] < inicio})
        if extra:
            avisar(f"Dias anteriores com lançamento novo ({tipo}): {', '.join(extra)}")
        return sel

    def lote(lista, fn, nome):
        lista = [x for x in lista if x[1]]
        avisar(f'Lendo {len(lista)} relatórios de {nome}…')
        def um(x):
            try:
                return fn(x)
            except Exception as e:
                res['erros'].append(f'{x[0]} {nome}: {e}'); return []
        with ThreadPoolExecutor(5) as ex:
            return [r for rs in ex.map(um, lista) for r in rs]
    # saldo a pagar por data e credor: uma consulta por dia que teve empenho no ano
    datas = sorted({d for d, _ in dias['emp']})
    avisar(f'Lendo o saldo a pagar de {len(datas)} datas…')
    def saldo_dia(d):
        br = '/'.join(reversed(d.split('-')))
        out = []
        for r in tabela(f'{BASE}saldoCredoresAPagar/listaSaldoCredoresAPagarPorFornecedor?{_q(ano)}&formulario.data={br}'):
            c = r['c']
            if len(c) >= 4 and c[1] and not re.match(r'^(total|Fornecedor)$', c[1], re.I):
                v = num(c[3])
                if v > 0:
                    out.append({'d': d, 'f': re.sub(r'^[\d.]+\s+', '', re.sub(r'\s*\d{11}$', '', c[1])), 'v': v})
        return out
    def saldo_seguro(d):
        try:
            return saldo_dia(d)
        except Exception as e:
            res['erros'].append(f'{d} saldo: {e}'); return []
    with ThreadPoolExecutor(5) as ex:
        res['saldo'] = [r for rs in ex.map(saldo_seguro, datas) for r in rs]

    # estornos e anulações de empenhos antigos só aparecem relendo o relatório do dia do empenho:
    # relê os dias cujo saldo a pagar (credor + data) mudou e, quando há estorno de liquidação ou de
    # pagamento novo, os dias dos empenhos liquidados nos 30 dias anteriores
    reler = set(dias_extra or [])
    if saldo_anterior is not None:
        ant, nov = {}, {}
        for r in saldo_anterior: ant[(r['d'], r['f'])] = ant.get((r['d'], r['f']), 0) + r['v']
        for r in res['saldo']: nov[(r['d'], r['f'])] = nov.get((r['d'], r['f']), 0) + r['v']
        reler |= {k[0] for k in set(ant) | set(nov) if abs(ant.get(k, 0) - nov.get(k, 0)) > 0.005}
    if mov_anterior and emp_por_liq_dia:
        for d, n in res['mov'].items():
            a = mov_anterior.get(d, {})
            if any(abs((n.get(k) or 0) - (a.get(k) or 0)) > 0.005 for k in ('liqEst', 'pagEst')):
                fim = datetime.fromisoformat(d); ini = (fim - timedelta(days=30)).strftime('%Y-%m-%d')
                for ld, ds in emp_por_liq_dia.items():
                    if ini <= ld <= d: reler |= set(ds)
    reler -= {x[0] for x in dias['emp'] if x[0] >= desde}
    if reler:
        avisar(f"Relendo {len(reler)} dias de empenho por estorno/anulação/pagamento: {', '.join(sorted(reler)[:12])}{'…' if len(reler) > 12 else ''}")

    res['empenhos'] = lote(escolher('emp', desde), lambda x: ler_empenhos(pdf_texto(x[1], True)), 'empenho')
    liqs = lote(escolher('liq', liq_desde), lambda x: ler_liquidacoes(pdf_texto(x[1]), x[0]), 'liquidação')
    # a mesma liquidação pode aparecer em duas páginas (a segunda sem nota fiscal): junta mantendo os campos preenchidos
    junta = {}
    for l in liqs:
        o = junta.get(l['n'])
        if o is None:
            junta[l['n']] = l
        else:
            for k, v in l.items():
                if v and not o.get(k):
                    o[k] = v
    res['liquidacoes'] = list(junta.values())
    res['pagamentos'] = lote(escolher('pag', liq_desde), lambda x: ler_pagamentos(pdf_texto(x[1]), x[0]), 'pagamento')

    for r in tabela(f'{BASE}despesaEmpenhadaAPagar/listaDespesaEmpenhadaAPagarPorAno?{_q(ano)}'):
        c = r['c'] + [''] * 5
        if re.match(r'^\d+ - ', c[3]):
            res['fontes'].append({'fonte': c[3], 'cod': c[3].split(' - ')[0], 'v': num(c[4])})
    try:
        res['docs'] = ler_documentos(docs_desde or liq_desde, datetime.now().strftime('%Y-%m-%d'), ano, avisar)
    except Exception as e:
        res['erros'].append(f'documentos fiscais: {e}'); res['docs'] = []
    avisar(f"Coleta: {len(res['empenhos'])} empenhos, {len(res['liquidacoes'])} liquidações, {len(res['pagamentos'])} pagamentos, {len(res['saldo'])} saldos, {len(res.get('docs', []))} documentos fiscais, {len(res['erros'])} erros")
    return res
