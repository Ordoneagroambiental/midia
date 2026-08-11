# Backend gratuito opcional — Ordone

Esta pasta contém um Google Apps Script pronto para receber os pré-atendimentos.

## Como ativar
1. Criar uma planilha no Google Sheets.
2. Abrir Extensões → Apps Script.
3. Colar `Code.gs`.
4. Trocar `SEU_EMAIL_AQUI` pelo e-mail que receberá aviso.
5. Implantar como Aplicativo da Web.
6. Copiar a URL `/exec`.
7. Colar a URL em `assets/lead-config.js`.

## O que fica gratuito
- Google Sheets como CRM inicial.
- Google Apps Script como endpoint.
- E-mail de aviso pelo Gmail/Google.
- Site hospedado no GitHub Pages.

## Anexos
A V7 não envia arquivos automaticamente ao Google Drive. Isso é intencional: primeiro deve ser definida a política de armazenamento e acesso aos documentos. Até lá, o site lista os arquivos e direciona o usuário para enviá-los pelo WhatsApp.

## Resultado
Cada novo pré-atendimento pode gerar uma linha na planilha:
data, nome, WhatsApp, município, demanda, área, prazo, órgão, descrição, respostas específicas e arquivos disponíveis.
