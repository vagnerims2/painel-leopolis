"""Resumo semanal em PDF (uma página) para a chefia, a partir dos CSVs gerados pelo build.py.
Uso: python3 resumo_semanal.py <pasta_saida_do_build> <arquivo.pdf>
"""
import csv, io, json, os, re, statistics, sys, unicodedata
from collections import defaultdict
from datetime import date, timedelta

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except ImportError:  # instala na hora se faltar
    os.system(f'{sys.executable} -m pip install -q --break-system-packages reportlab matplotlib')
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

SAIDA, PDF = sys.argv[1], sys.argv[2]
ler = lambda n: list(csv.DictReader(open(os.path.join(SAIDA, n), encoding='utf-8')))
f = lambda x: float(x or 0)
def brl(v, casas=2):
    s = f'{v:,.{casas}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return 'R$ ' + s
def br(d): return '/'.join(reversed(d.split('-'))) if d else ''

E, MOV, DOT, FON, IT = ler('empenhos.csv'), ler('movimento.csv'), ler('dotacoes.csv'), ler('saldo_fontes.csv'), ler('itens.csv')
fim = max(r['data'] for r in MOV); ini = (date.fromisoformat(fim) - timedelta(days=6)).isoformat()
sem = sorted([r for r in MOV if r['data'] >= ini], key=lambda r: r['data'])
emp_s, liq_s, pag_s = (sum(f(r[k]) for r in sem) for k in ('empenhado_liquido', 'liquidado', 'pago'))
emp_n = sum(1 for r in E if ini <= r['data'] <= fim)
saldo = sum(f(r['saldo_a_pagar']) for r in FON)
falta = sum(f(r['falta_liquidar']) for r in E); lnp = sum(f(r['liquidado_nao_pago']) for r in E)

# ---- estilos
AZ, AZ2, AZ3, CINZA = colors.HexColor('#1b2a47'), colors.HexColor('#1f4e8c'), colors.HexColor('#93c0ee'), colors.HexColor('#605e5c')
st = lambda **k: ParagraphStyle('x', fontName=k.pop('font', 'Helvetica'), **k)
H1, H2, P, PS, NUM = st(fontSize=15, leading=18, textColor=colors.white, font='Helvetica-Bold'), st(fontSize=10.5, leading=13, textColor=AZ, font='Helvetica-Bold', spaceBefore=6, spaceAfter=3), st(fontSize=8.5, leading=11), st(fontSize=7.5, leading=9.5, textColor=CINZA), st(fontSize=13, leading=15, font='Helvetica-Bold', textColor=AZ)

def tabela(linhas, larg, cab=True, alinhar_dir=()):
    t = Table(linhas, colWidths=larg, repeatRows=1 if cab else 0)
    s = [('FONT', (0, 0), (-1, -1), 'Helvetica', 7.6), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5), ('TOPPADDING', (0, 0), (-1, -1), 2.5),
         ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#e1dfdd'))]
    if cab: s += [('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 7.6), ('LINEBELOW', (0, 0), (-1, 0), 0.8, AZ2), ('TEXTCOLOR', (0, 0), (-1, 0), AZ)]
    for c in alinhar_dir: s.append(('ALIGN', (c, 0), (c, -1), 'RIGHT'))
    t.setStyle(TableStyle(s)); return t
corta = lambda t, n: (t[:n - 1] + '…') if len(t) > n else t

doc = SimpleDocTemplate(PDF, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=10 * mm, bottomMargin=10 * mm, title='Resumo semanal - Empenhos Leópolis')
W = A4[0] - 24 * mm; story = []
cab = Table([[Paragraph(f'Resumo semanal de empenhos — semana de {br(ini)} a {br(fim)}', H1)],
             [Paragraph(f'Prefeitura Municipal de Leópolis · dados do Portal da Transparência até {br(fim)} · gerado em {date.today().strftime("%d/%m/%Y")}', st(fontSize=8, textColor=colors.HexColor('#d5ddec')))]], colWidths=[W])
cab.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), AZ), ('LEFTPADDING', (0, 0), (-1, -1), 8), ('TOPPADDING', (0, 0), (0, 0), 7), ('BOTTOMPADDING', (0, -1), (-1, -1), 7), ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#f2c811'))]))
story += [cab, Spacer(1, 6)]

