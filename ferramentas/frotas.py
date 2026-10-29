"""Frota do município: cadastro do Portal da Transparência + abastecimentos do sistema de Frotas.

- Cadastro (portal, tela "Relação da Frota Municipal"): todos os veículos e máquinas, ativos e baixados, com placa,
  descrição, aquisição, marca/modelo, ano, local, conservação, combustível e medidor. Lido a cada atualização.
- Abastecimentos (sistema de Frotas do Equiplano, que não vai para o portal): "Relatório de Abastecimento de Veículos"
  (rptAbastecimentoVeiculo), salvo pelo Vagner na pasta "Frotas" do Drive (compartilhada por link, sem login). O robô lê
  todos os PDFs da pasta e junta os abastecimentos (um relatório novo substitui o que já havia pela ordem de abastecimento).
  A pasta vem do segredo FROTAS_PASTA (link ou id da pasta).
Os dois se ligam pela placa (máquinas sem placa: pela descrição). Grava data/frotas.json.

Uso:  python ferramentas/frotas.py [arquivo.pdf ... | -] [saida.json] [--motorista] [--sem-portal]
  -            lê os PDFs da pasta do Drive
  --motorista  inclui o nome do motorista (sem ele, o arquivo publicado não traz nomes de pessoas)
  --sem-portal não lê o cadastro do portal (só o relatório de abastecimento)
"""
import io, json, os, re, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from pendentes import baixar, baixar_drive

CACHE = os.path.join(os.path.dirname(__file__), '..', 'motor', 'estado', 'frotas_pdfs.json')
CABECALHO = re.compile(r'^(Equiplano|SISTEMA DE CONTROLE DE FROTAS|página \d+|MUNICÍPIO DE LEÓPOLIS|de|Período: .*|Veículo nr pr.*|SCF \d.*|.*rptAbastecimentoVeiculo\.jasper.*)$')
PERIODO = re.compile(r'Período: (\d\d/\d\d/\d{4}) à (\d\d/\d\d/\d{4})')
EMITIDO = re.compile(r', (\d\d/\d\d/\d{4} \d\d:\d\d:\d\d)')  # "VAGNER ..., 28/10/2026 20:47:33" no rodapé
# tipo + combustível, litros (3 casas), preço (3 casas), valor (2 casas), hodômetro/horímetro (pode faltar), percorrido, média (2 casas) colada no nº da NF
ABAST = re.compile(r'^(Parcial|Completo)([A-ZÇÃÁÉÍÓÕÚ0-9 ]+?) ?(\d[\d.]*,\d{3}) ?(\d[\d.]*,\d{3}) (\d[\d.]*,\d{2}) (?:(\d+(?:\.\d+)?) )?(-?\d+) (-?\d+,\d{2})(\d*)$')
FROTA = re.compile(r'^Nr\.Frota: (\S+) Placa: (\S*) Cod\.Patr\.: (\S*) ?(.*)$')
ORGAO = re.compile(r'Órgão: (\d+) - (.+?)\s+Unidade: (\d+) - (.+?)\s+Local: (\d+) - (.+)$')
TOTAL = re.compile(r'^Total Veículo (\d[\d.]*,\d{3})')


def num(s):
    return float(s.replace('.', '').replace(',', '.'))


def texto_pdf(dados):
    from pypdf import PdfReader
    return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(dados)).pages)


