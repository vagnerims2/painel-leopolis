# CLAUDE.md — Painel de Empenhos de Leópolis

Contexto para o Claude Code. Responda sempre em português, em linguagem simples (o dono do projeto, Vagner, não é programador).

## Quem usa e para quê
- Vagner é agente administrativo na Prefeitura Municipal de Leópolis-PR, setor de empenho e liquidação (recebimento de notas). Usa o sistema Equiplano.
- O painel controla empenhos, liquidações e pagamentos e já tem servidores usando todos os dias.
- Site no GitHub Pages: `index.html` = link público; `interno/index.html` = link dos servidores (todos os funcionários podem usar, com usuário e senha próprios; ver "Acesso").
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

## Acesso (tela de entrada do link dos servidores)
- Cada pessoa cria o próprio acesso (usuário = o seu nome + senha; sem aprovação). Nome único: maiúsculas, acentos e espaços não contam ("Maria Souza" = "maria  souza").
- Firebase do Vagner, projeto `painel-leopolis` (Authentication e-mail/senha + Firestore em São Paulo, plano grátis Spark). Coleções: `usuarios` (nome, entradas, último acesso, aparelho, bloqueado), `acessos` (cada entrada), `nomes` (nome → conta atual). E-mail interno: `nome@usuarios.painel-leopolis.app` (depois de zerar a senha, `nome+2@...`, `nome+3@...`).
- "Manter conectado neste navegador": marcado = entra direto até clicar em Sair; desmarcado = fechar o navegador desconecta. Atualizar a página não pede senha.
- Todos: botão Trocar senha (senha atual + nova duas vezes) e Sair.
- Administrador = o usuário "Vagner" (pelo e-mail interno; também aceita o campo `admin: true` no Firestore). Só ele vê o botão Usuários: lista de quem entra, quando e quantas vezes; Zerar senha (a pessoa cadastra outra em "Criar acesso" com o mesmo nome; o histórico continua junto) e Remover/Devolver acesso.
- As regras de segurança ficam no Firebase (Firestore > Regras), coladas pelo Vagner; se mudar algo nas coleções, mandar as regras novas para ele colar.
- Na prévia (Claude) o Firebase não carrega: funciona em demonstração, com usuários guardados só no navegador (crie "Vagner" para ver a lista).
- Limite: a tela identifica quem usa; os arquivos de `data/` continuam num endereço aberto do GitHub.

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
- Relatórios por secretaria (inclusive Gastos da Saúde): só por pagamento (o que foi efetivamente pago, pela data de emissão do pagamento, já descontados os estornos; nada de empenhado). A folha aparece como "Folha de pagamento dos servidores (Município de Leópolis)". Filtro de natureza: em cima, botões das naturezas principais da secretaria (ex.: Material de consumo 3.3.90.30); ao escolher uma, aparecem embaixo os desdobramentos (ex.: Material farmacológico 30.09) — sem escolher desdobramento, entra a natureza inteira. Assim a Saúde (medicamentos) e a Educação (merenda) não se misturam em 3.3.90.32.
- Relatório da Saúde: conta só a Secretaria de Saúde (SEMUS), pela data do pagamento, igual à planilha de controle que a Saúde recebe (conferida centavo por centavo nos 1º e 2º quadrimestres de 2026). Tipos: SAMU, Mensalidade, Extra cota, Saúde mental, Convênios e emendas; Santa Casa = Casa de Misericórdia de Cornélio Procópio. Pagamento ao CISNOP da conta custeio 57936-X (fonte 1018) sem descrição é extra cota (confirmado pelo Vagner).

## Abas atuais
- Ativas no link dos servidores (o Vagner usa todas): Visão geral, Dotações, Empenhos (com quadro do fornecedor e notas fiscais), Requisições (sem senha), Produtos (busca por empenho ou por nota fiscal), Licitações, Receitas, Indicadores LRF, Para o cidadão, Relatórios.
- Aba Relatórios: abre numa lista (no computador, também desce no menu lateral): "Relatório geral" (todas as secretarias) primeiro, depois um relatório por secretaria em ordem alfabética. Ao escolher, abre período (ano todo é o padrão), filtros (atalhos, natureza da despesa, fornecedor com sugestões, empenho) e "Imprimir relatório". O Relatório da Saúde tem dois botões: "Gastos da Saúde" e "CISNOP e Santa Casa" (caixinhas para um ou os dois). A antiga busca de produtos/fornecedores da aba Relatórios foi tirada (pedido do Vagner); o gráfico de barras que ela tinha continua sendo usado pela aba Receitas.
- Busca por valor: na aba Empenhos, valor com vírgula (ex.: 3.380,62) acha o empenho pelo valor empenhado, liquidado, pago ou da nota; na aba Relatório da Saúde, a caixa "Conferir um pagamento" (só na tela).
- Visão geral (aprovada em 25/10/2026): cartões no fundo escuro — Empenhado, Liquidado e Pago em linha animada mês a mês (valor do mês em cima de cada ponto), Sem liquidar (até 30 / 31–90 / mais de 90 dias + dotações que não fecham o mês), Saldo a pagar por fonte e Maiores secretarias; tocar num cartão abre a aba. Os quadros antigos da aba continuam no código, escondidos.
- Animações: linhas que "andam" (Visão geral e Gasto com pessoal em Indicadores LRF) e barras que sobem (Arrecadação por mês em Receitas — o Vagner preferiu barras ali). Começam quando o gráfico aparece na tela e recomeçam ao abrir a aba ou recarregar (F5); na impressão saem completas. Função comum: `linhaAnimada` / `animarLinhas`.
- Números (pedido do Vagner, 25/10/2026): porcentagens sempre com 2 casas, sem arredondar (28,73%); valores em reais nos gráficos e cartões ficam abreviados (R$ 37,46 mi, 4,2), e o valor completo aparece ao passar o mouse ou tocar no ponto/barra (no celular, a dica fica uns 3 segundos e o toque no ponto não troca de aba).
- Topo da página: nome de quem entrou em balão laranja, Usuários/Trocar senha/Sair em branco apagado, Imprimir verde à direita, todos do mesmo tamanho na mesma linha (no celular: "Senha" e só o ícone da impressora).
- Removidas do menu: Alertas e Dia e semana (o código continua na página, escondido). Relatório automático em PDF do painel: fora por enquanto.

## Ideias futuras
- Painel tributário (IPTU, ISS, ITBI, taxas, transferências, dívida ativa), receita prevista × arrecadada, só com dados do portal.
- Envio periódico (e-mail) do Relatório da Saúde. A aba já existe; falta só o envio automático.

## Estrutura
- `motor/`: coleta do portal e cálculo (`painel.py`, `coleta.py`, `financas.py`, `build.py`); estado inicial em `motor/semente/`.
- `ferramentas/`: geração do site, planilha, fornecedores, notas XML, pendentes, relatório de atraso, promoção da prévia.
- `data/`: arquivos lidos pelas páginas (gerados pelo robô; não editar à mão).
- Em caso de divergência, vale o portal oficial.
