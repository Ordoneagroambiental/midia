/**
 * ORDONE AGROAMBIENTAL — CAPTAÇÃO GRATUITA
 * Google Apps Script + Google Sheets + Google Drive
 *
 * 1) Crie uma planilha Google.
 * 2) Extensões > Apps Script.
 * 3) Cole este código.
 * 4) Altere NOTIFY_EMAIL.
 * 5) Implantar > Nova implantação > Aplicativo da Web.
 * 6) Executar como você; acesso: qualquer pessoa.
 * 7) Copie a URL /exec para o arquivo assets/lead-config.js do site.
 *
 * Esta versão recebe dados do lead e cria uma linha na planilha.
 * Arquivos podem continuar sendo enviados pelo WhatsApp enquanto
 * não houver uma política de armazenamento de anexos definida.
 */

const SHEET_NAME = 'Leads';
const NOTIFY_EMAIL = 'SEU_EMAIL_AQUI';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents || '{}');
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    let sheet = ss.getSheetByName(SHEET_NAME);

    if (!sheet) {
      sheet = ss.insertSheet(SHEET_NAME);
      sheet.appendRow([
        'Data/Hora','Nome','WhatsApp','Município','Demanda','Área',
        'Prazo','Órgão','Descrição','Respostas específicas','Arquivos'
      ]);
    }

    sheet.appendRow([
      new Date(),
      data.nome || '',
      data.telefone || '',
      data.municipio || '',
      data.demanda || '',
      data.area || '',
      data.prazo || '',
      data.orgao || '',
      data.descricao || '',
      JSON.stringify(data.respostas || {}),
      (data.arquivos || []).join(', ')
    ]);

    if (NOTIFY_EMAIL && NOTIFY_EMAIL !== 'SEU_EMAIL_AQUI') {
      const subject = 'Novo lead — Ordone Agroambiental';
      const body =
        'Novo pré-atendimento recebido.\n\n' +
        'Nome: ' + (data.nome || '') + '\n' +
        'WhatsApp: ' + (data.telefone || '') + '\n' +
        'Município: ' + (data.municipio || '') + '\n' +
        'Demanda: ' + (data.demanda || '') + '\n' +
        'Área: ' + (data.area || '') + '\n' +
        'Prazo: ' + (data.prazo || '') + '\n' +
        'Órgão: ' + (data.orgao || '') + '\n' +
        'Descrição: ' + (data.descricao || '') + '\n\n' +
        'Respostas: ' + JSON.stringify(data.respostas || {}, null, 2);

      MailApp.sendEmail(NOTIFY_EMAIL, subject, body);
    }

    return ContentService
      .createTextOutput(JSON.stringify({ok:true}))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ok:false,error:String(err)}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
