"""Receitas, indicadores da LRF e dívida ativa — tudo do Portal da Transparência de Leópolis (Equiplano).

Gera dois arquivos para o site:
  data/receitas.json     receita prevista x arrecadada (Anexo 10), arrecadação por mês, comparação com o ano anterior
  data/indicadores.json  saúde (15%), educação (25% e FUNDEB 70%), pessoal (LRF), dívida consolidada,
                         dívida ativa (recebido e saldo a receber, só totais) e gasto por função

Uso:  python financas.py PASTA_SAIDA      (ou financas.gerar(pasta) a partir do painel.py)
Os relatórios são os mesmos que qualquer cidadão baixa no portal (botão CSV). Nenhum dado interno.
"""
import json, os, re, sys, time
from datetime import date, datetime
from urllib.parse import urlencode

import coleta
from coleta import BASE, num

ENTIDADES = [(304, 'Câmara Municipal de Leópolis', 'CAMARA'), (300, 'Município de Leópolis', 'PREFEITURA')]
MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']
MES_ABREV = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


# ---------------------------------------------------------------- acesso ao portal
def post(caminho, dados):
    """POST no portal com 3 tentativas; devolve o texto (CSV em latin-1). Erro se o portal devolver a página HTML de erro."""
    for i in range(3):
        try:
            r = coleta.SESSAO.post(BASE + caminho, data=dados, timeout=300, verify=coleta._VERIFICA_SSL)
            r.raise_for_status()
            t = r.content.decode('latin-1')
            if '<html' in t[:3000].lower():
                m = re.search(r'(Regra de neg[^<]{0,200}|Ocorreu uma exce[^<]{0,120})', t)
                raise RuntimeError(f'{caminho}: o portal não gerou o relatório ({m.group(1).strip() if m else "página de erro"})')
            return t
        except RuntimeError:
            raise
        except Exception:
            if i == 2:
                raise
            time.sleep(3)


def lrf(caminho, periodicidade, periodo, entidades=(304, 300), ano=None, **extra):
    dados = [('formulario.exercicio', str(ano or date.today().year)), ('formulario.tpPeriodicidadeLrf', str(periodicidade)),
             ('formulario.tpPeriodoLrf', str(periodo)), ('formulario.nrPaginaInicial', '1'), ('formulario.tpFormatoExterno', 'CSV')]
    dados += [(f'formulario.{k}', str(v)) for k, v in extra.items()]
    for i, (cod, nome, tipo) in enumerate(ENTIDADES):
        dados += [(f'formulario.seletorEntidades.itens[{i}].objeto.codEntidade', str(cod)),
                  (f'formulario.seletorEntidades.itens[{i}].objeto.nome', nome),
                  (f'formulario.seletorEntidades.itens[{i}].objeto.tipoEntidade', tipo)]
        if cod in entidades:
            dados.append((f'formulario.seletorEntidades.itens[{i}].selecionado', 'true'))
    return post(f'{caminho}/process', dados)


def anexo10(ano, m1, m2):
    dados = {'formulario.exercicio': str(ano), 'formulario.mesInicial': str(m1), 'formulario.mesFinal': str(m2),
             'formulario.previsaoAnexo10Receitas': '2', 'formulario.tpFormatoExterno': 'CSV',
             'formulario.seletorEntidades.itens[0].objeto.codEntidade': '304',
             'formulario.seletorEntidades.itens[1].objeto.codEntidade': '300', 'formulario.seletorEntidades.itens[1].selecionado': 'true'}
    return post('execucaoOrcamentariaAnexo10ComparativoDaReceitaPrevistaComArrecadada/process', dados)


def arrecadacao_mensal(ano):
    out = []
    for r in coleta.tabela(f'{BASE}receitaArrecadada/listaReceitaArrecadadaPorMes?formulario.codEntidade=300&formulario.exercicio={ano}'):
        c = [x for x in r['c'] if x]
        if len(c) >= 2 and c[0] in MESES:
            out.append([c[0], num(c[1])])
    return out


