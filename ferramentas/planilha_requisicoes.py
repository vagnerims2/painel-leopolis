"""Lê a planilha de requisições (Google Sheets "Espelho Fornecedores") e grava data/planilha.json (sem senha).

Desde 22/10/2026 a aba Requisições é só dos servidores e abre sem senha (o modo antigo, criptografado em
data/planilha.enc.json, foi tirado em 24/10/2026).

Uso:  python ferramentas/planilha_requisicoes.py [--aberto] [arquivo.csv | -] [saida.json]
  sem arquivo (ou "-"): baixa a planilha do endereço em PLANILHA_URL (segredo do GitHub)
  --aberto: aceito por compatibilidade (é o único modo)
Se faltar o endereço, não faz nada (o resto da atualização continua normal).
"""
import csv, io, json, os, re, sys, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


def baixar(url):
    m = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]+)', url)
    if m and '/export' not in url:
        url = f'https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv'
    req = urllib.request.Request(url, headers={'User-Agent': 'painel-leopolis'})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode('utf-8-sig')
    if t.lstrip().startswith('<'):
        raise SystemExit('A planilha não abriu sem login: confira o compartilhamento "Qualquer pessoa com o link — Leitor".')
    return t


# nome da coluna na planilha (normalizado) -> chave curta no arquivo
COLUNAS = {'LIQUIDACAO': 'li', 'LIQUIDACOES': 'li', 'MEMORANDOS': 'm', 'MEMORANDO': 'm', 'SECRETARIA': 's', 'DATA': 'd', 'REQUISICAO': 'r', 'REQUISICAO DE COMPRA': 'r',
           'REQUISICAO DE EMPENHO': 're', 'REQ EMPENHO': 're', 'EMPENHO': 'e', 'ETAPA': 'et', 'STATUS': 'st',
           'DIAS DE ATRASO': 'da', 'EMPRESA': 'f', 'TELEFONE': 't', 'EMAIL': 'em', 'E MAIL': 'em', 'OBSERVACOES': 'o', 'OBSERVACAO': 'o'}


def coluna(h):
    """chave curta de um cabeçalho; aceita variações ("Nº Requisição de Compra", "Req. Empenho", "Fornecedor"…)"""
    n = norm(h)
    if n in COLUNAS:
        return COLUNAS[n]
    n = re.sub(r'\b(N|NO|NUM|NUMERO|DA|DE|DO)\b', ' ', n); n = re.sub(r'\s+', ' ', n).strip()
    if n in COLUNAS:
        return COLUNAS[n]
    if re.search(r'\bREQ\w* EMP', n): return 're'
    if re.search(r'\bREQ\w*( COMPRA)?$', n): return 'r'
    if re.search(r'^EMPENHO', n): return 'e'
    if re.search(r'FORNECEDOR|EMPRESA|CREDOR', n): return 'f'
    if re.search(r'^(FONE|TELEFONE|CELULAR|WHATS)', n): return 't'
    if re.search(r'MAIL', n): return 'em'
    if re.search(r'LIQUIDA', n): return 'li'
    if re.search(r'MEMORANDO', n): return 'm'
    if re.search(r'OBSERVA', n): return 'o'
    return ''


