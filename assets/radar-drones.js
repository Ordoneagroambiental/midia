(() => {
  'use strict';
  const list = document.getElementById('drone-opportunities');
  if (!list) return;
  const labels = {oportunidade_formal:'Oportunidade formal',parceria:'Parceria operacional',analise_pendente:'Análise pendente',prospeccao:'Prospecção comercial'};
  let data = null;
  let selected = 'oportunidade_formal';
  let loading = false;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safe = value => { try { const u = new URL(value); return u.protocol === 'https:' ? u.href : '#'; } catch { return '#'; } };
  const date = value => { const d = new Date(value); return value && Number.isFinite(d.getTime()) ? d.toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo',dateStyle:'short',timeStyle:'short'}) + ' (Brasília)' : 'Não informado'; };
  const display = value => Array.isArray(value) ? value.join(' · ') || 'Não informado' : value === null || value === undefined || value === '' ? 'Não informado' : String(value);
  function activeItems() {
    return (data?.oportunidades || []).filter(x => {
      if (!labels[x.classificacao]) return false;
      if (x.classificacao === 'prospeccao' && !x.prazo_final) return true;
      const d = new Date(x.prazo_final);
      return x.prazo_final && Number.isFinite(d.getTime()) && d > new Date();
    });
  }
  function render() {
    if (!data) return;
    const items = activeItems();
    document.querySelectorAll('[data-drone-count]').forEach(el => {
      el.textContent = items.filter(x => x.classificacao === el.dataset.droneCount).length;
    });
    const uf = document.getElementById('drone-uf').value;
    const query = document.getElementById('drone-query').value.toLocaleLowerCase('pt-BR').trim();
    const filtered = items.filter(x => x.classificacao === selected && (!uf || x.uf === uf) && (!query || [x.titulo,x.objeto,x.contratante,x.municipio,...(x.servicos || [])].join(' ').toLocaleLowerCase('pt-BR').includes(query)))
      .sort((a,b) => Number(b.aderencia || 0)-Number(a.aderencia || 0));
    document.getElementById('drone-result-count').textContent = `${filtered.length} resultado(s) · ${labels[selected]}`;
    if (!filtered.length) {
      const failure = data.status_coleta === 'falha';
      const pending = selected === 'oportunidade_formal' && items.some(x => x.classificacao === 'analise_pendente');
      list.innerHTML = `<article class="dr-empty"><h2>${failure ? 'Coleta indisponível nesta tentativa.' : 'Nenhum resultado confirmado neste filtro.'}</h2><p>${failure ? 'A ausência de resultados não confirma ausência de contratos. Consulte o diagnóstico abaixo e os portais oficiais.' : pending ? 'Há processos em análise pendente. Eles ficam separados até a confirmação do objeto e dos documentos.' : 'O radar exibe somente registros compatíveis com esta categoria. A cobertura da rodada e suas limitações estão descritas abaixo.'}</p><a href="https://pncp.gov.br/app/editais" target="_blank" rel="noopener noreferrer">Consultar o PNCP →</a></article>`;
      return;
    }
    list.innerHTML = filtered.map(x => {
      const req = x.requisitos || {};
      const deadline = x.prazo_final ? date(x.prazo_final) : 'Sem contratação aberta confirmada';
      const amount = Number.isFinite(x.valor_estimado) ? new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(x.valor_estimado) : 'Não informado';
      const fields = [['Contratante',x.contratante],['Local',[x.municipio,x.uf].filter(Boolean).join(' / ')],['Modalidade',x.modalidade],['Processo',x.numero_processo],['Plataforma',x.plataforma],['Área (ha)',req.area_hectares],['Equipamentos',req.equipamentos],['Equipe',req.equipe],['Registros e ART',req.registros],['Acervo e atestados',req.acervo],['Insumos',req.insumos],['Parceiro necessário',req.parceria]];
      return `<article class="dr-card"><div class="dr-card-top"><span class="dr-tag">${escape(labels[x.classificacao])}</span><span class="dr-score">Aderência preliminar ${escape(x.aderencia ?? '—')}/100</span></div><h2>${escape(x.titulo || 'Serviço com drone')}</h2><p>${escape(x.objeto)}</p><div class="dr-deadline"><b>Prazo: ${escape(deadline)}</b><span>Valor estimado: ${escape(amount)}</span></div><details><summary>Escopo, exigências e pendências</summary><dl>${fields.map(([k,v])=>`<div><dt>${k}</dt><dd>${escape(display(v))}</dd></div>`).join('')}</dl><p><b>Leitura documental:</b> ${escape(x.documentos?.status || 'Não informada')}</p>${(x.pontos_pendentes || []).length?`<ul>${x.pontos_pendentes.map(p=>`<li>${escape(p)}</li>`).join('')}</ul>`:''}${(x.documentos?.links || []).map((d,i)=>`<p><a href="${escape(safe(typeof d === 'string'?d:d.url))}" target="_blank" rel="noopener noreferrer">Documento oficial ${i+1} →</a></p>`).join('')}</details><p class="dr-action"><b>Próxima ação:</b> ${escape(x.acao_recomendada || 'Ler o processo e conferir a habilitação antes de preparar a proposta.')}</p><a class="btn btn-primary" href="${escape(safe(x.url_oficial))}" target="_blank" rel="noopener noreferrer">Abrir processo oficial →</a><small>Verificado em ${escape(date(x.verificado_em))}. Habilitação da Ordone sujeita à conferência do edital e do acervo.</small></article>`;
    }).join('');
  }
  function diagnostics() {
    const stamp = document.getElementById('drone-updated');
    const time = new Date(data.gerado_em).getTime();
    const stale = Boolean(data.gerado_em) && (!Number.isFinite(time) || Date.now()-time > 6*3600*1000);
    stamp.textContent = data.gerado_em ? `Última tentativa: ${date(data.gerado_em)}` : 'Primeira coleta ainda não concluída';
    const status = document.getElementById('drone-status');
    const statuses = {nao_executada:'Primeira coleta ainda não concluída; aguarde a execução do robô.',completa_no_recorte:'Rodada concluída dentro do recorte configurado.',parcial:'Coleta parcial: há limites ou fontes não concluídas.',falha:'Falha na coleta: cobertura não confirmada.'};
    status.textContent = (stale?'Dados desatualizados. ':'') + (statuses[data.status_coleta] || 'Aguardando coleta.') + ' Agendamento: a cada 2 horas; execução sujeita à disponibilidade das fontes e do agendador.';
    status.className = 'dr-status ' + (stale || data.status_coleta !== 'completa_no_recorte' ? 'dr-status-warning':'');
    document.getElementById('drone-sources').innerHTML = (data.fontes || []).map(f=>`<tr><th scope="row"><a href="${escape(safe(f.url))}" target="_blank" rel="noopener noreferrer">${escape(f.nome)}</a></th><td>${escape(display(f.status))}</td><td>${escape(f.paginas_consultadas ?? 0)}</td><td>${escape(f.registros_examinados ?? 0)}</td><td>${escape(display(f.detalhes))}${(f.falhas || []).length ? `<details><summary>Falhas (${f.falhas.length})</summary><ul>${f.falhas.map(e=>`<li>${escape(e)}</li>`).join('')}</ul></details>` : ''}</td></tr>`).join('');
    const configured = data.limites && !Array.isArray(data.limites) ? Object.entries(data.limites).filter(([,v])=>v && typeof v === 'object').map(([name,v])=>`${name === 'pncp' ? 'PNCP' : 'Compras.gov.br'}: publicações dos últimos ${v.dias_publicacao} dias, até ${v.max_paginas} páginas e ${v.limite_segundos} segundos por rodada.`) : [];
    const notes = [...(Array.isArray(data.avisos)?data.avisos:[]), ...configured, ...(Array.isArray(data.limites)?data.limites:[])];
    document.getElementById('drone-coverage-notes').innerHTML = notes.map(n=>`<li>${escape(typeof n === 'string'?n:JSON.stringify(n))}</li>`).join('');
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    const button = document.getElementById('drone-refresh');
    button.disabled = true;
    try {
      const response = await fetch('dados/radar_drones.json?t='+Date.now(),{cache:'no-store'});
      if (!response.ok) throw new Error('HTTP');
      const payload = await response.json();
      if (!Array.isArray(payload.oportunidades)) throw new Error('payload');
      data = payload; diagnostics(); render();
    } catch {
      document.getElementById('drone-status').textContent = 'Não foi possível carregar os dados publicados. Tente novamente. Resultados anteriores, se visíveis, não foram revalidados.';
      document.getElementById('drone-status').className = 'dr-status dr-status-warning';
      if (!data) list.innerHTML = '<article class="dr-empty"><h2>Dados indisponíveis.</h2><p>O painel não conseguiu consultar o arquivo da coleta. Isso não significa que não existam oportunidades.</p></article>';
    } finally { loading = false; button.disabled = false; }
  }
  document.querySelectorAll('[data-drone-filter]').forEach(b=>b.addEventListener('click',()=>{
    selected=b.dataset.droneFilter;
    document.querySelectorAll('[data-drone-filter]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b));});render();
  }));
  document.getElementById('drone-uf').addEventListener('change',render);
  document.getElementById('drone-query').addEventListener('input',render);
  document.getElementById('drone-refresh').addEventListener('click',refresh);
  refresh();
  setInterval(refresh,300000);
  setInterval(render,60000);
})();
