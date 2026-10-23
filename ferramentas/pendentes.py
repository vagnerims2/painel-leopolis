"""Itens pendentes das requisições de compra (relatório do Equiplano salvo pelo Vagner no Google Drive).

Relatório: "Controle de saldo da Requisição de compra x Liquidação quantitativa", emitido com o critério
"Somente produtos com quantidade pendente". Se a requisição aparece, os itens listados estão pendentes;
se não aparece, já foi tudo recebido.

O robô procura o PDF mais recente com esse nome na pasta do Drive (compartilhada por link, sem login),
lê os itens e grava data/pendentes.json. A pasta vem do segredo PENDENTES_PASTA (link ou id da pasta).

Uso:  python ferramentas/pendentes.py [arquivo.pdf | -] [saida.json]
"""
import io, json, os, re, sys, urllib.request
from datetime import datetime, timezone, timedelta

NOME = re.compile(r'controle de saldo da requisi', re.I)
CAB = re.compile(r'^\s*(\d+)/(\d{4})\s+(\d\d/\d\d/\d{4})\s+(\S+-\d)\s+(.+?)\s*$')
ITEM = re.compile(r'^\s*(\d{3}/\d{3})\s+(\d+)\s+(.+?)\s{2,}([\d.]+,\d\d)\s+([\d.]+,\d+)\s+([\d.]+,\d{3})\s+([\d.]+,\d{3})\s+(-?[\d.]+,\d{3})\s*$')
EMITIDO = re.compile(r'(\d\d/\d\d/\d{4} \d\d:\d\d:\d\d)\s*$')
PERIODO = re.compile(r'Data da requisi\S+ de compra: de (\d\d/\d\d/\d{4}) at\S+ (\d\d/\d\d/\d{4})')


def num(s):
    return float(s.replace('.', '').replace(',', '.'))


def baixar(url, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 painel-leopolis'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


CACHE = os.path.join(os.path.dirname(__file__), '..', 'motor', 'estado', 'drive_pdfs.json')

def listar(pasta):
    """[(id, nome, alteração)] dos relatórios do Equiplano na pasta pública do Drive"""
    m = re.search(r'folders/([A-Za-z0-9_-]+)', pasta)
    pid = m.group(1) if m else pasta.strip()
    html = baixar(f'https://drive.google.com/embeddedfolderview?id={pid}').decode('utf-8', 'replace')
    out = []
    for bloco in re.split(r'(?=<div class="flip-entry")', html)[1:]:
        i = re.search(r'id="entry-([A-Za-z0-9_-]+)"', bloco); n = re.search(r'flip-entry-title">([^<]*)', bloco)
        d = re.search(r'flip-entry-last-modified"[^>]*>(?:<[^>]+>)*([^<]+)', bloco)
        if i and n and NOME.search(n.group(1)):
            out.append((i.group(1), n.group(1).strip(), d.group(1).strip() if d else ''))
    return out

def tipo_de(texto):
    """'pend' = relatório resumido (só pendentes); 'ano' = relatório completo, com movimentos"""
    if re.search(r'Somente produtos com quantidade pendente', texto, re.I): return 'pend'
    if re.search(r'Requisi\S+ de empenho\s+\d+/\d{4}', texto): return 'ano'
    return 'pend'

def relatorios(pasta):
    """os relatórios da pasta com o tipo de cada um; baixa só o que é novo (guarda o tipo por id + data de alteração)"""
    try:
        cache = json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        cache = {}
    out = []
    for fid, nome, mod in listar(pasta):
        k = f'{fid}|{mod}'; dados = None
        if k not in cache:
            dados = baixar(f'https://drive.google.com/uc?export=download&id={fid}', timeout=600)
            if not dados.startswith(b'%PDF'):
                continue
            import pypdf
            r = pypdf.PdfReader(io.BytesIO(dados))
            cache[k] = tipo_de('\n'.join(p.extract_text() or '' for p in r.pages[:3]))
        out.append({'id': fid, 'nome': nome, 'mod': mod, 'chave': k, 'tipo': cache[k], 'dados': dados})
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True); json.dump(cache, open(CACHE, 'w', encoding='utf-8'))
    except Exception:
        pass
    return out