def inscritos_divida_ativa(ano):
    t = post('inscritosDividaAtiva/process', {'formulario.nrExercicio': str(ano), 'formulario.nmContribuinte': '',
                                               'formulario.nrDocumento': '', 'formulario.tpFormatoExterno': 'CSV'})
    # só os valores; nomes e documentos dos contribuintes não saem daqui
    vals = []
    for linha in t.splitlines()[1:]:
        p = linha.strip().split(';')
        if len(p) >= 2:
            try:
                vals.append(float(p[-1].strip().replace(',', '.')))
            except ValueError:
                pass
    return vals


# ---------------------------------------------------------------- leitura dos CSVs
def linhas(t):
    return [re.sub(r';{2,}', ';', l).strip(' ;\t') for l in t.replace('\r', '').split('\n')]

_NUM = re.compile(r'^\(?-?[\d.]*\d,\d+\)?%?$|^\(?-?\d+\)?%?$')
def nums(l):
    return [num(x.rstrip('%')) for x in l.split(';') if _NUM.match(x.strip())]

def achar(ls, padrao, depois=False, ini=0):
    """números da linha que contém o padrão (ou da linha seguinte, quando o valor vem embaixo do título)"""
    rx = re.compile(padrao, re.I)
    for i in range(ini, len(ls)):
        if rx.search(ls[i]):
            if depois:
                for j in range(i + 1, min(i + 4, len(ls))):
                    v = nums(ls[j])
                    if v:
                        return v
                return []
            return nums(ls[i])
    return []

def periodo_texto(ls):
    for l in ls[:12]:
        if re.search(r'\b(JANEIRO|FEVEREIRO|MARÇO|ABRIL|MAIO|JUNHO|JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO)\b.*\d{4}', l):
            return l.strip(';').lower()
    return ''


def ler_rcl(t):
    ls = linhas(t)
    v = achar(ls, r'^RECEITA CORRENTE L[ÍI]QUIDA \(III\)')
    vp = achar(ls, r'LIMITES DA DESPESA COM PESSOAL \(VIII\)')
    return {'rcl': v[-2] if len(v) >= 2 else 0, 'rcl_ajustada_pessoal': vp[-2] if len(vp) >= 2 else 0}


def ler_pessoal(t):
    ls = linhas(t)
    dtp = achar(ls, r'DESPESA TOTAL COM PESSOAL - DTP')
    rcl = achar(ls, r'^RECEITA CORRENTE L[ÍI]QUIDA - RCL')
    rcla = achar(ls, r'RECEITA CORRENTE L[ÍI]QUIDA AJUSTADA PARA C[ÁA]LCULO DOS LIMITES DA DESPESA COM PESSOAL')
    mx, pr, al = achar(ls, r'^LIMITE M[ÁA]XIMO'), achar(ls, r'^LIMITE PRUDENCIAL'), achar(ls, r'^LIMITE DE ALERTA')
    return {'periodo': periodo_texto(ls), 'valor': dtp[0] if dtp else 0, 'pct': dtp[1] if len(dtp) > 1 else 0,
            'rcl': rcl[0] if rcl else 0, 'rcl_ajustada': rcla[0] if rcla else 0,
            'max': mx[-1] if mx else 54, 'prudencial': pr[-1] if pr else 51.3, 'alerta': al[-1] if al else 48.6}