def ler(texto):
    """{'periodo': (de, ate), 'emitido', 'veiculos': {frota: {...}}, 'abast': [...], 'avisos': [...]}"""
    L = [x.strip() for x in texto.splitlines()]
    per = PERIODO.search(texto); emi = EMITIDO.search(texto)
    out = {'periodo': [per.group(1), per.group(2)] if per else None, 'emitido': emi.group(1) if emi else '', 'veiculos': {}, 'abast': [], 'avisos': []}
    grupo = {}; v = None; a = None; i = 0; soma = 0.0
    while i < len(L):
        l = L[i]; i += 1
        if not l or CABECALHO.match(l):
            continue
        m = re.match(r'^(.*)(Espécie|Marca|Modelo):$', l)
        if m:
            grupo[m.group(2).lower()] = m.group(1).strip(); continue
        m = FROTA.match(l)
        if m:
            v = {'frota': m.group(1), 'placa': m.group(2), 'patrimonio': m.group(3), 'descricao': m.group(4).strip(),
                 'especie': grupo.get('espécie', ''), 'marca': grupo.get('marca', ''), 'modelo': grupo.get('modelo', ''), 'medida': 'km'}
            out['veiculos'][v['frota']] = v; a = None; soma = 0.0; continue
        if l.startswith('Órgão:') and v is not None:
            # o órgão, a unidade e o local quebram em mais de uma linha
            bloco = l; m = None
            while i < len(L) and not L[i].startswith(('Parcial', 'Completo', 'Total ')) and L[i] not in ('KmKm', 'horahora'):
                m = ORGAO.search(re.sub(r'\s+', ' ', bloco))
                if m and not re.search(r'Local: \d+ -\s*$', bloco):
                    break
                bloco += ' ' + L[i]; i += 1
            m = ORGAO.search(re.sub(r'\s+', ' ', bloco))
            if m:
                v.update(orgao=f'{m.group(1)} - {m.group(2).strip()}', unidade=m.group(4).strip(), local=m.group(6).strip())
            continue
        if l in ('KmKm', 'horahora') and v is not None:
            v['medida'] = 'km' if l == 'KmKm' else 'h'; continue
        if l.startswith(('Parcial', 'Completo')) and v is not None:
            # linha quebrada pelo PDF (ex.: valor grande que não coube): junta com as próximas até fechar o padrão
            m = ABAST.match(l); j = i; tentativa = l
            while not m and j < len(L) and j < i + 3:
                tentativa = tentativa + ('' if re.search(r',\d$', tentativa) else ' ') + L[j]; j += 1
                m = ABAST.match(tentativa)
            if not m:
                out['avisos'].append(f'linha não lida (frota {v["frota"]}): {l}'); continue
            i = j
            a = {'frota': v['frota'], 'tipo': m.group(1), 'combustivel': m.group(2).strip(), 'litros': num(m.group(3)), 'preco': num(m.group(4)),
                 'valor': num(m.group(5)), 'hod': float(m.group(6)) if m.group(6) else None, 'nf': m.group(9) or '', 'ordem': '', 'data': '',
                 'posto': '', 'motorista': ''}
            out['abast'].append(a); soma += a['litros']; continue
        m = TOTAL.match(l)
        if m and v is not None:
            if abs(num(m.group(1)) - soma) > 0.01:
                out['avisos'].append(f'frota {v["frota"]}: soma dos litros {soma:.3f} difere do total do relatório {m.group(1)}')
            a = None; continue
        if l.startswith('Total '):
            a = None; continue
        if a is None:
            continue
        m = re.match(r'^ordem (\d+)$', l)
        if m:
            a['ordem'] = m.group(1); continue
        m = re.match(r'^Motorista: ?(.*)$', l)
        if m:
            a['motorista'] = m.group(1).strip(); continue
        m = re.match(r'^(\d\d)/(\d\d)/(\d{4}) (\d\d:\d\d)$', l)
        if m:
            a['data'] = f'{m.group(3)}-{m.group(2)}-{m.group(1)} {m.group(4)}'; continue
        m = re.match(r'^\d+-\d (.+)$', l)
        if m and not a['posto']:
            # "POSTO PASSAGNOLO LTDA Leópolis/PR": tira a cidade (que pode ter espaço, como "Piraí do Sul/PR")
            p = m.group(1).strip(); f = re.match(r'^(.*?\b(?:LTDA|EIRELI|S/?A|EPP|ME)\b\.?)', p, re.I)
            a['posto'] = f.group(1) if f else re.sub(r' \S+/[A-Z]{2}$', '', p); continue
    return out


def juntar(relatorios):
    """junta os relatórios (do mais antigo ao mais novo): o mais novo substitui o abastecimento de mesma ordem"""
    veic, ab = {}, {}
    for r in relatorios:
        veic.update(r['veiculos'])
        for a in r['abast']:
            ab[a['ordem'] or f"{a['frota']}|{a['data']}|{a['litros']}"] = a
    return veic, sorted(ab.values(), key=lambda a: (a['data'], a['frota']))


PORTAL = 'https://leopolispr.equiplano.com.br:7300/transparencia/relacaoFrotaMunicipal/listaRelacaoFrotaMunicipal'


def cadastro_portal():
    """veículos e máquinas da "Relação da Frota Municipal" do portal (CSV), ativos e baixados"""
    import csv
    out = []
    for ativo, cod in ((True, 1), (False, 2)):
        url = (f'{PORTAL}?formulario.codEntidade=300&formulario.somenteVeiculosAtivos={cod}&formulario.tipoMedidor=&formulario.codLocal='
               '&formulario.dtInicial=&formulario.dtFinal=&6578706f7274=1&d-5470-e=1')
        txt = baixar(url).decode('latin-1')
        if not txt.startswith('Placa;'):
            raise RuntimeError('o portal não devolveu a lista da frota')
        for r in csv.DictReader(io.StringIO(txt), delimiter=';'):
            placa = r['Placa'].strip()
            out.append({'placa': '' if placa.lower().startswith('não informado') else placa, 'descricao': re.sub(r'\s+', ' ', r['Descrição']).strip(),
                        'aquisicao': r['Dt. Aquisição'].strip(), 'marca_modelo': r['Marca/Modelo'].strip(), 'ano': '' if 'Informado' in r['Ano Fab.'] else r['Ano Fab.'].strip(),
                        'local': r['Local'].strip(), 'conservacao': '' if 'Informado' in r['Conservação'] else r['Conservação'].strip(),
                        'combustivel': r['Combustível'].strip(), 'medidor': r['Medidor'].strip(), 'ativo': ativo})
    return out