kp = [('Empenhado na semana', brl(emp_s, 0), f'{emp_n} empenhos'), ('Liquidado na semana', brl(liq_s, 0), 'inclui restos a pagar'), ('Pago na semana', brl(pag_s, 0), 'inclui restos a pagar'),
      ('Saldo a pagar (oficial)', brl(saldo, 0), f'falta liquidar {brl(falta, 0)} · liq. não pago {brl(lnp, 0)}')]
kt = Table([[[Paragraph(a, PS), Paragraph(b, NUM), Paragraph(c, PS)] for a, b, c in kp]], colWidths=[W / 4] * 4)
kt.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#e1dfdd')), ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e1dfdd')), ('LEFTPADDING', (0, 0), (-1, -1), 6), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
story += [kt, Spacer(1, 5)]

# gráfico dos dias da semana
fig, ax = plt.subplots(figsize=(7.4, 1.7), dpi=200)
x = range(len(sem)); w = 0.26
for i, (k, c, nm) in enumerate([('empenhado_liquido', '#1f4e8c', 'Empenhado'), ('liquidado', '#3d85d8', 'Liquidado'), ('pago', '#93c0ee', 'Pago')]):
    ax.bar([j + (i - 1) * w for j in x], [f(r[k]) / 1000 for r in sem], w, color=c, label=nm)
ax.set_xticks(list(x)); ax.set_xticklabels([br(r['data'])[:5] for r in sem], fontsize=7); ax.tick_params(axis='y', labelsize=7); ax.set_ylabel('R$ mil', fontsize=7)
for s_ in ('top', 'right'): ax.spines[s_].set_visible(False)
ax.legend(fontsize=7, frameon=False, ncol=3, loc='upper left'); ax.grid(axis='y', color='#eeeeee'); fig.tight_layout()
buf = io.BytesIO(); fig.savefig(buf, format='png'); plt.close(fig); buf.seek(0)
story += [Image(buf, width=W, height=W * 1.7 / 7.4)]

# alertas: empenhos parados
par = [r for r in E if r['tipo'] == 'Ordinário' and f(r['liquidado']) == 0 and f(r['saldo_a_pagar']) > 0 and int(r['dias'] or 0) >= 10]
fx = lambda a, b: sum(1 for r in par if a <= int(r['dias']) < b)
story.append(Paragraph(f'Empenhos sem nenhuma liquidação: {len(par)} — {fx(10, 20)} com 10 a 19 dias, {fx(20, 30)} com 20 a 29 dias e {fx(30, 9999)} com 30 dias ou mais', H2))
top = sorted(par, key=lambda r: -f(r['saldo_a_pagar']))[:8]
story.append(tabela([['Empenho', 'Data', 'Dias', 'Fornecedor', 'Secretaria', 'Saldo']] + [[r['empenho'], br(r['data']), r['dias'], corta(r['fornecedor'], 38), corta(r['secretaria'], 28), brl(f(r['saldo_a_pagar']))] for r in top],
                    [16 * mm, 18 * mm, 11 * mm, 70 * mm, 50 * mm, W - 165 * mm], alinhar_dir=(2, 5)))
story.append(Paragraph('Os 8 de maior valor. A lista completa está na aba Alertas do painel.', PS))

# dotações
dm = sorted([r for r in DOT if r['recorrente'] == 'Sim' and f(r['falta_fechar_mes']) > 0], key=lambda r: -f(r['falta_fechar_mes']))
story.append(Paragraph(f'Dotações recorrentes que não fecham o mês: {len(dm)} — falta {brl(sum(f(r["falta_fechar_mes"]) for r in dm), 0)} para fechar o mês', H2))
story.append(tabela([['Dotação', 'Secretaria', 'Elemento', 'Fonte', 'Saldo', 'Falta p/ o mês']] + [[r['dotacao'], corta(r['secretaria'], 18), corta(r['tipo_despesa'], 34), corta(r['fonte'], 20), brl(f(r['saldo_atual'])), brl(f(r['falta_fechar_mes']))] for r in dm[:8]],
                    [14 * mm, 34 * mm, 58 * mm, 34 * mm, 22 * mm, W - 162 * mm], alinhar_dir=(4, 5)))

