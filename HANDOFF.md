# Portal Contábil — HANDOFF

Portal em que o cliente do escritório contábil envia os documentos do mês e o sistema gera a
planilha de importação do **Alterdata**. Uma instância (stack) por escritório; o que muda é env.

> ⚠️ **Este repositório é PÚBLICO.** Nenhum dado de cliente entra aqui: documentos, planilhas,
> valores, CNPJs, contas. O `.gitignore` bloqueia pdf/ofx/xml/xls; mesmo assim, conferir o
> `git diff --staged` antes de cada commit. A especificação (MAPEAMENTO), o roteiro (PLANO) e as
> amostras reais ficam numa pasta do projeto **fora do repositório**, apontada por `AMOSTRAS_DIR`.

## Estado (17/10/2026)

Fase 1 (demo) construída. Validado só com: DAS (PDF) e comprovante Sicoob (PDF-imagem, OCR).

- `pytest`: os testes com dados inventados rodam sempre; os que usam as amostras reais leem
  `AMOSTRAS_DIR/esperado.json` e são pulados sem ela.
- Fumaça pela API (login → troca de senha → cadastro → envio → recusa de foto/repetido → casamento
  → download → arquivo só com login) e QA no navegador: limpos.
- **OCR dentro do container**: Tesseract 5.5 + `tessdata/por.traineddata` (tessdata_best) dá o
  mesmo resultado do local (~90% de confiança, código de barras consertado pelo DV); ~7 s por
  comprovante.

## Como funciona

```
arquivo → leitura/entrada.py (formato pelo conteúdo; recusa imagem)
        → PDF com texto: das.py | boleto.py (linha digitável)      PDF sem texto: OCR → comprovante_sicoob.py
        → OFX: ofx.py (uma linha de extrato por transação)
        → fatos (JSON na tabela `fatos`)
casamento.py  fatos → pagamentos + pendências   (K1 código de barras; K4/K5 valor + data; K6 nome)
classificacao.py  regras (tabela) → lancto auto, histórico, complemento
planilha.py   pagamentos ok → .xls no formato exato do modelo (A e J texto, D data, E 2 casas)
```

Pagamentos e pendências são **recalculados** a cada consulta (determinístico); só documentos,
fatos, regras e downloads ficam gravados.

- **Vários documentos do mesmo pagamento = uma linha.**
- **Data: extrato › comprovante › vencimento da guia.** No comprovante do Sicoob a data e hora do
  pagamento são o "gerado em" do quadro azul (a linha "Pagamento efetuado" sai "null"; confirmado
  em 21/10); a linha logo abaixo do valor é texto digitado pelo pagador. Comprovante com data basta
  sozinho. O vencimento só entra quando o comprovante não traz nenhuma data (linha marcada:
  "vencimento" + pendência informativa DV). Agendamento, ou comprovante sem data e sem guia → P3.
- **Leitor melhorou? Reprocesse.** A leitura fica gravada no envio. `reprocessar.py` relê os
  documentos ativos com os leitores atuais (todos, ou por id).
- **Código do lançamento automático:** a regra do DAS é semeada sem código; a coluna A sai em
  branco e aparece a pendência CL. Não inventar código: quando a tabela do escritório chegar, é
  `UPDATE regras SET lancto_auto = …, cod_historico = …`.
- Pendência aberta vem antes de "Baixada" na situação do cliente.

## Rodar local

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt
cp .env.example .env          # preencher (Postgres local, AMOSTRAS_DIR)
.venv/Scripts/python -X utf8 init_db.py
PORT=5077 USAR_WAITRESS=1 .venv/Scripts/python -X utf8 server.py
.venv/Scripts/python -m pytest -q
```
OCR local no Windows: Tesseract 5.4 (winget `UB-Mannheim.TesseractOCR`); o modelo vem de
`tessdata/` do projeto (o instalador só traz inglês).

Usuários da equipe (sem tela ainda), dentro do container ou local:
`python -X utf8 usuarios_cli.py criar|senha|listar`.

## Deploy (servidor JOGA, Swarm + Traefik)

1. Push na `main` → o Actions publica `ghcr.io/jogasolucoesempresarias-debug/contabilidade:latest`.
2. DNS `contabilidade.jogasolucoes.com.br` → servidor JOGA (feito em 17/10).
3. Stack no Portainer com `docker-compose.prod.yml` (Postgres próprio). Segredos no env da stack
   ou no YAML colado no Portainer — **nunca** commitados aqui.
4. O container roda `init_db.py` a cada subida (idempotente) e cria o admin de `ADMIN_EMAIL`.
5. `curl -s https://contabilidade.jogasolucoes.com.br/health`
6. Depois de um deploy que muda leitor, reprocessar os documentos já enviados:
   `docker exec $(docker ps -q -f name=contabilidade_contabilidade-app) python -X utf8 reprocessar.py`
7. Usuários do escritório:
   `docker exec $(docker ps -q -f name=contabilidade_contabilidade-app) python -X utf8 usuarios_cli.py criar email "Nome" operador`

Os volumes `contabilidade-pgdata` e `contabilidade-docs` guardam dado de cliente: entram no backup.

## Limites conhecidos (aceitos para a demo)

- Uma conexão de banco por consulta e `/api/clientes` recalcula o mês de cada cliente: com
  centenas de clientes vai pesar. Antes de escalar: pool + resumo por cliente.
- OCR síncrono no envio (~5–7 s por comprovante): ok para a demo; fila se o volume crescer.
- XML (nota fiscal) e extrato em PDF ainda não são lidos.
- Juros/multa vão no valor total, com pendência informativa JM, até a regra do escritório.

## Não fazer

- Não usar PyMuPDF (AGPL). Não aceitar foto. Não inventar código de lançamento.
- Não commitar documento, valor ou identificação de cliente — nem em teste (use `esperado.json`
  fora do repositório).
