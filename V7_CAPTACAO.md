# Ordone V7 — Captação sem mensalidade

## O que foi preparado
- Endpoint opcional com Google Apps Script.
- Google Sheets como base inicial de leads.
- Aviso por e-mail opcional.
- Site continua funcionando mesmo sem endpoint.
- WhatsApp continua como fallback.
- Arquivos não são armazenados automaticamente.

## Ativação
Siga `backend_google_apps_script/README.md`.

Depois cole a URL `/exec` em:
`assets/lead-config.js`

## Importante
A V7 não deve armazenar documentos automaticamente antes de definir política de acesso, retenção e segurança. Por isso, nesta etapa os nomes dos arquivos entram na ficha, mas os anexos seguem pelo WhatsApp.
