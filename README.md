# YouTube Music Link Scraper (Playwright)

Automação em Python + Playwright para pesquisar músicas no YouTube, abrir o primeiro vídeo válido e salvar os links.

## Requisitos

- Python 3.11+
- Google Chrome/Chromium

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Uso

Arquivo de entrada padrão: `musicas.txt` (1 música por linha).

```bash
python youtube_scraper.py \
  --input musicas.txt \
  --output links.txt \
  --errors erros.txt \
  --headless false \
  --limit 100 \
  --delay-ms 1200 \
  --timeout 30000 \
  --delimiter tab
```

### Opções principais

- `--input`: caminho do TXT de entrada.
- `--output`: caminho do TXT de saída.
- `--errors`: caminho do arquivo de erros.
- `--limit`: limita quantas músicas processar (0 = sem limite).
- `--delay-ms`: atraso entre buscas.
- `--timeout`: timeout de carregamento em ms.
- `--headless`: `true` ou `false`.
- `--delimiter`: `tab` ou `comma`.
- `--dedupe`: evita reprocessar músicas repetidas (usa cache em memória).
- `--resume`: continua a partir do tamanho atual de `links.txt`.
- `--include-meta`: inclui título e canal como colunas extras.
- `--output-json`: salva resultados também em JSON.

## Saída

`links.txt` contém 2 colunas (música, URL) separadas por TAB (ou vírgula) e mantém a ordem do arquivo de entrada. Se `--include-meta` for usado, adiciona mais duas colunas: título e canal.

`erros.txt` registra falhas com música, motivo e timestamp.

## Observações

- Se o YouTube mostrar consentimento de cookies ou prompts de login, o script tenta fechar automaticamente.
- Em caso de bloqueios, aumente `--delay-ms`, rode em modo visível (`--headless false`) e evite paralelismo.
- O navegador é reutilizado para todas as músicas e fechado corretamente ao final.
