"""Relatório semanal de requisições em atraso, por fornecedor, enviado por e-mail (dois PDFs: 31 a 90 dias e mais de 90 dias).

Usa os mesmos dados e a mesma regra da aba Requisições da versão dos servidores:
  - planilha de requisições: data/planilha.enc.json (aberta com a senha dos servidores, segredo PAINEL_SENHA)
  - empenhos, liquidações e notas fiscais: data/*.csv (Portal da Transparência)
  - atraso = dias desde o envio marcado na planilha (ou desde a requisição, para as enviadas antes do controle),
    só para as requisições em aberto (não concluídas, não canceladas, já enviadas).

Uso:  python ferramentas/relatorio_atraso.py <pasta_do_site> <pasta_saida> [--enviar]
E-mail (segredos do GitHub): GMAIL_USUARIO, GMAIL_SENHA_APP, RELATORIO_PARA (vários separados por vírgula; padrão = GMAIL_USUARIO).
Sem a senha da planilha ou sem os dados do Gmail, avisa e não envia (o resto da atualização continua normal).
"""
import base64, csv, json, os, re, smtplib, ssl, sys
from collections import defaultdict
from datetime import date
from email.message import EmailMessage

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


# ---------------------------------------------------------------- dados
def decifrar(pacote, senha):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    b = lambda k: base64.b64decode(pacote[k])
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b('sal'), iterations=int(pacote['iter'])).derive(senha.encode('utf-8'))
    return json.loads(AESGCM(chave).decrypt(b('iv'), b('dados'), None).decode('utf-8'))

N = lambda x: float(x or 0)
semz = lambda v: re.sub(r'^0+(?=\d)', '', str(v or '').strip())
def dmy(s):
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})', str(s or '')); return f'{m[3]}-{m[2]}-{m[1]}' if m else ''
def br(d): return '/'.join(reversed(d.split('-'))) if re.match(r'^\d{4}-\d\d-\d\d$', d or '') else (d or '')
def brl(v): return 'R$ ' + f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
def dias(iso, hoje): return (hoje - date.fromisoformat(iso)).days


def trilha(l, emp_map, tem_re, re_map):
    """mesma regra da página (função trilha): onde a requisição está parada"""
    if not l['e'] and l.get('re') and len(re_map.get(semz(l['re']), [])) == 1:
        l = {**l, 'e': semz(re_map[semz(l['re'])][0]['empenho'])}
    e = emp_map.get(l['e']) if l['e'] else None
    re_num = l.get('re') or (e and e.get('requisicao_empenho')) or ''
    cancel = re.search('CANCELAD', f"{l.get('et', '')} {l.get('st', '')}", re.I) and not (e and N(e['liquidado']) > 0)
    if cancel: return 'Cancelada', e, re_num
    if not l['e']:
        return ('Aguardando requisição de empenho' if (tem_re and not re_num) else 'Aguardando empenho'), e, re_num
    if not e: return 'Empenho não achado no portal', e, re_num
    if e['situacao'] == 'Anulado': return 'Empenho anulado', e, re_num
    _val, liq, pag, falta = N(e['valor']), N(e['liquidado']), N(e['pago']), N(e['falta_liquidar'])
    if liq <= 0.004: return 'Aguardando liquidação', e, re_num
    if falta > 0.004: return 'Liquidação parcial', e, re_num
    if pag <= 0.004: return 'Aguardando pagamento', e, re_num
    if pag < liq - 0.004: return 'Pagamento parcial', e, re_num
    return 'Concluída', e, re_num


