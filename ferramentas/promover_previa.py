"""Leva a página aprovada no Modo Desenvolvedor para os dois links oficiais.

Uso: python3 ferramentas/promover_previa.py <previa/index.html> <repositorio>
  gera  <repositorio>/interno/index.html  (servidores: tudo, Requisições com senha, dados em ../data/)
        <repositorio>/index.html          (público: sem Dotações, Requisições e quadros internos, dados em data/)
"""
import re, sys

src, repo = sys.argv[1], sys.argv[2]
base = open(src, encoding='utf-8').read()

def rep(s, a, b, n=1):
    assert s.count(a) >= 1, f'não achei: {a[:70]}'
    return s.replace(a, b) if n is None else s.replace(a, b, n)

def cut(s, a, b):
    i = s.index(a); j = s.index(b, i)
    return s[:i] + s[j:]

# ---- comum: tira a faixa e as marcas do modo desenvolvedor
s = re.sub(r'<div style="background:#b7791f;[^>]*>MODO DESENVOLVEDOR[^<]*</div>', '', base, count=1)
# documento completo (a prévia é publicada sem o esqueleto <html><head><body>)
if '<!doctype' not in s[:200].lower():
    i = s.index('</style>') + len('</style>')
    s = '<!doctype html>\n<html lang="pt-BR">\n<head>' + s[:i] + '\n</head>\n<body>' + s[i:].rstrip() + '\n</body>\n</html>\n'
assert 'MODO DESENVOLVEDOR' not in s and s.count('id="dash-root"') == 1
s = s.replace(' (modo desenvolvedor)', '')
# a prévia lê a planilha nova (planilha_previa.json) e cai na oficial se ela não existir; os links oficiais leem só a oficial
s = s.replace("fetch('data/planilha_previa.json?v=' + Date.now()).then(r => { if (!r.ok) throw 0; return r.json(); }).catch(() => fetch('data/planilha.json?v=' + Date.now()).then(r => r.json()))", "fetch('data/planilha.json?v=' + Date.now()).then(r => r.json())")

# ---------------- servidores
si = s.replace('<title>Painel Modo Desenvolvedor</title>', '<title>Painel interno de Empenhos — Leópolis</title>')
si = si.replace("'data/", "'../data/").replace('"data/', '"../data/')
assert "'data/" not in si  # Requisições sem senha (pedido de 22/10/2026): lê ../data/planilha.json
open(f'{repo}/interno/index.html', 'w', encoding='utf-8').write(si)

# ---------------- público
sp = s.replace('<title>Painel Modo Desenvolvedor</title>', '<title>Despesas do Município — Leópolis</title>')
sp = sp.replace('<meta name="robots" content="noindex,nofollow">\n', '')
# sem Requisições (dados internos da planilha) e sem Dotações
sp = re.sub(r'\s*<button data-go="requisicoes"[^<]*</button>', '', sp)
sp = re.sub(r'\s*<button data-go="dotacoes"[^<]*</button>', '', sp)
i = sp.index("/* sem senha: abre direto */"); j = sp.index('\n', i)
sp = sp[:i] + sp[j + 1:]
EXTERNO_CSS = """
/* versão para o cidadão: só informação geral */
#dash-root #alertas-resumo,#dash-root #composicao,#dash-root #precos-alto,#dash-root .tab[data-tab=alertas],#dash-root .tab[data-tab=dotacoes],#dash-root .tab[data-tab=semana],#dash-root .tab[data-tab=requisicoes],
#dash-root #faixa,#dash-root .tiles .card.tile:nth-child(4) .sub{display:none!important}
#tbl th:nth-child(5),#tbl tbody td:nth-child(5),#tbl th:nth-child(6),#tbl tbody td:nth-child(6),#tbl th:nth-child(9),#tbl tbody td:nth-child(9),
#tbl tfoot td:nth-child(3),#tbl tfoot td:nth-child(4){display:none!important}
"""
sp = rep(sp, '</style>', EXTERNO_CSS + '</style>')
sp = sp.replace('Prefeitura Municipal de Leópolis · Execução da despesa', 'Prefeitura Municipal de Leópolis · Transparência')
sp = sp.replace('Empenhos e liquidações — 2026</h1>', 'Despesas do Município — 2026</h1>')
sp = re.sub(r'<p class="foot">.*?</p>', '<p class="foot">Fonte: Portal da Transparência do Município de Leópolis — despesa empenhada, liquidada e paga, receitas, demonstrativos da LRF e dívida ativa. Painel informativo, atualizado automaticamente nos dias úteis; em caso de divergência, vale o portal oficial. <span id="atualizado"></span><br>Baixar dados (CSV): <a href="data/empenhos.csv">empenhos</a> · <a href="data/itens.csv">itens</a> · <a href="data/liquidacoes.csv">liquidações</a> · <a href="data/movimento.csv">movimento diário</a> · <a href="data/saldo_fontes.csv">saldo por fonte</a></p>', sp, count=1, flags=re.S)
sp = rep(sp, "{ const h = location.hash.slice(1); if (", "{ const h = ['alertas', 'dotacoes', 'semana', 'requisicoes'].includes(location.hash.slice(1)) ? '' : location.hash.slice(1); if (")
# link público desativado a pedido (22/10/2026): no lugar do painel fica um aviso. Para religar: PUBLICO_ATIVO = True
# (antes de religar: tirar da versão pública o código dos itens pendentes do Equiplano, que a checagem abaixo vai acusar)
PUBLICO_ATIVO = False
chk = sp.lower().replace('equiplano.com.br', '')
assert not PUBLICO_ATIVO or ('equiplano' not in chk and 'planilha.json' not in sp), 'conteúdo interno na versão pública'
AVISO = '''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Despesas do Município — Leópolis</title>
<style>:root{color-scheme:light dark}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f4ef;color:#1f1e1b;font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding:16px;box-sizing:border-box}
main{max-width:34rem;background:#fff;border-radius:12px;padding:28px;box-shadow:0 4px 18px rgba(0,0,0,.08)}h1{font-size:1.25rem;margin:0 0 8px}a{color:#255f85}
@media (prefers-color-scheme:dark){body{background:#1c1b19;color:#ecebe7}main{background:#262522}a{color:#6fa8d6}}</style></head>
<body><main><h1>Painel temporariamente indisponível</h1>
<p>Este painel da Prefeitura Municipal de Leópolis está fora do ar por enquanto.</p>
<p>As informações oficiais de receitas e despesas continuam no <a href="https://leopolispr.equiplano.com.br:7300/transparencia/" rel="noopener">Portal da Transparência do Município</a>.</p></main></body></html>
'''
open(f'{repo}/index.html', 'w', encoding='utf-8').write(sp if PUBLICO_ATIVO else AVISO)
print('ok', len(si), len(sp))