def ler_saude(t):
    ls = linhas(t)
    base = achar(ls, r'TOTAL DAS RECEITAS RESULTANTES DE IMPOSTOS E TRAN')
    apl = achar(ls, r'\(=\) VALOR APLICADO EM ASPS', depois=True)
    mini = achar(ls, r'Despesa M[íi]nima a ser Aplicada em ASPS.*15%', depois=True)
    pct = achar(ls, r'^PERCENTUAL DA RECEITA DE IMPOSTOS E TRANSFER[ÊE]NCIAS CONSTITUCIONAIS E LEGAIS APLICADO EM ASPS', depois=True)
    tot = [num(x) for x in (next((l for l in ls if re.search(r'TOTAL DAS DESPESAS COM SA[ÚU]DE\s*\(XLVII\)', l)), '')).split(';') if re.match(r'^\(?[\d.]+,\d\d\)?$', x.strip())]
    return {'periodo': periodo_texto(ls), 'base': base[2] if len(base) > 2 else 0, 'aplicado': apl[0] if apl else 0,
            'liquidado': apl[1] if len(apl) > 1 else 0, 'pct': pct[0] if pct else 0, 'pct_liq': pct[1] if len(pct) > 1 else 0,
            'minimo': mini[0] if mini else 0, 'total_saude_todas_fontes': tot[0] if tot else 0}


def ler_mde(t):
    ls = linhas(t)
    base = achar(ls, r'^3 - TOTAL DA RECEITA RESULTANTE DE IMPOSTOS')
    m = achar(ls, r'^29 - APLICA[ÇC][ÃA]O EM MDE')
    f = achar(ls, r'^15 - M[íi]nimo de 70% do FUNDEB')
    return {'periodo': periodo_texto(ls), 'base': base[-1] if base else 0, 'exigido': m[0] if m else 0,
            'aplicado': m[1] if len(m) > 1 else 0, 'pct': m[2] if len(m) > 2 else 0,
            'fundeb70': {'exigido': f[0] if f else 0, 'aplicado': f[1] if len(f) > 1 else 0, 'pct': f[-1] if f else 0}}


def ler_dcl(t, quad):
    ls = linhas(t)
    col = lambda p: (lambda v: v[quad] if len(v) > quad else 0)(achar(ls, p))
    comp = []
    for nome, p in [('Parcelamento de contribuições previdenciárias', r'^De Contribui[çc][õo]es Previdenci'),
                    ('Parcelamento de tributos', r'^De Tributos;'), ('Parcelamento de FGTS', r'^Do FGTS;'),
                    ('Precatórios vencidos e não pagos', r'^Precat[óo]rios Posteriores.*Vencidos'),
                    ('Empréstimos internos', r'^Empr[ée]stimos;'), ('Financiamentos', r'^Financiamentos;'),
                    ('Dívida mobiliária', r'^D[íi]vida Mobili[áa]ria'), ('Outras dívidas', r'^(Demais D[íi]vidas Contratuais|Outras D[íi]vidas);')]:
        v = col(p)
        if abs(v) > 0.004:
            comp.append([nome, v])
    return {'periodo': periodo_texto(ls), 'dc': col(r'^D[ÍI]VIDA CONSOLIDADA - DC \(I\)'), 'caixa': col(r'^Disponibilidade de Caixa;'),
            'dcl': col(r'^D[ÍI]VIDA CONSOLIDADA L[ÍI]QUIDA \(DCL\)'), 'rcl_ajustada': col(r'^RECEITA CORRENTE L[ÍI]QUIDA AJUSTADA PARA C[ÁA]LCULO DOS LIMITES DE ENDIVIDAMENTO'),
            'pct_dc': col(r'^% da DC sobre a RCL'), 'pct_dcl': col(r'^% da DCL sobre a RCL'), 'limite_pct': 120, 'composicao': comp}