def ligar(veiculos, cadastro):
    """liga cada veículo do relatório de abastecimento ao cadastro do portal: pela placa; sem placa, pela descrição
    (no relatório ela vem cortada, então vale o começo). Devolve {frota: índice no cadastro}."""
    pl = lambda s: re.sub(r'[^A-Z0-9]', '', (s or '').upper())
    ds = lambda s: re.sub(r'\s+', ' ', (s or '').upper()).strip()
    livres = set(range(len(cadastro))); par = {}
    por_placa = {}
    for i, c in enumerate(cadastro):
        if pl(c['placa']):
            por_placa.setdefault(pl(c['placa']), []).append(i)
    for v in veiculos:  # placa: o ativo primeiro
        cs = [i for i in por_placa.get(pl(v['placa']), []) if i in livres] if pl(v['placa']) else []
        cs.sort(key=lambda i: not cadastro[i]['ativo'])
        if cs:
            par[v['frota']] = cs[0]; livres.discard(cs[0])
    for v in veiculos:  # descrição igual ou que começa igual (máquinas iguais, como duas retroescavadeiras, ficam uma para cada)
        if v['frota'] in par or not v.get('descricao'):
            continue
        d = ds(v['descricao'])
        cs = sorted((i for i in livres if ds(cadastro[i]['descricao']) == d), key=lambda i: not cadastro[i]['ativo']) or \
             sorted((i for i in livres if ds(cadastro[i]['descricao']).startswith(d) or d.startswith(ds(cadastro[i]['descricao']))), key=lambda i: not cadastro[i]['ativo'])
        if cs:
            par[v['frota']] = cs[0]; livres.discard(cs[0])
    return par


def gravar(relatorios, saida, motorista=False, cadastro=None):
    veic, ab = juntar(relatorios)
    if cadastro:
        # veículos do cadastro que não abasteceram no período entram também (sem nº de frota, que só existe no sistema de Frotas)
        par = ligar(list(veic.values()), cadastro)
        org = {}  # local do portal ("18-SECRETARIA ...") -> órgão do relatório, para a secretaria sair igual
        for v in veic.values():
            if v['frota'] in par:
                c = cadastro[par[v['frota']]]; v['cad'] = c
                org.setdefault(c['local'].split('-')[0], v.get('orgao', ''))
        usados = set(par.values())
        for i, c in enumerate(cadastro):
            if i in usados:
                continue
            k = f'p{i}'
            veic[k] = {'frota': '', 'chave': k, 'placa': c['placa'], 'patrimonio': '', 'descricao': c['descricao'], 'especie': '', 'marca': c['marca_modelo'].split('/')[0],
                       'modelo': c['marca_modelo'], 'orgao': org.get(c['local'].split('-')[0]) or c['local'], 'unidade': '', 'local': c['local'],
                       'medida': 'h' if c['medidor'].startswith('Hor') else 'km' if c['medidor'].startswith('Hod') else 'n', 'cad': c}  # n: motosserra, roçadeira (sem medidor)
    lista = sorted(veic.values(), key=lambda v: (v.get('orgao', ''), int(v['frota']) if v['frota'].isdigit() else 10 ** 6))
    pos = {v.get('chave', v['frota']): k for k, v in enumerate(lista)}
    postos = sorted({a['posto'] for a in ab}); mot = sorted({a['motorista'] for a in ab}) if motorista else []
    comb = sorted({a['combustivel'] for a in ab})
    datas = [a['data'][:10] for a in ab if a['data']]
    dados = {
        'gerado': datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M'),
        'periodo': [min(datas), max(datas)] if datas else None,
        'relatorios': [{'arquivo': r.get('arquivo', ''), 'periodo': r['periodo'], 'emitido': r['emitido'], 'abastecimentos': len(r['abast'])} for r in relatorios],
        # cadastro do portal em cada veículo (quando achado): ano, aquisição, conservação, combustível, ativo ou baixado
        'cadastro': {'lido': bool(cadastro), 'ativos': sum(1 for c in cadastro or [] if c['ativo']), 'baixados': sum(1 for c in cadastro or [] if not c['ativo'])},
        'veiculos': [dict({k: v.get(k, '') for k in ('frota', 'placa', 'patrimonio', 'descricao', 'especie', 'marca', 'modelo', 'orgao', 'unidade', 'local', 'medida')},
                          **({'portal': {k: v['cad'][k] for k in ('descricao', 'aquisicao', 'marca_modelo', 'ano', 'local', 'conservacao', 'combustivel', 'medidor', 'ativo')}} if v.get('cad') else {}))
                     for v in lista],
        'postos': postos, 'combustiveis': comb, 'motoristas': mot,
        # cada abastecimento: [veículo, data e hora, combustível, litros, preço, valor, hodômetro/horímetro, NF, ordem, posto, motorista]
        'campos': ['veiculo', 'data', 'combustivel', 'litros', 'preco', 'valor', 'hod', 'nf', 'ordem', 'posto', 'motorista'],
        'abastecimentos': [[pos[a['frota']], a['data'], comb.index(a['combustivel']), a['litros'], a['preco'], a['valor'], a['hod'], a['nf'], a['ordem'],
                            postos.index(a['posto']), mot.index(a['motorista']) if motorista else None] for a in ab],
        'avisos': [x for r in relatorios for x in r['avisos']],
    }
    with open(saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, separators=(',', ':'))
    return dados