# limite de dispensa (mesmas regras da aba Licitações)
LIM_I, LIM_II = 130984.20, 65492.11
fora = re.compile(r'ENERGIA|ÁGUA E ESGOTO|BANCÁRIO|JUDICI|POSTAIS|ANUIDADE|TELEFON|MÉDIA E ALTA COMPLEXIDADE|PEDÁGIO|SEGURO', re.I)
publico = re.compile(r'CONS[OÓ]RCIO|MUNIC[IÍ]PIO|INSTITUTO NACIONAL|CAIXA ECON|BANCO DO BRASIL|COPEL|SANEPAR|ESTADO D|FUNDO |TRIBUNAL|CORREIOS', re.I)
base = [r for r in E if re.match(r'(Sem licitação|Dispensa)', r['modalidade']) and re.match(r'(3\.3\.90\.(30|32|36|39|40)|4\.4\.90\.(51|52))', r['natureza']) and not fora.search(r['tipo_despesa']) and not publico.search(r['fornecedor'])]
proc = defaultdict(float)
for r in base:
    if r['modalidade'].startswith('Dispensa'): proc[r['licitacao']] += f(r['valor']) - f(r['anulado'])
obj = defaultdict(lambda: [0.0, LIM_II])
for r in base:
    v = f(r['valor']) - f(r['anulado'])
    if (proc[r['licitacao']] if r['modalidade'].startswith('Dispensa') else v) > LIM_I: continue
    inc1 = r['natureza'].startswith('4.4.90.51') or re.search('ENGENHARIA|OBRAS', r['tipo_despesa'], re.I) or (r['natureza'].startswith('3.3.90.39') and re.search('VEÍCULO', r['tipo_despesa'], re.I) and re.search('MANUTEN', r['tipo_despesa'], re.I))
    k = r['tipo_despesa']; obj[k][0] += v; obj[k][1] = LIM_I if inc1 else LIM_II
lim = sorted([(k, v, l, v / l) for k, (v, l) in obj.items() if v / l >= 0.8], key=lambda x: -x[3])
story.append(Paragraph(f'Compras sem licitação/dispensa com 80% ou mais do limite do art. 75 (Decreto 12.807/2025): {len(lim)} objetos', H2))
if lim: story.append(tabela([['Objeto', 'Limite', 'Empenhado no ano', '% do limite']] + [[corta(k, 70), brl(l), brl(v), f'{p * 100:.0f}%'.replace('.', ',')] for k, v, l, p in lim[:6]], [W - 85 * mm, 25 * mm, 35 * mm, 25 * mm], alinhar_dir=(1, 2, 3)))

# preços acima do padrão na semana
g = defaultdict(list)
chave = lambda t: re.sub(r'\s+', ' ', unicodedata.normalize('NFD', t.lower()).encode('ascii', 'ignore').decode()).strip()
for r in IT:
    if r['situacao'] != 'Anulado' and f(r['valor_unitario']) > 0: g[chave(r['produto'])].append(r)
alto = []
for rs in g.values():
    if len(rs) < 3: continue
    med = statistics.median(f(r['valor_unitario']) for r in rs)
    alto += [(r, med) for r in rs if ini <= r['data'] <= fim and f(r['valor_unitario']) > med * 1.2]
alto.sort(key=lambda x: -(f(x[0]['valor_unitario']) / x[1]))
story.append(Paragraph(f'Itens empenhados na semana com preço 20% ou mais acima da mediana do ano: {len(alto)}', H2))
if alto: story.append(tabela([['Produto', 'Empenho', 'Fornecedor', 'Pago', 'Mediana', 'Acima']] + [[corta(r['produto'], 42), r['empenho'], corta(r['fornecedor'], 30), brl(f(r['valor_unitario'])), brl(m), f'+{(f(r["valor_unitario"]) / m - 1) * 100:.0f}%'] for r, m in alto[:6]],
                                 [62 * mm, 15 * mm, 50 * mm, 22 * mm, 22 * mm, W - 171 * mm], alinhar_dir=(3, 4, 5)))
story += [Spacer(1, 6), Paragraph('Fonte: Portal da Transparência do Município de Leópolis (Equiplano). Documento informativo gerado automaticamente; em caso de divergência, vale o sistema oficial. Painel interno: vagnerims2.github.io/painel-leopolis/interno/', PS)]
doc.build(story)
print('ok', PDF)