FUNCOES = {'SAÚDE': 'Saúde', 'EDUCAÇÃO': 'Educação', 'ADMINISTRAÇÃO': 'Administração', 'TRANSPORTE': 'Transporte', 'URBANISMO': 'Urbanismo',
           'ASSISTÊNCIA SOCIAL': 'Assistência social', 'LEGISLATIVA': 'Legislativo (Câmara)', 'DESPORTO E LAZER': 'Desporto e lazer',
           'GESTÃO AMBIENTAL': 'Gestão ambiental', 'ENCARGOS ESPECIAIS': 'Encargos especiais', 'CULTURA': 'Cultura', 'AGRICULTURA': 'Agricultura',
           'ENERGIA': 'Energia', 'DIREITOS DA CIDADANIA': 'Direitos da cidadania', 'COMÉRCIO E SERVIÇOS': 'Comércio e serviços',
           'HABITAÇÃO': 'Habitação', 'SANEAMENTO': 'Saneamento', 'SEGURANÇA PÚBLICA': 'Segurança pública', 'PREVIDÊNCIA SOCIAL': 'Previdência social',
           'TRABALHO': 'Trabalho', 'INDÚSTRIA': 'Indústria', 'COMUNICAÇÕES': 'Comunicações', 'JUDICIÁRIA': 'Judiciária', 'ESSENCIAL À JUSTIÇA': 'Essencial à justiça',
           'CIÊNCIA E TECNOLOGIA': 'Ciência e tecnologia', 'ORGANIZAÇÃO AGRÁRIA': 'Organização agrária', 'RELAÇÕES EXTERIORES': 'Relações exteriores', 'DEFESA NACIONAL': 'Defesa nacional'}

def ler_funcoes(t):
    ls = linhas(t); itens = []; tot = {}
    for l in ls:
        p = l.split(';')
        if p and p[0] in FUNCOES:
            v = nums(l)
            if len(v) >= 7 and v[3] > 0:
                itens.append([FUNCOES[p[0]], v[3]])
        elif l.startswith('TOTAL III'):
            v = nums(l)
            if len(v) >= 9:
                tot = {'dot': v[1], 'total_emp': v[3], 'total_liq': v[7]}
    itens.sort(key=lambda x: -x[1])
    return {**tot, 'itens': itens}


# ---------------------------------------------------------------- Anexo 10
def _cat(cod):
    """categoria de cada natureza de receita (pelo código do ementário)"""
    c = cod
    R = [('1.1.1.2.50', 'IPTU', 'proprio'), ('1.1.1.2.53', 'ITBI', 'proprio'), ('1.1.1.3.03', 'IRRF (retido na fonte)', 'proprio'),
         ('1.1.1.4.51', 'ISS', 'proprio'), ('1.1.2', 'Taxas', 'proprio'), ('1.2.4', 'Contribuição de iluminação pública (COSIP)', 'proprio'),
         ('1.3', 'Rendimentos de aplicações e patrimônio', 'proprio'), ('1.6', 'Receita de serviços', 'proprio'),
         ('1.9', 'Outras receitas correntes (multas, restituições)', 'proprio'), ('1.1', 'Outros impostos e contribuições', 'proprio'),
         ('1.2', 'Outros impostos e contribuições', 'proprio'), ('1.4', 'Outras receitas correntes (multas, restituições)', 'proprio'),
         ('1.5', 'Outras receitas correntes (multas, restituições)', 'proprio'),
         ('1.7.1.1.51', 'FPM (Fundo de Participação dos Municípios)', 'transf'), ('1.7.1.1.52', 'ITR', 'transf'),
         ('1.7.1.3', 'SUS (União)', 'transf'), ('1.7.1.4', 'FNDE (salário-educação, PNAE, PNATE)', 'transf'),
         ('1.7.1', 'Outras transferências da União', 'transf'), ('1.7.2.1.50', 'ICMS (cota-parte)', 'transf'),
         ('1.7.2.1.51', 'IPVA (cota-parte)', 'transf'), ('1.7.2.1.52', 'IPI-Exportação', 'transf'), ('1.7.2', 'Outras transferências do Estado', 'transf'),
         ('1.7.5', 'FUNDEB', 'transf'), ('1.7', 'Outras transferências correntes', 'transf'),
         ('2.2', 'Alienação de bens', 'capital'), ('2.4', 'Transferências de capital (convênios e obras)', 'capital'), ('2', 'Outras receitas de capital', 'capital')]
    for p, nome, tipo in R:
        if c == p or c.startswith(p + '.'):
            return nome, tipo
    return 'Outras receitas', 'proprio'

