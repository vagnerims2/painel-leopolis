# CLAUDE.md — Painel de Empenhos de Leópolis

Contexto para o Claude Code. Responda sempre em português, em linguagem simples (o dono do projeto, Vagner, não é programador).

## Quem usa e para quê
- Vagner é agente administrativo na Prefeitura Municipal de Leópolis-PR, setor de empenho e liquidação (recebimento de notas). Usa o sistema Equiplano.
- O painel controla empenhos, liquidações e pagamentos e já tem servidores usando todos os dias.
- Site no GitHub Pages: `index.html` = link público; `interno/index.html` = link dos servidores (todos os funcionários têm acesso, sem senha).
- **No momento o link público está desativado**; só o link dos servidores está ativo.

## Regra de ouro: prévia antes de publicar
- Toda melhoria vai primeiro para o **modo desenvolvedor** (link fixo de prévia). Só depois que o Vagner aprovar ela vai para os links oficiais (`ferramentas/promover_previa.py`).
- Nunca altere direto o que os usuários veem sem aprovação.

## Fontes de dados (só estas)
- **Todos os dados do site vêm do Portal da Transparência**, inclusive a versão interna. Não buscar dados internos do Equiplano automaticamente.
- Ordem de leitura aprovada:
  1. Relatório completo do ano do Equiplano ("Controle de saldo da Requisição de compra x Liquidação quantitativa", com movimentos e estornos) como base para ligar requisição de compra → requisição de empenho → empenho. Salvo no Drive só algumas vezes por mês.
  2. Planilha Excel/Drive para dados do fornecedor e requisições emitidas depois do relatório.
  3. Portal para empenho, liquidação, pagamento, itens e nota fiscal.
  4. PDF resumido de pendentes (fica na pasta do Drive no dia a dia).
- Planilha "Espelho Fornecedores" (no Drive do Vagner, via IMPORTRANGE da planilha do colega) é lida a cada atualização automática.
- XMLs das notas ficam na subpasta "XML Notas" do Drive; o robô lê os produtos deles.

## Atualização automática
- GitHub Actions (`.github/workflows/atualizar.yml`) é o principal; o notebook de casa é reserva (só roda se o GitHub falhar por mais de 1h15).
- Dias úteis, das 7h30 às 17h30 (prefeitura funciona 7h30–17h). Nada fora desse horário.
- O portal é conferido a cada 5 minutos (publica só se houver novidade); rodada completa (planilha, Drive, XMLs, fornecedores) a cada 20 minutos. O rodapé mostra só "Última atualização" com a hora da última leitura completa, mesmo sem novidade.
- Ajuste no robô gravado fora do horário não dispara rodada; a próxima rodada do turno já usa a versão nova.
- Toda segunda, após a primeira atualização, envia por e-mail (Gmail do Vagner, só para ele) dois PDFs de requisições em atraso por fornecedor: 31–90 dias e mais de 90 dias.

## Regras de negócio
- Fluxo: requisição de compra → requisição de empenho → empenho → liquidação → pagamento. O painel mostra onde cada uma está parada.
- O campo "Requisição Nº" da nota de empenho no portal é a **requisição de empenho**, não a de compra.
- Empenho pago no portal = todos os itens recebidos.
- Requisição nova já empenhada entre um PDF e outro: itens do empenho aparecem como pendentes. Liquidação parcial feita depois do PDF: lista apagada com "desatualizado".
- Compras com convênio (obras, veículos) saem em 2 empenhos: valor do convênio + contrapartida.
- Uma mesma nota fiscal pode ser liquidada em vários empenhos do mesmo fornecedor (dotações diferentes); várias notas numa mesma liquidação é normal.
- Requisição anterior a 01/10/2026 que só está na planilha e sem requisição de empenho só aparece se o status for estornado ou cancelado (caso Lucas Mizael/Construcin).
- Telefone e e-mail funcionam como cadastro de fornecedores pelo código do fornecedor no Equiplano, atualizado pela planilha (não preso à requisição).
- Saldo de dotação: usar o saldo real pelos últimos empenhos (já reflete decretos). O contador abre decreto de suplementação no fim de cada mês; alerta mensal das dotações recorrentes (diárias, consórcio, cota extra) que não cobrem o mês seguinte.
- "Preços acima do padrão" só compara itens com mesmo código CATMAT (ou nome), mesma unidade e mesma embalagem.

## Abas atuais
- Ativas no link dos servidores (o Vagner usa todas): Visão geral, Dotações, Empenhos (com quadro do fornecedor e notas fiscais), Requisições (sem senha), Produtos (busca por empenho ou por nota fiscal), Licitações, Receitas, Indicadores LRF, Para o cidadão, Relatórios (produtos e fornecedores por período; CISNOP e Santa Casa pela data do pagamento).
- Removidas do menu: Alertas e Dia e semana (o código continua na página, escondido). Relatório automático em PDF do painel: fora por enquanto.

## Ideias futuras
- Painel tributário (IPTU, ISS, ITBI, taxas, transferências, dívida ativa), receita prevista × arrecadada, só com dados do portal.
- Relatório periódico para a Saúde do gasto com CISNOP e Santa Casa, contado pela data do pagamento (não do empenho). A aba Relatórios já faz isso na tela; falta só o envio periódico.

## Estrutura
- `motor/`: coleta do portal e cálculo (`painel.py`, `coleta.py`, `financas.py`, `build.py`); estado inicial em `motor/semente/`.
- `ferramentas/`: geração do site, planilha, fornecedores, notas XML, pendentes, relatório de atraso, promoção da prévia.
- `data/`: arquivos lidos pelas páginas (gerados pelo robô; não editar à mão).
- Em caso de divergência, vale o portal oficial.
