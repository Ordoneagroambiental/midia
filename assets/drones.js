/* The quote is assembled locally; the visitor explicitly sends it in WhatsApp. */
(() => {
  'use strict';
  const form = document.getElementById('drone-quote-form');
  if (!form) return;
  const result = document.getElementById('drone-quote-result');
  const link = document.getElementById('drone-quote-link');
  const preview = document.getElementById('drone-quote-preview');
  const service = document.getElementById('drone-service');

  document.querySelectorAll('[data-drone-service]').forEach(item => {
    item.addEventListener('click', () => {
      service.value = item.dataset.droneService;
      result.hidden = true;
    });
  });

  // Editing a prepared quote invalidates its link until it is generated again.
  form.addEventListener('input', () => { result.hidden = true; });
  form.addEventListener('change', () => { result.hidden = true; });
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const fields = new FormData(form);
    const value = name => String(fields.get(name) || '').trim();
    const optional = name => value(name) || 'Não informado';
    const message = [
      'Olá, Ordone! Quero solicitar um orçamento de serviço com drone agrícola.',
      '',
      'Nome: ' + value('nome'),
      'WhatsApp: ' + value('contato'),
      'Local: ' + value('municipio') + ' / ' + value('uf'),
      'Cultura ou vegetação: ' + value('cultura'),
      'Serviço: ' + value('servico'),
      'Área: ' + (value('area') ? value('area') + ' ha' : 'A confirmar'),
      'Data ou janela desejada: ' + optional('prazo'),
      'Insumo previsto: ' + optional('insumo'),
      'Água disponível: ' + optional('agua'),
      'Acesso à área: ' + optional('acesso'),
      'Observações: ' + optional('observacoes'),
      '',
      'Se disponível, enviarei o KML/KMZ e as fotos nesta conversa.'
    ].join('\n');
    link.href = 'https://wa.me/5562982315179?text=' + encodeURIComponent(message);
    preview.textContent = message;
    result.hidden = false;
    result.focus({ preventScroll: true });
    result.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'nearest' });
  });
})();