def achar_pdf(pasta, tipo='pend'):
    """o relatório do tipo pedido (o último da lista, se houver mais de um); devolve (id, nome, bytes ou None)"""
    rs = relatorios(pasta)
    escolha = [r for r in rs if r['tipo'] == tipo] or ([r for r in rs] if tipo == 'pend' else [])
    if not escolha:
        raise SystemExit(f'Relatório ({tipo}): não achei na pasta do Drive (confira o nome do arquivo e o compartilhamento).')
    r = escolha[-1]
    return r['id'], r['nome'], r['dados']


def texto_pdf(dados):
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(dados))
    return '\n'.join(p.extract_text(extraction_mode='layout') or '' for p in r.pages)


def ler(texto):
    reqs, cur, periodo, emitido = {}, None, None, None
    for l in texto.split('\n'):
        if periodo is None and (m := PERIODO.search(l)):
            periodo = [m.group(1), m.group(2)]
        if 'Emitido por' in l and (m := EMITIDO.search(l)):
            emitido = m.group(1)
            continue
        if (m := CAB.match(l)):
            cur = reqs.setdefault(m.group(1), {'d': m.group(3), 'c': m.group(4), 'f': re.sub(r'\s+', ' ', m.group(5)), 'i': []})
            continue
        if cur is not None and (m := ITEM.match(l)):
            cur['i'].append([m.group(1), m.group(2), re.sub(r'\s+', ' ', m.group(3)).strip(), num(m.group(4)), num(m.group(5)),
                             num(m.group(6)), num(m.group(7)), num(m.group(8))])
    # só interessa o que está pendente (o relatório resumido já vem assim; o completo traz também os recebidos)
    for r in reqs.values():
        r['i'] = [i for i in r['i'] if i[7] > 0.0005]
    return {k: v for k, v in reqs.items() if v['i']}, periodo, emitido


def main():
    args = [a for a in sys.argv[1:]]
    fonte = args[0] if args and args[0] != '-' else ''
    saida = args[1] if len(args) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'pendentes.json')
    if fonte:
        dados, nome = open(fonte, 'rb').read(), os.path.basename(fonte)
    else:
        pasta = os.environ.get('PENDENTES_PASTA', '')
        if not pasta:
            print('Itens pendentes: pasta do Drive (PENDENTES_PASTA) não configurada; pulando.'); return
        fid, nome, dados = achar_pdf(pasta, 'pend')
        dados = dados or baixar(f'https://drive.google.com/uc?export=download&id={fid}', timeout=600)
        if not dados.startswith(b'%PDF'):
            raise SystemExit('Itens pendentes: o arquivo do Drive não veio como PDF (confira o compartilhamento).')
    reqs, periodo, emitido = ler(texto_pdf(dados))
    try:
        velho = json.load(open(saida, encoding='utf-8'))
    except Exception:
        velho = {}
    if velho.get('emitido') and emitido and velho.get('emitido') == emitido and velho.get('reqs') == reqs:
        print(f'Itens pendentes: relatório de {emitido} já lido ({len(reqs)} requisições).'); return
    if not reqs and len(dados) > 50000:
        raise SystemExit('Itens pendentes: o PDF veio, mas não li nenhuma requisição; mantive o arquivo anterior.')
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
    out = {'lido': agora, 'emitido': emitido, 'periodo': periodo, 'arquivo': nome,
           'fonte': 'Equiplano: Controle de saldo da Requisição de compra x Liquidação quantitativa (somente produtos com quantidade pendente).',
           'campos': ['lote/item', 'código', 'produto', 'valor total', 'valor unitário', 'requisitada', 'liquidada', 'pendente'],
           'reqs': reqs}
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    json.dump(out, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'Itens pendentes: {len(reqs)} requisições, {sum(len(r["i"]) for r in reqs.values())} itens (emitido {emitido}).')


if __name__ == '__main__':
    main()
