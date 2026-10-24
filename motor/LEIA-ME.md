# Motor de atualização do painel

- **Principal: GitHub.** A automação *Atualizar painel* (.github/workflows/atualizar.yml) roda nos dias úteis, das 7h30 às 17h30: confere o Portal da Transparência a cada 5 minutos (publica só se houver novidade) e faz a rodada completa (planilha, Drive, XMLs e fornecedores) a cada 20 minutos. Ela recalcula e publica `data/`, a planilha e o resumo semanal.
- **Reserva: notebook.** O agendador do Windows continua rodando `painel.py`, mas ele só trabalha se o GitHub não tiver atualizado com sucesso na última 1h15.
- O estado entre uma rodada e outra (master.json etc.) fica no cache da automação. Se o cache sumir, ela recomeça pela pasta `semente/`.
- Para atualizar na hora: aba **Actions** → *Atualizar painel* → **Run workflow**.

## Itens: unidade, embalagem e código CATMAT
- O robô lê, de cada item da nota de empenho, a unidade (coluna UM), a descrição completa e o código do catálogo federal (CATMAT/CODIGOBR).
- O quadro "Preços acima do padrão" só compara itens com o mesmo código (ou mesmo nome), a mesma unidade e as mesmas medidas de embalagem (ex.: galão 5 L x refil 800 ml ficam separados).
- Os dias antigos são relidos aos poucos (`DET_POR_RODADA` dias por atualização, em `painel.py`); os dias já relidos ficam em `estado.json` (`det_dias`).
