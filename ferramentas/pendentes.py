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


def achar_pdf(pasta):
    """id e nome do relatório na pasta pública do Drive (o mais abaixo na lista, se houver mais de um)"""
    m = re.search(r'folders/([A-Za-z0-9_-]+)', pasta)
    pid = m.group(1) if m else pasta.strip()
    html = baixar(f'https://drive.google.com/embeddedfolderview?id={pid}').decode('utf-8', 'replace')
    achados = re.findall(r'id="entry-([A-Za-z0-9_-]+)".*?flip-entry-title">([^<]*)', html, re.S)
    pdfs = [(i, n.strip()) for i, n in achados if NOME.search(n)]
    if not pdfs:
        raise SystemExit('Itens pendentes: não achei o relatório na pasta do Drive (confira o nome do arquivo e o compartilhamento).')
    return pdfs[-1]


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
        fid, nome = achar_pdf(pasta)
        dados = baixar(f'https://drive.google.com/uc?export=download&id={fid}')
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
