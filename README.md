# Ordone Agroambiental — Site V2.0 Integrado

Publicação preparada para GitHub Pages no caminho `https://ordoneagroambiental.github.io/midia/`.

## Novidades V2.0
- Home com foco também em produtor rural.
- Conceito de logo em teste, substituível sem alterar layout.
- Página `produtor-rural.html`.
- Página `pesquisa-aplicada.html`.
- Página `inteligencia-ambiental.html` com mapas e fontes oficiais.
- Atualidades automáticas por GitHub Actions (`.github/workflows/atualizar-atualidades.yml`).
- QA automático de links locais (`.github/workflows/verificar-site.yml`).
- Prompts mestres internos para evolução do site e do acervo.

## Teste local
`python -m http.server 8000`

## QA
`python scripts/verificar_site.py`

## Publicação
Subir **o conteúdo desta pasta diretamente na raiz do repositório** e manter GitHub Pages em `principal` + `/(root)`.
