"""Itens das notas fiscais (XML da NF-e) salvos pelo Vagner na subpasta "XML Notas" da pasta do Drive.

O portal da transparência só traz número, valor e chave de acesso da nota; os produtos vêm do XML.
A cada rodada o robô lista a subpasta (compartilhada por link, sem login), baixa só os arquivos ainda não lidos
e junta tudo em data/notas_itens.json. O arquivo só cresce: depois de lido, o XML pode ser apagado da pasta.

Do XML guarda só o necessário para a busca de produtos: chave, número, série, data, CNPJ e nome do emitente,
valor da nota e, de cada item, descrição, unidade, quantidade, valor unitário e total (nada de dados adicionais,
transporte, motorista ou impostos). Evento de cancelamento (110111) marca a nota como cancelada.
Também aceita .zip com XMLs dentro.

Uso:  python ferramentas/notas_xml.py [saida.json] [arquivo_ou_pasta_local ...]
      (sem arquivos locais, usa a subpasta do Drive achada dentro de PENDENTES_PASTA)
"""
import io, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from pendentes import baixar  # noqa: E402

NS = '{http://www.portalfiscal.inf.br/nfe}'
SUBPASTA = re.compile(r'\bxml', re.I)
LIMITE = 400   # arquivos novos por rodada (o resto fica para a próxima)


def entradas(pid):
    """[(id, nome, alteração, é_pasta)] de uma pasta pública do Drive"""
    html = baixar(f'https://drive.google.com/embeddedfolderview?id={pid}').decode('utf-8', 'replace')
    out = []
    for bloco in re.split(r'(?=<div class="flip-entry")', html)[1:]:
        i = re.search(r'id="entry-([A-Za-z0-9_-]+)"', bloco); n = re.search(r'flip-entry-title">([^<]*)', bloco)
        d = re.search(r'flip-entry-last-modified"[^>]*>(?:<[^>]+>)*([^<]+)', bloco)
        if i and n:
            out.append((i.group(1), n.group(1).strip(), d.group(1).strip() if d else '', '/folders/' in bloco))
    return out


def baixar_arquivo(fid):
    """XML/ZIP pequeno do Drive: às vezes vem a página de "verificação de vírus"; aí confirma com os campos dela"""
    dados = baixar(f'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t')
    if dados[:2] == b'PK' or b'<html' not in dados[:3000].lower():
        return dados
    campos = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', dados.decode('utf-8', 'replace')))
    if campos:
        from urllib.parse import urlencode
        return baixar('https://drive.usercontent.google.com/download?' + urlencode(campos))
    return dados


def t(el, cam):
    x = el.find('/'.join(NS + p for p in cam.split('/')))
    return (x.text or '').strip() if x is not None else ''


def ler_xml(dados):
    """devolve ('nfe', chave, nota) | ('canc', chave, None) | (None, None, None)"""
    try:
        raiz = ET.fromstring(dados)
    except (ET.ParseError, ValueError):
        return None, None, None
    ev = raiz.find(f'.//{NS}infEvento')
    if ev is not None and raiz.find(f'.//{NS}infNFe') is None:
        return ('canc' if t(ev, 'tpEvento') == '110111' else None), t(ev, 'chNFe'), None
    inf = raiz.find(f'.//{NS}infNFe')
    if inf is None:
        return None, None, None
    chave = (inf.get('Id') or '').replace('NFe', '')
    itens = []
    for det in inf.findall(f'{NS}det'):
        p = det.find(f'{NS}prod')
        if p is None:
            continue
        f = lambda k: float(t(p, k).replace(',', '.') or 0)
        itens.append([t(p, 'xProd'), t(p, 'uCom'), round(f('qCom'), 4), round(f('vUnCom'), 4), round(f('vProd'), 2)])
    nota = {'n': t(inf, 'ide/nNF'), 's': t(inf, 'ide/serie'), 'd': (t(inf, 'ide/dhEmi') or t(inf, 'ide/dEmi'))[:10],
            'cnpj': t(inf, 'emit/CNPJ') or t(inf, 'emit/CPF'), 'f': t(inf, 'emit/xNome'),
            'dest': t(inf, 'dest/CNPJ'), 'v': float(t(inf, 'total/ICMSTot/vNF') or 0), 'i': itens}
    return 'nfe', chave, nota