def requisicoes_em_atraso(site, senha, hoje):
    aberta = os.path.join(site, 'data', 'planilha.json')
    if os.path.exists(aberta):                          # planilha publicada sem senha (desde 22/10/2026)
        plan = json.load(open(aberta, encoding='utf-8'))
    else:
        plan = decifrar(json.load(open(os.path.join(site, 'data', 'planilha.enc.json'), encoding='utf-8')), senha)
    ler = lambda n: list(csv.DictReader(open(os.path.join(site, 'data', n), encoding='utf-8')))
    emps, notas = ler('empenhos.csv'), (ler('notas.csv') if os.path.exists(os.path.join(site, 'data', 'notas.csv')) else [])
    emp_map, re_map = {}, defaultdict(list)
    for r in emps:
        emp_map[semz(r['empenho'])] = r
        if r.get('requisicao_empenho'): re_map[semz(r['requisicao_empenho'])].append(r)
    nf_emp = defaultdict(list)
    for n in notas:
        if n.get('empenho'): nf_emp[semz(n['empenho'])].append(n)
    linhas = plan.get('linhas', [])
    tem_re = any(l.get('re') for l in linhas)
    out = []
    for l0 in linhas:
        l = {**l0, 'e': semz(l0.get('e', ''))}
        parada, e, re_num = trilha(l, emp_map, tem_re, re_map)
        if parada in ('Cancelada', 'Empenho anulado', 'Concluída'): continue
        env = l.get('env') or ''
        if not env: continue                                   # ainda não enviada ao fornecedor: não conta atraso
        ini = env if re.match(r'^\d{4}-\d\d-\d\d$', env) else dmy(l.get('d'))
        if not ini: continue
        atraso = dias(ini, hoje)
        en = semz(e['empenho']) if e else l['e']
        nfs = nf_emp.get(en, []) if en else []
        out.append({'fornecedor': (e['fornecedor'] if e else '') or l.get('f') or '—', 'telefone': l.get('t', ''), 'email': l.get('em', ''),
                    'req': l.get('r', ''), 'data_req': l.get('d', ''), 'memo': l.get('m', ''), 'secretaria': l.get('s', ''),
                    'req_empenho': re_num, 'empenho': en, 'data_empenho': br(e['data']) if e else '',
                    'valor': N(e['valor']) if e else 0, 'falta_liquidar': N(e['falta_liquidar']) if e else 0,
                    'liquidado_a_pagar': N(e['liquidado_nao_pago']) if e else 0,
                    'notas': '; '.join(f"{n['tipo']} {n['numero']} ({brl(N(n['valor']))})" for n in nfs) or '—',
                    'parada': parada, 'atraso': atraso, 'desde': br(ini) if re.match(r'^\d{4}', env) else f'{br(ini)} (req.)'})
    return out, plan.get('atualizado', '')


# ---------------------------------------------------------------- PDF
from urllib.parse import quote
from xml.sax.saxutils import escape

def fone_br(t):
    """(44) 99814-3205 e o número com DDI para os links"""
    d = re.sub(r'\D', '', t or '')
    if d.startswith('55') and len(d) > 11: d = d[2:]
    if d.startswith('0'): d = d.lstrip('0')
    if len(d) not in (10, 11): return (t or '').strip(), ''
    vis = f'({d[:2]}) {d[2:-4]}-{d[-4:]}'
    return vis, '55' + d

