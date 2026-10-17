"""Gera index.html público a partir da página do painel do Claude (pipe/index.html).
Uso: python3 montar_site.py <index_painel.html> <saida/index.html>"""
import re, sys
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

shell = open(__file__.replace('montar_site.py', 'molde.html'), encoding='utf-8').read()
out = shell.replace('/*ESTILO*/', style).replace('<!--CORPO-->', body).replace('/*PAGINA*/', js)
open(sys.argv[2], 'w', encoding='utf-8').write(out)
print('ok', len(out))