def abrir(dados):
    """um arquivo pode ser XML ou ZIP de XMLs"""
    if dados[:2] == b'PK':
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                return [z.read(n) for n in z.namelist() if n.lower().endswith('.xml')]
        except (zipfile.BadZipFile, OSError):
            return []   # ZIP com defeito: conta como arquivo não reconhecido
    return [dados]


def main():
    args = sys.argv[1:]
    saida = args[0] if args else os.path.join(os.path.dirname(__file__), '..', 'data', 'notas_itens.json')
    try:
        base = json.load(open(saida, encoding='utf-8'))
    except Exception:
        base = {}
    notas, lidos, canc = base.get('notas', {}), base.get('lidos', {}), set(base.get('canceladas', []))
    novos = []   # (identificador, bytes)
    locais = args[1:]
    if locais:
        for a in locais:
            arqs = [os.path.join(r, n) for r, _, ns in os.walk(a) for n in ns] if os.path.isdir(a) else [a]
            novos += [(os.path.basename(x), open(x, 'rb').read()) for x in arqs if x.lower().endswith(('.xml', '.zip'))]
    else:
        pasta = os.environ.get('PENDENTES_PASTA', '')
        if not pasta:
            print('XML das notas: pasta do Drive (PENDENTES_PASTA) não configurada; pulando.'); return
        m = re.search(r'folders/([A-Za-z0-9_-]+)', pasta); pid = m.group(1) if m else pasta.strip()
        sub = [e for e in entradas(pid) if e[3] and SUBPASTA.search(e[1])]
        if not sub:
            print('XML das notas: não achei a subpasta "XML Notas" na pasta do Drive; pulando.'); return
        lista = [e for e in entradas(sub[0][0]) if not e[3] and e[1].lower().endswith(('.xml', '.zip'))]
        pend = [e for e in lista if lidos.get(e[0]) != e[2]]
        for fid, nome, mod, _ in pend[:LIMITE]:
            try:
                novos.append(((fid, mod), baixar_arquivo(fid)))
            except Exception as ex:
                print(f'Aviso: não baixei "{nome}" ({ex}); tento na próxima rodada.')
        if len(pend) > LIMITE:
            print(f'XML das notas: {len(pend) - LIMITE} arquivos ficam para a próxima rodada.')
        base['na_pasta'] = len(lista)
    n_nfe = n_canc = n_ruim = 0
    for ident, dados in novos:
        ok = False
        for x in abrir(dados):
            try:
                tipo, chave, nota = ler_xml(x)
            except ValueError:   # número fora do padrão no XML: pula este arquivo, segue com os outros
                tipo = chave = nota = None
            if tipo == 'nfe' and chave:
                notas[chave] = nota; n_nfe += 1; ok = True
            elif tipo == 'canc' and chave:
                canc.add(chave); n_canc += 1; ok = True
            elif tipo is None and chave:
                ok = True   # outro evento (carta de correção etc.): nada a guardar
        if not ok:
            n_ruim += 1
        if isinstance(ident, tuple):
            lidos[ident[0]] = ident[1]
    for c in canc:
        if c in notas:
            notas[c]['canc'] = 1
    if not novos and base.get('notas') is not None:
        print(f'XML das notas: nada novo ({len(notas)} notas já lidas).')
        if base.get('na_pasta') is not None:
            json.dump(base, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        return
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
    base.update({'lido': agora, 'campos': ['descrição', 'unidade', 'quantidade', 'valor unitário', 'valor total'],
                 'notas': notas, 'canceladas': sorted(canc), 'lidos': lidos})
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    json.dump(base, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'XML das notas: {n_nfe} notas e {n_canc} cancelamentos lidos agora'
          + (f', {n_ruim} arquivos não reconhecidos' if n_ruim else '') + f'; total {len(notas)} notas.')


if __name__ == '__main__':
    main()
