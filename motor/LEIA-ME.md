# Motor de atualização do painel

- **Principal: GitHub.** A automação *Atualizar painel* (.github/workflows/atualizar.yml) roda a cada 30 minutos nos dias úteis, das 7h às 18h30. Ela consulta o Portal da Transparência, recalcula e publica `data/`, a planilha e o resumo semanal.
- **Reserva: notebook.** O agendador do Windows continua rodando `painel.py`, mas ele só trabalha se o GitHub não tiver atualizado com sucesso na última 1h15.
- O estado entre uma rodada e outra (master.json etc.) fica no cache da automação. Se o cache sumir, ela recomeça pela pasta `semente/`.
- Para atualizar na hora: aba **Actions** → *Atualizar painel* → **Run workflow**.
