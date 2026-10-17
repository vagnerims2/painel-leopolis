# Painel de Empenhos — Leópolis

Painel público de empenhos, liquidações e pagamentos da Prefeitura Municipal de Leópolis-PR, montado com dados do Portal da Transparência do município.

- `index.html`: versão para o cidadão (resumo, empenhos, produtos e licitações).
- `interno/index.html`: versão completa para os servidores (alertas, dotações, dia e semana).
- As duas leem os mesmos arquivos da pasta `data/`.
- `data/` é atualizada automaticamente nos dias úteis (9h, 11h40, 14h30 e 16h50).
- `ferramentas/montar_site.py` gera as duas páginas a partir do painel original (`externo` e `interno`).

Painel informativo: em caso de divergência, vale o portal oficial.