def contatos(fornecedor, rs):
    """linha com telefone e e-mail clicáveis (ligar, WhatsApp, e-mail já com assunto e a lista das requisições)"""
    LINK = '<font color="#1a56db"><u>{}</u></font>'
    partes = []
    vis, cod = fone_br(rs[0]['telefone'])
    if vis:
        partes.append(f'Telefone: <b>{escape(vis)}</b>')
        if cod:
            partes.append(f'<a href="tel:+{cod}">{LINK.format("Ligar")}</a>')
            partes.append(f'<a href="https://wa.me/{cod}">{LINK.format("WhatsApp")}</a>')
    em = (rs[0]['email'] or '').strip()
    if em and '@' in em:
        reqs = ', '.join(r['req'] for r in rs)
        assunto = f'Prefeitura de Leópolis - requisição(ões) {reqs} em aberto'
        corpo = 'Prezados,\n\nConsta(m) em aberto na Prefeitura Municipal de Leópolis:\n' + '\n'.join(
            f"- Requisição {r['req']}" + (f" / empenho {r['empenho']}" if r['empenho'] else '') + f" ({r['atraso']} dias desde o envio)" for r in rs) + \
            '\n\nSolicitamos informar a previsão de entrega ou o envio da nota fiscal.\n\nAtenciosamente,'
        href = f'mailto:{em}?subject={quote(assunto)}&body={quote(corpo)}'
        partes.append(f'E-mail: <b>{escape(em)}</b>')
        partes.append(f'<a href="{escape(href)}">{LINK.format("Enviar e-mail")}</a>')
    return ' &nbsp;·&nbsp; '.join(partes) or '<font color="#6b6862">sem telefone e e-mail na planilha</font>'

AZUL = colors.HexColor('#1e3a5f'); CINZA = colors.HexColor('#6b6862'); LINHA = colors.HexColor('#d9d6ce')