_GRUPO_DA = [('1.1.1.2.50', 'IPTU'), ('1.1.1.4.51', 'ISS'), ('1.1.2', 'Taxas'), ('1.2.4', 'COSIP')]

def ler_anexo10(t):
    ls = linhas(t)
    grupos, cats, da = [], {}, {}
    ded = None
    for l in ls:
        p = l.split(';')
        if re.match(r'^\d\d$', p[0]) and len(p) >= 4:
            v = [num(x) for x in p[2:4]]
            if len(v) >= 2 and not any(g[0] == 'G' + p[0] for g in grupos):
                grupos.append(['G' + p[0], p[1].strip(), v[0], v[1]])
        elif l.startswith('Deduções de Receita para a Formação do FUNDEB') and ded is None and grupos:
            v = nums(l); ded = ['GDED', 'Deduções para formação do FUNDEB', v[0], v[1]]
        elif l.startswith('TOTAL;') and ded is not None and not any(g[0] == 'GDED' for g in grupos):
            grupos.insert(next((i for i, g in enumerate(grupos) if g[0] > 'G17'), len(grupos)), ded)
        m = re.match(r'^(\d(?:\.\d+){9})\.?;', l)
        if m:
            v = nums(l)
            if len(v) < 2:
                continue
            cod = m.group(1); nome, tipo = _cat(cod)
            k = cats.setdefault(nome, {'nome': nome, 'tipo': tipo, 'prev': 0.0, 'arr': 0.0}); k['prev'] += v[0]; k['arr'] += v[1]
            seg = cod.split('.')
            if len(seg) > 6 and seg[6] in ('3', '4'):          # dívida ativa (principal e multas/juros)
                g = next((n for pf, n in _GRUPO_DA if cod.startswith(pf + '.')), 'Outras')
                d = da.setdefault(g, [0.0, 0.0]); d[0] += v[0]; d[1] += v[1]
    tot = achar(ls, r'^TOTAL;')
    r2 = lambda x: round(x, 2)
    return {'grupos': [[a, b, r2(c), r2(d)] for a, b, c, d in grupos],
            'cat': [{**k, 'prev': r2(k['prev']), 'arr': r2(k['arr'])} for k in cats.values()],
            'divida_ativa': {g: [r2(a), r2(b)] for g, (a, b) in da.items()},
            'total': tot[:2]}


