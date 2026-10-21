"""Lê a planilha de requisições (Google Sheets "Espelho Fornecedores") e grava data/planilha.enc.json criptografado.

Os dados da planilha são internos (memorando, etapa, telefone, e-mail, observações), por isso só vão para o site
criptografados com a senha dos servidores (AES-256-GCM, chave derivada por PBKDF2-SHA256). A página interna
pede a senha no botão "Ver dados" e abre tudo no próprio navegador.

Uso:  python ferramentas/planilha_requisicoes.py [arquivo.csv] [saida.json]
  sem arquivo: baixa a planilha do endereço em PLANILHA_URL (segredo do GitHub)
  senha: variável PAINEL_SENHA (segredo do GitHub)
Se faltar a senha ou o endereço, não faz nada (o resto da atualização continua normal).
"""
import base64, csv, io, json, os, re, sys, unicodedata, urllib.request
from datetime import datetime, timezone, timedelta

ITER = 310000


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


def baixar(url):
    m = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]+)', url)
    if m and '/export' not in url:
        url = f'https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv'
    req = urllib.request.Request(url, headers={'User-Agent': 'painel-leopolis'})
    with urllib.request.urlopen(req, timeout=60) as r:
        t = r.read().decode('utf-8-sig')
    if t.lstrip().startswith('<'):
        raise SystemExit('A planilha não abriu sem login: confira o compartilhamento "Qualquer pessoa com o link — Leitor".')
    return t


# nome da coluna na planilha (normalizado) -> chave curta no arquivo
COLUNAS = {'MEMORANDOS': 'm', 'MEMORANDO': 'm', 'SECRETARIA': 's', 'DATA': 'd', 'REQUISICAO': 'r', 'REQUISICAO DE COMPRA': 'r',
           'REQUISICAO DE EMPENHO': 're', 'REQ EMPENHO': 're', 'EMPENHO': 'e', 'ETAPA': 'et', 'STATUS': 'st',
           'DIAS DE ATRASO': 'da', 'EMPRESA': 'f', 'TELEFONE': 't', 'EMAIL': 'em', 'E MAIL': 'em', 'OBSERVACOES': 'o', 'OBSERVACAO': 'o'}


def ler(texto):
    linhas = list(csv.reader(io.StringIO(texto)))
    cab = [COLUNAS.get(norm(h), '') for h in linhas[0]]
    out = []
    for ln in linhas[1:]:
        r = {}
        for k, v in zip(cab, ln):
            v = re.sub(r'\s+', ' ', v).strip()
            if k and v and v.lower() != 'nan':
                r[k] = v
        if not (r.get('f') or r.get('t') or r.get('em')) or not r.get('r'):
            continue
        m = re.match(r'^C[oó]digo Nome\s+(\S+)\s+(.*)$', r.get('f', ''))
        if m:
            r['c'], r['f'] = m.group(1), m.group(2)
        for k in ('r', 'e', 're'):
            if k in r:
                r[k] = re.sub(r'\.0$', '', r[k])
        out.append(r)
    return out


def cifrar(dados, senha):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    sal, iv = os.urandom(16), os.urandom(12)
    chave = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=ITER).derive(senha.encode('utf-8'))
    ct = AESGCM(chave).encrypt(iv, json.dumps(dados, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), None)
    b = lambda x: base64.b64encode(x).decode()
    return {'v': 1, 'kdf': 'PBKDF2-SHA256', 'iter': ITER, 'sal': b(sal), 'iv': b(iv), 'dados': b(ct)}


def main():
    senha = os.environ.get('PAINEL_SENHA', '')
    fonte = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != '-' else os.environ.get('PLANILHA_URL', '')
    saida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..', 'data', 'planilha.enc.json')
    if not senha or not fonte:
        print('Planilha de requisições: sem senha ou endereço configurado; pulando.')
        return
    texto = baixar(fonte) if fonte.startswith('http') else open(fonte, encoding='utf-8-sig').read()
    linhas = ler(texto)
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M')
    pacote = cifrar({'atualizado': agora, 'linhas': linhas}, senha)
    # só regrava se o conteúdo mudou (evita commit a cada rodada por causa do sal novo)
    marca = __import__('hashlib').sha256(json.dumps(linhas, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    pacote['marca'] = marca
    try:
        if json.load(open(saida, encoding='utf-8')).get('marca') == marca:
            print(f'Planilha de requisições: {len(linhas)} linhas, sem mudança.')
            return
    except Exception:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    json.dump(pacote, open(saida, 'w', encoding='utf-8'))
    print(f'Planilha de requisições: {len(linhas)} linhas gravadas em {saida}.')


if __name__ == '__main__':
    main()
