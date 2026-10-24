# Painel de Empenhos — Leópolis

Painel de empenhos, liquidações e pagamentos da Prefeitura Municipal de Leópolis-PR, montado com dados do Portal da Transparência do município.

- `interno/index.html`: versão dos servidores (link em uso).
- `index.html`: link público — **desativado por enquanto** (mostra só um aviso com o link do Portal da Transparência).
- As páginas leem os arquivos da pasta `data/`, gerados pelo robô (não editar à mão).
- `data/` é atualizada automaticamente pelo GitHub Actions nos dias úteis, das 7h30 às 17h30 (horário de Brasília): o portal é conferido a cada 5 minutos (publica só se houver novidade) e a rodada completa (planilha, Drive, XMLs e fornecedores) roda a cada 20 minutos. O notebook fica de reserva.
- Melhorias na página passam antes pelo modo desenvolvedor (prévia); depois de aprovadas, `ferramentas/promover_previa.py` gera os links oficiais.

Painel informativo: em caso de divergência, vale o portal oficial.
