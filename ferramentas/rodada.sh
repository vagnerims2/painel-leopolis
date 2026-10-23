#!/usr/bin/env bash
# Uma rodada do robô no GitHub: portal -> planilha -> fornecedores -> pendentes -> base do ano -> e-mail de segunda -> publica.
# Uso: bash ferramentas/rodada.sh [--forcar]
set -u
FORCAR="${1:-}"
git pull -q --rebase --autostash -X theirs origin main || echo "Aviso: não consegui pegar a versão mais nova do repositório; sigo com a atual."
cp motor/painel.py motor/coleta.py motor/build.py motor/financas.py motor/estado/
# no GitHub só roda uma rodada por vez (fila do workflow): trava velha de uma rodada interrompida não pode bloquear
rm -f motor/estado/painel.trava

if ! python motor/estado/painel.py $FORCAR; then
  tail -n 40 motor/estado/painel.log || true
  echo "Coleta no portal falhou nesta rodada; nada publicado. Tenta de novo na próxima."
  return 1 2>/dev/null || exit 1
fi
python ferramentas/planilha_requisicoes.py --aberto - data/planilha.json || echo "Aviso: planilha não lida nesta rodada."
python ferramentas/fornecedores.py data || echo "Aviso: cadastro de fornecedores não atualizado nesta rodada."
python ferramentas/pendentes.py - data/pendentes.json || echo "Aviso: itens pendentes não lidos nesta rodada."
python ferramentas/requisicoes_ano.py - data/requisicoes_ano.json || echo "Aviso: base do ano não lida nesta rodada."
python ferramentas/notas_xml.py data/notas_itens.json || echo "Aviso: XML das notas não lidos nesta rodada."

# relatório semanal de requisições em atraso: segunda-feira, primeira rodada a partir das 7h (ou quando pedido)
semana=$(date +%G-%V); marca=motor/estado/relatorio_atraso.txt
if [ "${RELATORIO_AGORA:-}" = "true" ] || { [ "$(date +%u)" = 1 ] && [ "$(date +%H)" -ge 7 ] && [ "$(cat $marca 2>/dev/null)" != "$semana" ]; }; then
  if python ferramentas/relatorio_atraso.py . /tmp/relatorio --enviar; then echo "$semana" > $marca; else echo "Relatório não enviado (veja a mensagem acima)."; fi
fi

# publica (a hora da leitura muda sempre, mesmo sem novidade no portal)
date '+%d/%m/%Y %H:%M' > data/ultima_leitura.txt
tail -n 60 motor/estado/painel.log > data/robo_log.txt 2>/dev/null || true   # registro da rodada (só mensagens do robô) para conferência
git add data interno/planilha interno/resumos
if git diff --cached --quiet; then echo "Nada mudou nos dados publicados."; exit 0; fi
git commit -q -m "Dados de $(date '+%d/%m/%Y %H:%M') (GitHub)"
for i in 1 2 3; do
  git push -q origin main && exit 0
  git pull -q --rebase --autostash -X theirs origin main
done
echo "Não consegui publicar nesta rodada."; exit 1