def pdf(lista, titulo, arquivo, hoje, plan_atual):
    st = lambda **k: ParagraphStyle('x', **{'fontName': 'Helvetica', 'fontSize': 8, 'leading': 10, **k})
    p, pb, pc = st(), st(fontName='Helvetica-Bold'), st(textColor=CINZA, fontSize=7.5)
    doc = SimpleDocTemplate(arquivo, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=titulo, author='Painel de Empenhos — Prefeitura de Leópolis')
    els = [Paragraph(f'<b>{titulo}</b>', st(fontSize=14, leading=18, textColor=AZUL)),
           Paragraph(f'Prefeitura Municipal de Leópolis · relatório de {hoje.strftime("%d/%m/%Y")} · requisições em aberto, já enviadas ao fornecedor. '
                     f'Atraso contado desde o envio marcado na planilha (ou desde a requisição, nas enviadas antes do controle). '
                     f'Empenho, liquidação, pagamento e notas: Portal da Transparência. Planilha de {plan_atual or "—"}.', pc), Spacer(1, 5 * mm)]
    if not lista:
        els.append(Paragraph('Nenhuma requisição nesta faixa de atraso.', p))
    grupos = defaultdict(list)
    for r in lista: grupos[r['fornecedor']].append(r)
    ordem = sorted(grupos, key=lambda f: (-max(r['atraso'] for r in grupos[f]), f))
    els.append(Paragraph(f'{len(lista)} requisições de {len(grupos)} fornecedores · valor empenhado {brl(sum(r["valor"] for r in lista))}', pb))
    els.append(Spacer(1, 3 * mm))
    larg = [w * mm for w in (20, 18, 40, 18, 26, 26, 50, 38, 20, 17)]
    cab = ['Requisição', 'Memo', 'Secretaria', 'Req. emp.', 'Empenho', 'Valor / falta liq.', 'Nota(s) fiscal(is)', 'Parada em', 'Enviada', 'Atraso']
    for f in ordem:
        rs = sorted(grupos[f], key=lambda r: -r['atraso'])
        topo = Paragraph(f'<b>{f}</b>', st(fontSize=9.5, leading=12, textColor=AZUL))
        contato = Paragraph(contatos(f, rs), st(fontSize=8.5, leading=12))
        dados = [[Paragraph(c, pb) for c in cab]]
        for r in rs:
            dados.append([Paragraph(f"{r['req']}<br/><font color='#6b6862'>{r['data_req']}</font>", p), Paragraph(r['memo'] or '—', p),
                          Paragraph(r['secretaria'] or '—', p), Paragraph(r['req_empenho'] or '—', p),
                          Paragraph(f"{r['empenho'] or '—'}<br/><font color='#6b6862'>{r['data_empenho']}</font>", p),
                          Paragraph(f"{brl(r['valor'])}<br/><font color='#6b6862'>falta {brl(r['falta_liquidar'])}</font>" if r['empenho'] else '—', p),
                          Paragraph(r['notas'], p), Paragraph(r['parada'], p), Paragraph(r['desde'], p), Paragraph(f"<b>{r['atraso']} dias</b>", p)])
        t = Table(dados, colWidths=larg, repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2f7')), ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINHA),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
        els += [KeepTogether([topo, contato, Spacer(1, 1.5 * mm), t]), Spacer(1, 5 * mm)]
    doc.build(els)


# ---------------------------------------------------------------- e-mail
def enviar(arquivos, assunto, corpo):
    usuario, senha = os.environ.get('GMAIL_USUARIO', '').strip(), os.environ.get('GMAIL_SENHA_APP', '').replace(' ', '').strip()
    para = [x.strip() for x in (os.environ.get('RELATORIO_PARA') or usuario).split(',') if x.strip()]
    if not usuario or not senha:
        print('Sem GMAIL_USUARIO/GMAIL_SENHA_APP: relatório gerado, mas não enviado.'); return False
    m = EmailMessage(); m['From'] = f'Painel de Empenhos Leópolis <{usuario}>'; m['To'] = ', '.join(para); m['Subject'] = assunto
    m.set_content(corpo)
    for a in arquivos:
        m.add_attachment(open(a, 'rb').read(), maintype='application', subtype='pdf', filename=os.path.basename(a))
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(usuario, senha); s.send_message(m)
    print('E-mail enviado para', ', '.join(para)); return True


def main():
    site, saida = sys.argv[1], sys.argv[2]; os.makedirs(saida, exist_ok=True)
    senha = os.environ.get('PAINEL_SENHA', '')
    if not senha and not os.path.exists(os.path.join(site, 'data', 'planilha.json')):
        print('Sem PAINEL_SENHA: não dá para abrir a planilha; relatório não gerado.'); sys.exit(3)
    hoje = date.today()
    lista, plan_atual = requisicoes_em_atraso(site, senha, hoje)
    f1 = [r for r in lista if 31 <= r['atraso'] <= 90]
    f2 = [r for r in lista if r['atraso'] > 90]
    a1 = os.path.join(saida, f'requisicoes_atraso_31a90_{hoje.isoformat()}.pdf')
    a2 = os.path.join(saida, f'requisicoes_atraso_mais90_{hoje.isoformat()}.pdf')
    pdf(f1, 'Requisições com 31 a 90 dias de atraso, por fornecedor', a1, hoje, plan_atual)
    pdf(f2, 'Requisições com mais de 90 dias de atraso, por fornecedor', a2, hoje, plan_atual)
    nf = lambda l: len({r['fornecedor'] for r in l})
    corpo = (f'Bom dia!\n\nRelatório semanal das requisições em atraso ({hoje.strftime("%d/%m/%Y")}):\n'
             f'- 31 a 90 dias: {len(f1)} requisições de {nf(f1)} fornecedores (valor empenhado {brl(sum(r["valor"] for r in f1))})\n'
             f'- mais de 90 dias: {len(f2)} requisições de {nf(f2)} fornecedores (valor empenhado {brl(sum(r["valor"] for r in f2))})\n\n'
             'Os dois PDFs estão anexados, agrupados por fornecedor (o de maior atraso primeiro).\n'
             'Painel dos servidores: https://vagnerims2.github.io/painel-leopolis/interno/#requisicoes\n\n'
             'Mensagem automática do Painel de Empenhos (GitHub). Dados: Portal da Transparência e planilha de requisições.')
    print(corpo)
    if '--enviar' in sys.argv:
        ok = enviar([a1, a2], f'Requisições em atraso — {hoje.strftime("%d/%m/%Y")} ({len(f1)} de 31 a 90 dias, {len(f2)} acima de 90)', corpo)
        if not ok: sys.exit(3)


if __name__ == '__main__':
    main()
