"""Base do ano das requisições de compra: relatório completo do Equiplano "Controle de saldo da Requisição de compra x
Liquidação quantitativa" (com os movimentos: requisição de compra, requisição de empenho, empenho, liquidação e estornos).

O Vagner salva o relatório na mesma pasta do Drive dos pendentes (PENDENTES_PASTA). O robô reconhece qual é o completo
pelo conteúdo (tem os movimentos), lê e grava data/requisicoes_ano.json. Só relê quando o arquivo muda.

Uso: python ferramentas/requisicoes_ano.py [arquivo.pdf | -] [saida.json]
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pendentes as P

num = lambda s: (-1 if s.startswith('(') else 1) * float(s.strip('()').replace('.', '').replace(',', '.'))
CAB = re.compile(r'^(\d+)/(\d{4})\s+(\d\d/\d\d/\d{4})\s+(\S+-\d)\s+(.+?)\s*$')
ITEM = re.compile(r'^\s+(\d{3}/\d{3})\s+(\d+)\s+(.+?)\s{2,}(\(?[\d.]+,\d\d\)?)\s+(\(?[\d.]+,\d+\)?)\s+(\(?[\d.]+,\d{3}\)?)\s+(\(?[\d.]+,\d{3}\)?)\s+(\(?-?[\d.]+,\d{3}\)?)\s*$')
MOV = re.compile(r'^\s+(Requisição de compra|Requisição de empenho|Empenho|Liquidação|Estorno de requisição de compra|Estorno de requisição de empenho|Estorno de empenho|Estorno de liquidação)\s+(\d+)/(\d{4})\s+(\d\d/\d\d/\d{4})\s+(\(?[\d.]+,\d\d\)?)\s*$')
COD = {'Requisição de compra': 'RC', 'Requisição de empenho': 'RE', 'Empenho': 'EM', 'Liquidação': 'LQ', 'Estorno de requisição de compra': 'ERC',
       'Estorno de requisição de empenho': 'ERE', 'Estorno de empenho': 'EEM', 'Estorno de liquidação': 'ELQ'}


def ler(texto):
    R, cur, periodo, emitido = {}, None, None, None
    for l in texto.split('\n'):
        if periodo is None and (m := P.PERIODO.search(l)): periodo = [m.group(1), m.group(2)]
        if 'Emitido por' in l and (m := P.EMITIDO.search(l)): emitido = m.group(1); continue
        if (m := CAB.match(l)):
            cur = R.setdefault(m.group(1), {'d': m.group(3), 'c': m.group(4), 'f': re.sub(r'^\d{2}\.\d{3}\.\d{3}\s+', '', re.sub(r'\s+', ' ', m.group(5))), 'i': [], 'm': []}); continue
        if cur is None: continue
        if (m := ITEM.match(l)):
            cur['i'].append([m.group(1), m.group(2), re.sub(r'\s+', ' ', m.group(3)).strip(), round(num(m.group(4)), 2), num(m.group(5)), num(m.group(6)), num(m.group(7)), num(m.group(8))]); continue
        if (m := MOV.match(l)):
            cur['m'].append([COD[m.group(1)], m.group(2), m.group(4), num(m.group(5))])
    for q in R.values():
        rc = sum(x[3] for x in q['m'] if x[0] == 'RC'); erc = sum(x[3] for x in q['m'] if x[0] == 'ERC')
        q['x'] = 1 if erc and abs(rc - erc) < 0.01 else 0
    return R, periodo, emitido


def main():
    args = sys.argv[1:]
    fonte = args[0] if args and args[0] != '-' else ''
    saida = args[1] if len(args) > 1 else os.path.join(os.path.dirname(__file__), '..', 'data', 'requisicoes_ano.json')
    try:
        velho = json.load(open(saida, encoding='utf-8'))
    except Exception:
        velho = {}
    if fonte:
        dados, nome, chave = open(fonte, 'rb').read(), os.path.basename(fonte), ''
    else:
        pasta = os.environ.get('PENDENTES_PASTA', '')
        if not pasta:
            print('Base do ano: pasta do Drive não configurada; pulando.'); return
        rs = [r for r in P.relatorios(pasta) if r['tipo'] == 'ano']
        if not rs:
            print('Base do ano: nenhum relatório completo na pasta; fica a base atual.'); return
        r = rs[-1]; nome, chave = r['nome'], r['chave']
        if velho.get('chave') == chave:
            print(f"Base do ano: relatório já lido ({velho.get('emitido')})."); return
        dados = r['dados'] or P.baixar_drive(r['id'])
    R, periodo, emitido = ler(P.texto_pdf(dados))
    if len(R) < 0.8 * len(velho.get('reqs') or {}):
        raise SystemExit(f'Base do ano: li só {len(R)} requisições (antes {len(velho.get("reqs") or {})}); mantive a base anterior.')
    if velho.get('emitido') and emitido and datetime.strptime(emitido, '%d/%m/%Y %H:%M:%S') < datetime.strptime(velho['emitido'], '%d/%m/%Y %H:%M:%S'):
        print(f"Base do ano: o relatório da pasta ({emitido}) é mais antigo que a base atual ({velho['emitido']}); fica a atual."); return
    out = {'emitido': emitido, 'periodo': periodo, 'arquivo': nome, 'chave': chave,
           'lido': datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M'),
           'fonte': 'Equiplano: Controle de saldo da Requisição de compra x Liquidação quantitativa (relatório completo, com movimentos).',
           'campos_itens': ['lote/item', 'código', 'produto', 'valor total', 'valor unitário', 'requisitada', 'liquidada', 'pendente'],
           'movimentos': {v: k for k, v in COD.items()}, 'reqs': R}
    json.dump(out, open(saida, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print(f'Base do ano: {len(R)} requisições, {sum(len(q["i"]) for q in R.values())} itens (emitido {emitido}).')


if __name__ == '__main__':
    main()
