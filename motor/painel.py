"""Painel de Empenhos Leópolis — atualização automática.

Roda em dois lugares:
  * GitHub (principal): a automação "Atualizar painel" roda a cada 30 min nos dias úteis
    (variáveis PAINEL_PASTA, PAINEL_SITE e PAINEL_SEM_GIT=1; quem envia é a própria automação).
  * Notebook (reserva): só trabalha se o GitHub não tiver rodado com sucesso na última hora e 15 min.

O Agendador de Tarefas do Windows roda este programa a cada 30 minutos nos dias úteis.
Ele confere se o Portal da Transparência tem lançamento novo; se tiver, coleta, recalcula,
gera a planilha Excel e envia tudo para o GitHub (os links do site se atualizam sozinhos).

Uso:  python painel.py            (normal: só atualiza se houver novidade)
      python painel.py --forcar   (atualiza mesmo sem novidade)
"""
import json, os, subprocess, sys, traceback
from datetime import date, datetime, timedelta

PASTA = os.environ.get('PAINEL_PASTA') or os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get('PAINEL_SITE') or os.path.join(PASTA, 'site')
SEM_GIT = os.environ.get('PAINEL_SEM_GIT') == '1'   # no GitHub: a automação faz o envio
WORKFLOW_API = 'https://api.github.com/repos/vagnerims2/painel-leopolis/actions/workflows/atualizar.yml/runs?status=success&per_page=1'
LOG = os.path.join(PASTA, 'painel.log')
TRAVA = os.path.join(PASTA, 'painel.trava')
PAG_POR_RODADA = 30  # dias de pagamento relidos por atualização até todos terem o fornecedor
DET_POR_RODADA = 25   # dias relidos por atualização para detalhar os itens (unidade, descrição, CATMAT)
ESTADO = os.path.join(PASTA, 'estado.json')
P = lambda *a: os.path.join(PASTA, *a)


def log(msg):
    linha = f"{datetime.now():%d/%m/%Y %H:%M:%S}  {msg}"
    print(linha)
    try:
        if os.path.exists(LOG) and os.path.getsize(LOG) > 2_000_000:  # guarda só o log recente
            os.replace(LOG, LOG + '.antigo')
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(linha + '\n')
    except OSError:
        pass


def rodar(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}… falhou:\n{(r.stderr or r.stdout)[-1500:]}")
    return r.stdout


def ler_json(caminho, padrao):
    try:
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return padrao


def github_em_dia():
    """True se a automação do GitHub rodou com sucesso nos últimos 75 minutos"""
    try:
        import requests
        r = requests.get(WORKFLOW_API, timeout=20).json()['workflow_runs']
        if r:
            fim = datetime.fromisoformat(r[0]['updated_at'].replace('Z', '+00:00'))
            idade = (datetime.now(fim.tzinfo) - fim).total_seconds() / 60
            if idade < 75:
                log(f'GitHub atualizou há {idade:.0f} min; o notebook fica de reserva.')
                return True
            log(f'GitHub sem atualizar há {idade:.0f} min; o notebook assume.')
    except Exception as e:
        log(f'Não consegui consultar o GitHub ({e}); o notebook assume.')
    return False