# ---------------------------------------------------------------- montagem
def periodos(hoje):
    m = hoje.month; a = hoje.year
    bim = (m - 1) // 2                       # último bimestre fechado
    quad = (m - 1) // 4                      # último quadrimestre fechado
    mes = m - 1                              # último mês fechado
    return {'bim': (a, bim) if bim else (a - 1, 6), 'quad': (a, quad) if quad else (a - 1, 3),
            'mes': (a, mes) if mes else (a - 1, 12), 'bim_atual': (a, (m + 1) // 2)}


def gerar(saida, avisar=print, hoje=None):
    hoje = hoje or date.today(); ano = hoje.year; P = periodos(hoje)
    gerado = hoje.strftime('%d/%m/%Y'); m = hoje.month
    os.makedirs(saida, exist_ok=True)

    # ---- receitas
    avisar('Receitas: Anexo 10 e arrecadação mensal…')
    a_at, a_ant, a_ant_ano = ler_anexo10(anexo10(ano, 1, m)), ler_anexo10(anexo10(ano - 1, 1, m)), ler_anexo10(anexo10(ano - 1, 1, 12))
    soma = sum(g[3] for g in a_at['grupos'])
    if a_at['total'] and abs(soma - a_at['total'][1]) > 1:
        raise RuntimeError(f'Anexo 10: soma dos grupos ({soma:.2f}) não bate com o total ({a_at["total"][1]:.2f})')
    mes_at, mes_ant = arrecadacao_mensal(ano), arrecadacao_mensal(ano - 1)
    if mes_at and abs(sum(x[1] for x in mes_at) - soma) > 1:
        avisar(f'Aviso: arrecadação mensal ({sum(x[1] for x in mes_at):.2f}) difere do Anexo 10 ({soma:.2f}).')
    rec = {'gerado': gerado, 'ano': ano, 'mes': m,
           'fonte': f'Portal da Transparência de Leópolis — Anexo 10 (comparativo da receita prevista com a arrecadada, previsão atualizada, jan. a {MES_ABREV[m - 1]}.) e Receita Arrecadada por mês. Município de Leópolis (entidade 300).',
           'meses26': mes_at, 'meses25': mes_ant, 'grupos26': a_at['grupos'], 'grupos25': a_ant['grupos'],
           'cat26': a_at['cat'], 'cat25': a_ant['cat'], 'cat25ano': a_ant_ano['cat']}
    with open(os.path.join(saida, 'receitas.json'), 'w', encoding='utf-8') as f:
        json.dump(rec, f, ensure_ascii=False)

    # ---- indicadores
    avisar('Indicadores da LRF: saúde, educação, pessoal, dívida e despesa por função…')
    (ab, bim), (aq, quad), (am, mes), (aa, bat) = P['bim'], P['quad'], P['mes'], P['bim_atual']
    saude = ler_saude(lrf('receitaDespesaAcoesSaude', 2, bim, ano=ab, layout=2))
    mde = ler_mde(lrf('receitaDespesaManutencaoDesenvEnsino', 2, bim, ano=ab, layout=2))
    rcl = ler_rcl(lrf('receitaCorrenteLiquida', 1, mes, ano=am))
    pe = ler_pessoal(lrf('despesaComPessoal', 1, mes, entidades=(300,), ano=am))
    pt = ler_pessoal(lrf('despesaComPessoal', 1, mes, entidades=(304, 300), ano=am))
    # evolução: dezembro do ano anterior (como o ano fechou) e depois todos os meses fechados do ano.
    # Meses com mais de 2 meses de idade são reaproveitados da rodada anterior (o portal não muda mais).
    hist = []
    try:
        antes = {r[0]: r[1] for r in json.load(open(os.path.join(saida, 'indicadores.json'), encoding='utf-8'))['pessoal']['historico']}
    except Exception:
        antes = {}
    pontos = [(am - 1, 12)] + [(am, x) for x in range(1, mes + 1)]
    for (a, mm) in pontos:
        rot = f'{MES_ABREV[mm - 1]}/{str(a)[2:]}'
        recente = (a, mm) >= ((am, mes - 2) if mes > 2 else (am - 1, 10 + mes))
        if rot in antes and not recente:
            hist.append([rot, antes[rot]]); continue
        try:
            v = pe if (a, mm) == (am, mes) else ler_pessoal(lrf('despesaComPessoal', 1, mm, entidades=(300,), ano=a))
            hist.append([rot, v['pct']])
        except Exception as e:
            avisar(f'Aviso: pessoal {mm}/{a} não veio ({e}).')
    dcl = ler_dcl(lrf('dividaConsolidadaLiquida', 3, quad, ano=aq), quad)
    func = ler_funcoes(lrf('despesaFuncao', 2, bat, ano=aa))
    fim_bim = MESES[2 * bim - 1].lower()
    saude['periodo'] = mde['periodo'] = f'janeiro a {fim_bim} de {ab} ({bim}º bimestre)'
    pe['periodo'] = f"{pe['periodo']} (últimos 12 meses)" if pe['periodo'] else f'12 meses até {MESES[mes - 1].lower()}/{am}'
    dcl['periodo'] = f'até {MESES[4 * quad - 1].lower()} de {aq} ({quad}º quadrimestre)'
    for nome, v in (('saúde', saude['pct']), ('educação', mde['pct']), ('pessoal', pe['pct']), ('RCL', rcl['rcl'])):
        if not v:
            raise RuntimeError(f'Indicadores: valor de {nome} não encontrado no relatório do portal')

    # ---- dívida ativa: recebido (Anexo 10) e saldo a receber (consulta pública, só totais)
    avisar('Dívida ativa: saldo a receber por ano de inscrição…')
    acum = {}
    for a in range(2015, ano + 1):
        try:
            acum[a] = inscritos_divida_ativa(a)
        except Exception as e:
            avisar(f'Aviso: dívida ativa {a} não veio ({e}).')
    est = {}
    if ano in acum:
        vs = sorted(acum[ano], reverse=True); tot = sum(vs)
        s = {a: sum(v) for a, v in acum.items()}
        def entre(a1, a2):
            return s.get(a2, 0) - s.get(a1, 0) if a1 in s and a2 in s else 0
        idade = [['Até 2015', s.get(2015, 0)], ['2016 a 2020', entre(2015, 2020)], ['2021 a 2023', entre(2020, 2023)]]
        idade += [[str(a), entre(a - 1, a)] for a in range(2024, ano - 1)]
        idade += [[f'{ano - 1} e {ano}', entre(ano - 2, ano)]]
        faixas = [['Até R$ 500', lambda v: v <= 500], ['R$ 500 a 2 mil', lambda v: 500 < v <= 2000],
                  ['R$ 2 mil a 10 mil', lambda v: 2000 < v <= 10000], ['Acima de R$ 10 mil', lambda v: v > 10000]]
        est = {'total': round(tot, 2), 'contribuintes': len(vs), 'mediana': round(vs[len(vs) // 2], 2) if vs else 0,
               'maiores2': round(sum(vs[:2]), 2),
               'faixas': [[n, sum(1 for v in vs if f(v)), round(sum(v for v in vs if f(v)), 2)] for n, f in faixas],
               'idade': [[n, round(v, 2)] for n, v in idade if abs(v) > 0.004]}
    tot_da = lambda d: round(sum(v[1] for v in d.values()), 2)

    ind = {'gerado': gerado, 'ano': ano,
           'saude': saude, 'educacao': mde,
           'pessoal': {'periodo': pe['periodo'], 'rcl': rcl['rcl'] or pe['rcl'], 'rcl_ajustada': pe['rcl_ajustada'],
                       'executivo': {'valor': pe['valor'], 'pct': pe['pct'], 'max': pe['max'], 'prudencial': pe['prudencial'], 'alerta': pe['alerta']},
                       'camara': {'valor': round(pt['valor'] - pe['valor'], 2), 'pct': round((pt['valor'] - pe['valor']) / pe['rcl_ajustada'] * 100, 2) if pe['rcl_ajustada'] else 0, 'max': 6},
                       'consolidado': {'valor': pt['valor'], 'pct': pt['pct'], 'max': 60}, 'historico': hist},
           'divida': dcl,
           'divida_ativa': {'periodo_atual': f'Jan–{MES_ABREV[m - 1]} {ano}', 'periodo_anterior': f'Jan–{MES_ABREV[m - 1]} {ano - 1}',
                            'recebido': {'atual': a_at['divida_ativa'], 'anterior': a_ant['divida_ativa'], 'anterior_ano': a_ant_ano['divida_ativa']},
                            'recebido_total': {'atual': tot_da(a_at['divida_ativa']), 'anterior': tot_da(a_ant['divida_ativa']), 'anterior_ano': tot_da(a_ant_ano['divida_ativa'])},
                            'estoque': est},
           'funcoes': {'periodo': f'até {gerado}', **func},
           'fonte': 'Portal da Transparência de Leópolis: RREO Anexos 2, 3, 8 e 12; RGF Anexos 1 e 2; Anexo 10; consulta Inscritos em Dívida Ativa.'}
    with open(os.path.join(saida, 'indicadores.json'), 'w', encoding='utf-8') as f:
        json.dump(ind, f, ensure_ascii=False)
    avisar(f"Receitas e indicadores: arrecadado {soma:,.2f}; saúde {saude['pct']}%, educação {mde['pct']}%, pessoal {pe['pct']}%.")
    return rec, ind


if __name__ == '__main__':
    gerar(sys.argv[1] if len(sys.argv) > 1 else '.')
