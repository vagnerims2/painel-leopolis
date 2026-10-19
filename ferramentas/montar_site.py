"""Gera index.html público a partir da página do painel do Claude (pipe/index.html).
Uso: python3 montar_site.py <index_painel.html> <saida/index.html> [interno|externo]
  externo: versão simples para o cidadão (raiz do site)
  interno: versão completa para os servidores (pasta interno/), lê os dados de ../data/"""
import re, sys
modo = sys.argv[3] if len(sys.argv) > 3 else 'interno'
src = open(sys.argv[1], encoding='utf-8').read()
style = src[src.index('<style>') + 7: src.index('</style>')]
body = src[src.index('</style>') + 8: src.index('<script>')]
js = src[src.index('<script>') + 8: src.rindex('</script>')]

def cut(s, a, b, incl_b=True):
    i = s.index(a); j = s.index(b, i)
    return s[:i] + s[j + (len(b) if incl_b else 0):]

# remove aba Conferência e coluna Equiplano
body = re.sub(r'\s*<button data-go="conferencia"[^<]*</button>', '', body)
body = cut(body, '<!-- ============ CONFERÊNCIA', '<p class="foot">', incl_b=False)
body = body.replace('<th data-field="qtd_liquidada_equiplano" class="r hide-sm">Liq. (Equiplano)</th>', '')
body = re.sub(r'<p class="foot">.*?</p>', '<p class="foot">Fonte: Portal da Transparência do Município de Leópolis — despesa empenhada, liquidada e paga, saldo a pagar por credor e por fonte. Painel informativo, atualizado automaticamente nos dias úteis; em caso de divergência, vale o portal oficial. <span id="atualizado"></span><br>Baixar dados (CSV): <a href="data/empenhos.csv">empenhos</a> · <a href="data/itens.csv">itens</a> · <a href="data/liquidacoes.csv">liquidações</a> · <a href="data/movimento.csv">movimento diário</a> · <a href="data/saldo_fontes.csv">saldo por fonte</a> · <a href="data/dotacoes.csv">dotações</a></p>', body, flags=re.S)
js = cut(js, "dash.calc('conf', {", "\n});\n")
js = js.replace("fillMarks('conf', {});", '')
js = js.replace("td(tr, r.qtd_liquidada_equiplano === '' ? '—' : qtdF.format(N(r.qtd_liquidada_equiplano)), 'r hide-sm'); ", '')
body = body.replace('confira no Equiplano antes de pedir. Para mandar ao contador, baixe a lista em CSV em Sources (Dotações).', 'confira no sistema contábil. A lista pode ser baixada em CSV no rodapé.')
body = body.replace(' A coluna "Liq. (Equiplano)" vem do último relatório de requisições enviado.', '')
assert 'equiplano' not in (body + js).lower(), [m.start() for m in re.finditer('equiplano', (body+js).lower())]

EXTERNO_CSS = """
/* versão para o cidadão: só informação geral */
#dash-root .tabs button[data-go=alertas],#dash-root .tabs button[data-go=dotacoes],#dash-root .tabs button[data-go=semana],
#dash-root #alertas-resumo,#dash-root #composicao,#dash-root .tab[data-tab=alertas],#dash-root .tab[data-tab=dotacoes],#dash-root .tab[data-tab=semana],
#dash-root #faixa,#dash-root .tiles .card.tile:nth-child(4) .sub{display:none!important}
#tbl th:nth-child(5),#tbl tbody td:nth-child(5),#tbl th:nth-child(6),#tbl tbody td:nth-child(6),#tbl th:nth-child(9),#tbl tbody td:nth-child(9),
#tbl tfoot td:nth-child(3),#tbl tfoot td:nth-child(4){display:none!important}
"""
if modo == 'externo':
    style += EXTERNO_CSS
    # busca por requisição de compra: só na versão interna
    body = re.sub(r'\s*<button data-go="requisicoes"[^<]*</button>', '', body)
    body = cut(body, '<!--REQ-INI-->', '<!--REQ-FIM-->')
    js = cut(js, '// REQ-INI', '// REQ-FIM')
    body = body.replace('Prefeitura Municipal de Leópolis · Execução da despesa', 'Prefeitura Municipal de Leópolis · Transparência')
    body = body.replace('<h1 id="titulo">Empenhos e liquidações — 2026</h1>', '<h1 id="titulo">Despesas do Município — 2026</h1>')
    body = body.replace('Marque "Só com saldo a pagar" para ver apenas o que está em aberto. Dias em amarelo: 31 a 90; vermelho: mais de 90 (só para os abertos).', 'Pesquise por número, fornecedor ou produto e use os filtros para refinar.')
    js = js.replace("{ const h = location.hash.slice(1); if (", "{ const h = ['alertas', 'dotacoes', 'semana'].includes(location.hash.slice(1)) ? '' : location.hash.slice(1); if (")
    body = body.replace(' · <a href="data/dotacoes.csv">dotações</a>', '')
else:
    body = body.replace('href="data/', 'href="../data/')
    body = body.replace('Baixar dados (CSV):', '<a href="planilha/painel_empenhos.xlsx"><b>Baixar planilha (Excel)</b></a> · <a href="resumos/ultimo.pdf">Último resumo semanal (PDF)</a> · Baixar dados (CSV):')

shell = open(__file__.replace('montar_site.py', 'molde.html'), encoding='utf-8').read()
dados = 'data/' if modo == 'externo' else '../data/'
cab = '' if modo == 'externo' else '<meta name="robots" content="noindex,nofollow">'
titulo = 'Despesas do Município — Leópolis' if modo == 'externo' else 'Painel interno de Empenhos — Leópolis'
out = shell.replace('<!--CAB-->', cab).replace('__DADOS__', dados).replace('<title>Painel de Empenhos — Leópolis</title>', '<title>' + titulo + '</title>').replace('/*ESTILO*/', style).replace('<!--CORPO-->', body).replace('/*PAGINA*/', js)
if modo == 'externo':
    out = out.replace("const OPCIONAIS = ['requisicoes'];", 'const OPCIONAIS = [];')
open(sys.argv[2], 'w', encoding='utf-8').write(out)
print('ok', len(out))