def listar(pasta):
    """[(id, nome, alteração)] dos PDFs da pasta pública do Drive"""
    m = re.search(r'folders/([A-Za-z0-9_-]+)', pasta)
    pid = m.group(1) if m else pasta.strip()
    html = baixar(f'https://drive.google.com/embeddedfolderview?id={pid}').decode('utf-8', 'replace')
    out = []
    for bloco in re.split(r'(?=<div class="flip-entry")', html)[1:]:
        i = re.search(r'id="entry-([A-Za-z0-9_-]+)"', bloco); n = re.search(r'flip-entry-title">([^<]*)', bloco)
        d = re.search(r'flip-entry-last-modified"[^>]*>(?:<[^>]+>)*([^<]+)', bloco)
        if i and n and n.group(1).lower().endswith('.pdf'):
            out.append((i.group(1), n.group(1).strip(), d.group(1).strip() if d else ''))
    return out


def da_pasta(pasta):
    """relatórios da pasta do Drive, já lidos; baixa só o que é novo ou mudou"""
    try:
        cache = json.load(open(CACHE, encoding='utf-8'))
    except Exception:
        cache = {}
    novo, out = {}, []
    for fid, nome, mod in listar(pasta):
        k = f'{fid}|{mod}'
        r = cache.get(k)
        if r is None:
            r = ler(texto_pdf(baixar_drive(fid)))
            if not r['abast']:
                print(f'Aviso: {nome} não parece um relatório de abastecimento; ignorado.')
                continue
        r['arquivo'] = nome; novo[k] = r; out.append(r)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(novo, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
    # o mais antigo primeiro: pela data de emissão do relatório
    chave = lambda r: datetime.strptime(r['emitido'], '%d/%m/%Y %H:%M:%S') if r['emitido'] else datetime.min
    return sorted(out, key=chave)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    motorista = '--motorista' in sys.argv
    saida = args.pop() if len(args) >= 2 else 'data/frotas.json'
    if not args or args == ['-']:
        pasta = os.environ.get('FROTAS_PASTA', '').strip()
        if not pasta:
            sys.exit('FROTAS_PASTA não configurada; frota não atualizada.')
        rels = da_pasta(pasta)
    else:
        rels = []
        for p in args:
            r = ler(texto_pdf(open(p, 'rb').read())); r['arquivo'] = os.path.basename(p); rels.append(r)
    if not rels:
        sys.exit('Nenhum relatório de abastecimento na pasta; frota não atualizada.')
    cad = None
    if '--sem-portal' not in sys.argv:
        try:
            cad = cadastro_portal()
        except Exception as e:
            print(f'Aviso: cadastro da frota não lido no portal ({e}); a aba mostra só o relatório de abastecimento.')
    d = gravar(rels, saida, motorista, cad)
    print('ok', len(d['veiculos']), 'veículos,', len(d['abastecimentos']), 'abastecimentos,', len(d['avisos']), 'avisos;',
          f"cadastro do portal: {d['cadastro']['ativos']} ativos e {d['cadastro']['baixados']} baixados" if cad else 'sem cadastro do portal')
    for x in d['avisos'][:10]:
        print('  aviso:', x)
