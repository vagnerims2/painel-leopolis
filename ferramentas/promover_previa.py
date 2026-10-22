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

# ---------------- servidores
si = s.replace('<title>Painel Modo Desenvolvedor</title>', '<title>Painel interno de Empenhos — Leópolis</title>')
si = si.replace("'data/", "'../data/").replace('"data/', '"../data/')
si = rep(si, "/* PRÉVIA: abre direto, sem senha */ fetch('../data/planilha.json?v=' + Date.now()).then(r => r.json()).then(mostrarReq).catch(e => { document.getElementById('req-msg').textContent = 'Não consegui carregar os dados da prévia.'; });",
         "{ let s = ''; try { s = sessionStorage.getItem('req-senha') || ''; } catch (e) {} if (s) tentarSenha(s, true); }")
assert 'planilha.json' not in si and "'data/" not in si
open(f'{repo}/interno/index.html', 'w', encoding='utf-8').write(si)

# ---------------- público
sp = s.replace('<title>Painel Modo Desenvolvedor</title>', '<title>Despesas do Município — Leópolis</title>')
sp = sp.replace('<meta name="robots" content="noindex,nofollow">\n', '')
# sem Requisições (dados internos da planilha) e sem Dotações
sp = re.sub(r'\s*<button data-go="requisicoes"[^<]*</button>', '', sp)
sp = re.sub(r'\s*<button data-go="dotacoes"[^<]*</button>', '', sp)
i = sp.index("/* PRÉVIA: abre direto, sem senha */"); j = sp.index('\n', i)
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
chk = sp.lower().replace('equiplano.com.br', '')
assert 'equiplano' not in chk and 'planilha.json' not in sp, 'conteúdo interno na versão pública'
open(f'{repo}/index.html', 'w', encoding='utf-8').write(sp)
print('ok', len(si), len(sp))