def principal(forcar=False, arquivo_coleta=None):
    sys.path.insert(0, PASTA)
    import coleta

    estado = ler_json(ESTADO, {})
    py = sys.executable.replace('pythonw.exe', 'python.exe')

    # notebook = reserva: se o GitHub atualizou há pouco, não faz nada
    if not SEM_GIT and not forcar and github_em_dia():
        return

    # 0) pega as versões mais novas da página e das ferramentas do site
    if not SEM_GIT:
        try:
            rodar(['git', 'pull', '--quiet', '--rebase', 'origin', 'main'], cwd=SITE)
        except Exception as e:
            log(f'Aviso: não consegui atualizar a cópia do site ({e}). Sigo assim mesmo.')

    # 1) há novidade no portal?
    assin = 'teste' if arquivo_coleta else coleta.assinatura()[0]
    hoje = date.today()
    sexta_pendente = hoje.weekday() == 4 and datetime.now().hour >= 17 and estado.get('resumo_semanal') != hoje.isoformat()
    # ainda há dias para reler e detalhar os itens? então roda mesmo sem novidade no portal
    det_pendente = False
    if not arquivo_coleta:
        _m = ler_json(P('master.json'), {})
        _t = set(estado.get('det_dias', []))
        det_pendente = any(not e.get('det') and e.get('d') and e['d'] not in _t for e in _m.get('empenhos', {}).values())
        _pt = set(estado.get('pag_dias', []))
        det_pendente = det_pendente or any(not p.get('cred') and p.get('d') not in _pt for p in _m.get('pagamentos', {}).values())
        del _m
    if not forcar and assin == estado.get('assinatura') and not sexta_pendente and not det_pendente:
        log('Sem lançamento novo no portal.')
        return

    # 2) coleta (desde a última coleta menos 3 dias, para pegar correções)
    try:
        ultima = date.fromisoformat(open(P('ultima_coleta.txt'), encoding='utf-8').read().strip())
    except (OSError, ValueError):
        ultima = date(hoje.year, 1, 1)
    desde = max(date(hoje.year, 1, 1), ultima - timedelta(days=3)).isoformat()
    log(f'Novidade no portal. Coletando desde {desde}…')
    det_agora = []; pag_agora = []
    if arquivo_coleta:
        res = ler_json(arquivo_coleta, None)
    else:
        mestre = ler_json(P('master.json'), {})
        conhecido = {}
        for e in mestre.get('empenhos', {}).values():
            conhecido[e['d']] = conhecido.get(e['d'], 0) + (e.get('v') or 0)
        # dia da liquidação -> dias dos empenhos liquidados (para reler quando aparece estorno de liquidação/pagamento)
        por_liq = {}
        for l in mestre.get('liquidacoes', {}).values():
            e = mestre.get('empenhos', {}).get(l.get('e'))
            if e: por_liq.setdefault(l['d'], set()).add(e['d'])
        try:
            extra = [x.strip() for x in open(P('reler.txt'), encoding='utf-8') if x.strip()]
        except OSError:
            extra = []
        # releitura gradual dos dias antigos para pegar unidade, descrição completa e código CATMAT dos itens
        # (DET_POR_RODADA dias por atualização, dos mais recentes para os mais antigos)
        tentados = set(estado.get('det_dias', []))
        pend = sorted({e['d'] for e in mestre.get('empenhos', {}).values() if not e.get('det') and e.get('d') and e['d'] not in tentados}, reverse=True)
        det_agora = pend[:DET_POR_RODADA]
        if det_agora:
            log(f'Relendo {len(det_agora)} dias para detalhar os itens (faltam {len(pend) - len(det_agora)}).')
            extra += det_agora
        # pagamentos lidos antes de o robô guardar o fornecedor (precisa nos restos a pagar): relê aos poucos
        pag_t = set(estado.get('pag_dias', []))
        pag_pend = sorted({p['d'] for p in mestre.get('pagamentos', {}).values() if not p.get('cred') and p.get('d', '') < desde and p['d'] not in pag_t}, reverse=True)
        pag_agora = pag_pend[:PAG_POR_RODADA]
        if pag_agora:
            log(f'Relendo {len(pag_agora)} dias de pagamento para guardar o fornecedor (faltam {len(pag_pend) - len(pag_agora)}).')
        res = coleta.coletar(desde, desde, avisar=log, mov_anterior=mestre.get('mov'), emp_conhecido=conhecido if conhecido else None,
                             saldo_anterior=mestre.get('saldo'), emp_por_liq_dia=por_liq, dias_extra=extra, dias_pag_extra=pag_agora,
                             docs_desde=None if len(mestre.get('docs') or {}) > 1000 else f'{hoje.year}-01-01')
        del mestre
    if len(res['erros']) > 10:
        raise RuntimeError(f"Muitos erros na coleta ({len(res['erros'])}); nada foi publicado. Primeiros: {res['erros'][:3]}")
    with open(P('coleta_ultima.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False)

    # 3) recalcula (o build.py é o mesmo usado até aqui; ele atualiza master.json e alertas.json)
    saida = P('saida')
    out = rodar([py, P('build.py'), P('master.json'), P('coleta_ultima.json'), saida, P('itens_requisicoes.csv')]).strip()
    resumo = json.loads(out[out.index('{'):])
    dif = abs(resumo['saldo_calculado'] - resumo['saldo_portal'])
    if resumo['saldo_portal'] and dif / resumo['saldo_portal'] > 0.01:
        log(f"Atenção: saldo calculado {resumo['saldo_calculado']:.2f} difere do portal {resumo['saldo_portal']:.2f}. Publicando mesmo assim.")

    # 4) site: dados, planilha e (sexta à tarde) resumo semanal
    ferr = os.path.join(SITE, 'ferramentas')
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    rodar([py, os.path.join(ferr, 'atualizar_dados.py'), saida, SITE, agora])
    rodar([py, os.path.join(ferr, 'gerar_planilha.py'), saida, os.path.join(SITE, 'interno', 'planilha', 'painel_empenhos.xlsx')])
    # receitas, indicadores da LRF e dívida ativa (relatórios do portal): no máximo a cada 3 horas
    ult_fin = estado.get('financas', '')
    if forcar or not ult_fin or (datetime.now() - datetime.fromisoformat(ult_fin)).total_seconds() > 3 * 3600 \
            or not os.path.exists(os.path.join(SITE, 'data', 'indicadores.json')):
        try:
            import financas
            financas.gerar(os.path.join(SITE, 'data'), avisar=log)
            estado['financas'] = datetime.now().isoformat(timespec='seconds')
        except Exception as e:
            log(f'Aviso: receitas/indicadores não atualizados nesta rodada ({e}); ficam os da rodada anterior.')
    if sexta_pendente:
        pdf = os.path.join(SITE, 'interno', 'resumos', f'resumo_{hoje.isoformat()}.pdf')
        rodar([py, os.path.join(ferr, 'resumo_semanal.py'), saida, pdf])
        import shutil
        shutil.copyfile(pdf, os.path.join(SITE, 'interno', 'resumos', 'ultimo.pdf'))
        estado['resumo_semanal'] = hoje.isoformat()

    # 5) envia para o GitHub (no GitHub, quem envia é a automação)
    if SEM_GIT:
        log(f"Pronto para publicar: {resumo['empenhos']} empenhos, saldo a pagar R$ {resumo['saldo_portal']:,.2f}, {resumo['alertas_parados']} parados.")
    elif rodar(['git', 'add', 'data', 'interno/planilha', 'interno/resumos'], cwd=SITE) is None:
        pass
    elif subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=SITE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).returncode != 0:
        rodar(['git', 'commit', '--quiet', '-m', f'Dados de {agora}'], cwd=SITE)
        try:
            rodar(['git', 'push', '--quiet', 'origin', 'main'], cwd=SITE)
        except RuntimeError:
            # alguém publicou no site enquanto coletávamos (ex.: ajuste feito pelo Claude): junta e tenta de novo
            rodar(['git', 'pull', '--quiet', '--rebase', '-X', 'theirs', 'origin', 'main'], cwd=SITE)
            rodar(['git', 'push', '--quiet', 'origin', 'main'], cwd=SITE)
        log(f"Publicado: {resumo['empenhos']} empenhos, saldo a pagar R$ {resumo['saldo_portal']:,.2f}, {resumo['alertas_parados']} parados.")
    else:
        log('Nada mudou nos dados publicados.')

    if os.path.exists(P('reler.txt')):
        os.remove(P('reler.txt'))
    with open(P('ultima_coleta.txt'), 'w', encoding='utf-8') as f:
        f.write(hoje.isoformat())
    if not arquivo_coleta and pag_agora:
        _f = {x.split()[0] for x in res.get('erros', []) if x}
        estado['pag_dias'] = sorted(set(estado.get('pag_dias', [])) | (set(pag_agora) - _f))
    if not arquivo_coleta and det_agora:
        falhos = {x.split()[0] for x in res.get('erros', []) if x}
        estado['det_dias'] = sorted(set(estado.get('det_dias', [])) | (set(det_agora) - falhos))
    estado.update(assinatura=assin, ultima_atualizacao=datetime.now().isoformat(timespec='seconds'))
    with open(ESTADO, 'w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    agora = datetime.now()
    # trava para não rodar duas vezes ao mesmo tempo (uma atualização leva alguns minutos)
    if os.path.exists(TRAVA) and (agora.timestamp() - os.path.getmtime(TRAVA)) < 3 * 3600:
        log('Outra atualização ainda está rodando; saio.')
        sys.exit(0)
    open(TRAVA, 'w').close()
    try:
        arq = sys.argv[sys.argv.index('--coleta') + 1] if '--coleta' in sys.argv else None
        principal(forcar='--forcar' in sys.argv, arquivo_coleta=arq)
    except Exception as e:
        log('ERRO: ' + str(e))
        log(traceback.format_exc().splitlines()[-1])
        sys.exit(1)
    finally:
        try:
            os.remove(TRAVA)
        except OSError:
            pass