def ler(texto):
    linhas = list(csv.reader(io.StringIO(texto)))
    # o cabeçalho pode não estar na 1ª linha (título em cima): usa a primeira linha que tenha requisição e empresa
    ini = 0   # linha do cabeçalho (0 = primeira linha da planilha)
    for i, ln in enumerate(linhas[:15]):
        ks = [coluna(h) for h in ln]
        if 'r' in ks and ('f' in ks or 't' in ks):
            linhas = linhas[i:]; ini = i; break
    cab = []
    for h in linhas[0]:
        k = coluna(h); cab.append(k if k not in cab else '')   # coluna repetida: vale a primeira
    out = []
    for j, ln in enumerate(linhas[1:]):
        r = {'ln': ini + 2 + j}   # número da linha na planilha (para achar repetidas)
        for k, v in zip(cab, ln):
            v = re.sub(r'\s+', ' ', v).strip()
            if k and v and v.lower() != 'nan':
                r[k] = v
        if not (r.get('f') or r.get('t') or r.get('em')) or not r.get('r'):
            continue
        m = re.match(r'^C[oó]digo Nome\s+(\S+)\s+(.*)$', r.get('f', ''))
        if m:
            r['c'], r['f'] = m.group(1), m.group(2)
        for k in ('r', 'e', 're'):
            if k in r:
                r[k] = re.sub(r'\.0$', '', r[k])
                if k != 'r' and ',' in r[k]:   # mais de um número na célula ("7029, 7030"): guarda todos e usa o primeiro
                    r[k + 's'] = r[k]; r[k] = r[k].split(',')[0].strip()
        out.append(r)
    # aviso no registro do robô: mesma requisição em mais de uma linha
    vis = {}
    for x in out:
        vis.setdefault((x['r'].lstrip('0'), x.get('re', ''), norm(x.get('f', ''))), []).append(x['ln'])
    rep = {k[0]: v for k, v in vis.items() if len(v) > 1}
    if rep:
        print(f'Planilha de requisições: {len(rep)} requisições repetidas (linhas da planilha): ' + '; '.join(f'{k}: {", ".join(map(str, v))}' for k, v in rep.items()))
    return out


ENVIADO = re.compile(r'ENVIAD', re.I)
DATA_TXT = re.compile(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?')


def datas_de_envio(linhas, anteriores, hoje, primeira_vez):
    """Data em que a requisição apareceu como ENVIADO na planilha (a planilha não guarda a data).
    - se a própria célula trouxer a data ("ENVIADO 21/10"), usa ela;
    - senão, guarda o dia em que o robô viu o ENVIADO pela primeira vez;
    - as que já estavam enviadas quando o controle começou ficam marcadas como 'antes'."""
    for r in linhas:
        if not ENVIADO.search(r.get('et', '')):
            continue
        m = DATA_TXT.search(r.get('et', ''))
        if m:
            a = m.group(3) or str(hoje.year); a = a if len(a) == 4 else '20' + a
            try:
                r['env'] = datetime(int(a), int(m.group(2)), int(m.group(1))).strftime('%Y-%m-%d'); continue
            except ValueError:
                pass
        r['env'] = anteriores.get(r['r']) or ('antes' if primeira_vez else hoje.strftime('%Y-%m-%d'))


def main_aberto(fonte, saida):
    """Grava a planilha em JSON aberto (data/planilha.json). Se ela vier vazia ou bem menor que a anterior, não troca o arquivo."""
    texto = baixar(fonte) if fonte.startswith('http') else open(fonte, encoding='utf-8-sig').read()
    linhas = ler(texto)
    hoje = datetime.now(timezone(timedelta(hours=-3)))
    try:
        velho = json.load(open(saida, encoding='utf-8'))
    except Exception:
        velho = {}
    antes = velho.get('linhas') or []
    if not linhas or (len(antes) >= 50 and len(linhas) < 0.6 * len(antes)):
        raise SystemExit(f'Planilha de requisições: veio com {len(linhas)} linhas (antes {len(antes)}); mantive o arquivo anterior.')
    anteriores = {l['r']: l['env'] for l in antes if l.get('env')}
    datas_de_envio(linhas, anteriores, hoje, not velho.get('controle_envio'))
    marca = __import__('hashlib').sha256(json.dumps(linhas, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    if velho.get('marca') == marca:
        print(f'Planilha de requisições: {len(linhas)} linhas, sem mudança.'); return
    cont = {k: sum(1 for l in linhas if l.get(k)) for k in ('r', 're', 'e', 'f', 't', 'em')}
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    json.dump({'atualizado': hoje.strftime('%d/%m/%Y %H:%M'), 'controle_envio': velho.get('controle_envio') or hoje.strftime('%Y-%m-%d'),
               'marca': marca, 'linhas': linhas}, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'Planilha de requisições: {len(linhas)} linhas gravadas em {saida} (preenchidas: {cont}).')


def main():
    args = [a for a in sys.argv[1:] if a != '--aberto']
    fonte = args[0] if args and args[0] != '-' else os.environ.get('PLANILHA_URL', '')
    saida = args[1] if len(args) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'planilha_previa.json')
    if not fonte:
        print('Planilha de requisições: endereço (PLANILHA_URL) não configurado; pulando.'); return
    return main_aberto(fonte, saida)


if __name__ == '__main__':
    main()
