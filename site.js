
function wa(message){
  const phone="5562982315179";
  window.open("https://wa.me/"+phone+"?text="+encodeURIComponent(message),"_blank");
}
document.querySelectorAll("[data-wa]").forEach(el=>el.addEventListener("click",e=>{
  e.preventDefault(); wa(el.dataset.wa);
}));

const fileInput=document.querySelector('input[type="file"]');
if(fileInput){
  fileInput.addEventListener("change",()=>{
    const box=document.querySelector("#file-list");
    if(!box) return;
    const names=[...fileInput.files].map(f=>f.name);
    box.style.display=names.length?"block":"none";
    box.innerHTML=names.length ? "<b>Arquivos selecionados:</b><br>"+names.map(n=>"• "+n).join("<br>") : "";
  });
}

const form=document.querySelector("#assessment-form");
if(form){
  form.addEventListener("submit",e=>{
    e.preventDefault();
    const data=Object.fromEntries(new FormData(form).entries());
    const files=fileInput ? [...fileInput.files].map(f=>f.name) : [];
    const text=`Olá! Fiz a triagem inicial da Ordone.

Nome: ${data.nome}
WhatsApp: ${data.telefone}
Município: ${data.municipio}
Demanda: ${data.demanda}
Área: ${data.area||"não informada"}
Prazo: ${data.prazo||"não informado"}
Órgão: ${data.orgao||"não informado"}
Descrição: ${data.descricao||"não informada"}
Arquivos: ${files.length ? files.join(", ") : "nenhum selecionado"}`;
    const result=document.querySelector("#lead-result");
    result.innerHTML=`<div class="note"><b>Triagem organizada.</b><br>
      O site não envia os arquivos automaticamente nesta versão gratuita. Eles ficam apenas selecionados no seu computador.
      <br><br><a class="btn btn-gold" href="https://wa.me/5562982315179?text=${encodeURIComponent(text)}" target="_blank" rel="noopener">Enviar ficha pelo WhatsApp</a>
      <p style="margin:10px 0 0;color:#59655f;font-size:12px">Depois, os arquivos podem ser enviados na própria conversa.</p></div>`;
  });
}

// V6: local conversion markers. No external analytics or cookies are used.
document.querySelectorAll('a[href*="whatsapp"]').forEach(a=>{
  a.addEventListener("click",()=>{try{localStorage.setItem("ordone_last_whatsapp_click",new Date().toISOString())}catch(e){}});
});

// V7 — envio opcional para Google Apps Script / Google Sheets
(function(){
  const btn=document.getElementById("generate-lead");
  const endpoint=window.ORDONE_LEAD_ENDPOINT||"";
  const typeSelect=document.getElementById("demand-type");
  if(!btn || !typeSelect) return;

  btn.addEventListener("click", async function(){
    const type=typeSelect.value;
    const name=(document.getElementById("lead-name")||{}).value?.trim()||"";
    const phone=(document.getElementById("lead-phone")||{}).value?.trim()||"";
    const city=(document.getElementById("lead-city")||{}).value?.trim()||"";
    const area=(document.getElementById("lead-area")||{}).value?.trim()||"";
    const description=(document.getElementById("lead-description")||{}).value?.trim()||"";
    const files=[...(document.getElementById("lead-files")?.files||[])].map(f=>f.name);
    const output=document.getElementById("lead-output");

    if(!type||!name||!phone||!city){
      output.innerHTML='<div class="notice"><b>Falta pouco.</b> Preencha a situação, nome, WhatsApp e município.</div>';
      return;
    }

    const respostas={};
    document.querySelectorAll("#dynamic-fields input,#dynamic-fields select,#dynamic-fields textarea").forEach(el=>{
      if(el.value) respostas[el.dataset.question||el.id]=el.value;
    });

    const labels = {
      notificacao:"Notificação / exigência",prad:"Recuperação / PRAD / PRADA",
      erosao:"Erosão / talude",solo:"Análise de solo",mapa:"Mapa / KML / KMZ",
      vegetacao:"Vegetação / inventário",agua:"Água / APP / nascente",
      monitoramento:"Monitoramento",drone:"Drone / geotecnologia",outro:"Outro"
    };

    const payload={
      nome:name, telefone:phone, municipio:city,
      demanda:labels[type]||type, area:area,
      prazo:respostas["Existe prazo?"]||"",
      orgao:respostas["Órgão/entidade que emitiu"]||"",
      descricao:description,
      respostas:respostas, arquivos:files
    };

    let sent=false;
    if(endpoint){
      try{
        output.innerHTML='<div class="notice"><b>Enviando pré-atendimento...</b></div>';
        const response=await fetch(endpoint,{
          method:"POST",
          mode:"no-cors",
          headers:{"Content-Type":"text/plain;charset=utf-8"},
          body:JSON.stringify(payload)
        });
        sent=true;
      }catch(err){
        sent=false;
      }
    }

    const whatsapp=[
      "Olá! Fiz o pré-atendimento pelo site da Ordone.",
      "Nome: "+name,"WhatsApp: "+phone,"Município/UF: "+city,
      "Demanda: "+payload.demanda,"Área: "+(area||"não informada"),
      ...Object.entries(respostas).map(([k,v])=>k+": "+v),
      "Descrição: "+(description||"não informada"),
      "Arquivos disponíveis: "+(files.length?files.join(", "):"nenhum selecionado")
    ].join("\n");

    const wa="https://wa.me/5562982315179?text="+encodeURIComponent(whatsapp);
    output.innerHTML='<div class="notice"><b>'+(sent?'Pré-atendimento registrado.':'Ficha pronta.')+
      '</b><p>'+(sent?'As informações foram encaminhadas para a base de leads.':'O backend ainda não está conectado; a ficha está pronta para envio.')+
      '</p><a class="btn btn-gold" target="_blank" rel="noopener" href="'+wa+'">Enviar também pelo WhatsApp</a>'+
      '<p style="font-size:12px;margin-top:10px">Arquivos não são armazenados automaticamente nesta etapa.</p></div>';
  });
})();


// V2.0 — navegação móvel e cartões de atualidades oficiais
(function(){
  const btn=document.querySelector('.nav-toggle');
  const menu=document.querySelector('.menu');
  if(btn && menu){
    btn.addEventListener('click',()=>{
      const open=menu.classList.toggle('is-open');
      btn.setAttribute('aria-expanded', String(open));
    });
  }
})();

(function(){
  const target=document.getElementById('latest-official-news');
  if(!target) return;
  const base=document.body.dataset.base || '';
  fetch(base+'dados/atualidades.json',{cache:'no-store'})
    .then(r=>{if(!r.ok) throw new Error('feed'); return r.json()})
    .then(data=>{
      const items=(data.items||[]).slice(0,6);
      if(!items.length) return;
      target.innerHTML=items.map(item=>`<article class="news-card">
        <div class="meta">${escapeHtml(item.fonte||'Fonte oficial')} · ${escapeHtml(item.data||'')}</div>
        <h3>${escapeHtml(item.titulo||'Atualização oficial')}</h3>
        <a href="${safeUrl(item.url)}" target="_blank" rel="noopener noreferrer">Abrir na fonte oficial →</a>
      </article>`).join('');
      const stamp=document.getElementById('news-updated-at');
      if(stamp && data.atualizado_em) stamp.textContent='Coleta do painel: '+data.atualizado_em;
    }).catch(()=>{});
  function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
  function safeUrl(u){try{const x=new URL(u); return ['http:','https:'].includes(x.protocol)?x.href:'#'}catch(e){return '#'}}
})();

(function(){
  const buttons=[...document.querySelectorAll('[data-resource-filter]')];
  const cards=[...document.querySelectorAll('[data-resource-type]')];
  if(!buttons.length) return;
  buttons.forEach(btn=>btn.addEventListener('click',()=>{
    buttons.forEach(b=>b.classList.remove('active')); btn.classList.add('active');
    const filter=btn.dataset.resourceFilter;
    cards.forEach(c=>c.hidden=!(filter==='todos'||c.dataset.resourceType.includes(filter)));
  }));
})();


// V3.7.2 — Radar Ordone: leitura, filtragem defensiva e apresentação comercial.
(function(){
  const target=document.getElementById('radar-opportunity-list');
  if(!target) return;
  const base=document.body.dataset.base || '';
  let radarItems=[];
  const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const safe=u=>{try{const x=new URL(u,location.href);return ['http:','https:'].includes(x.protocol)?x.href:'#'}catch(e){return '#'}};
  const brl=v=>{if(v===null||v===undefined||v==='') return ''; try{return new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}).format(Number(v))}catch(e){return ''}};
  const norm=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\s+/g,' ').trim();
  const genericTitles=new Set(['ver todos os servicos','todos os servicos','servicos','saiba mais','leia mais','ver mais','acesse','acessar','clique aqui','inicio','home','sobre','sobre a cidade','noticias','mais noticias','contato']);
  const generic=x=>genericTitles.has(norm(x?.titulo||''));
  const regionWeight=x=>({"Goianésia":0,"Entorno imediato":1,"Região ampliada":2,"Goiás":3,"Brasil":4}[x?.regiao_prioridade]??5);
  function localRegion(item){return ['Goianésia','Entorno imediato','Região ampliada'].includes(item.regiao_prioridade)}
  function draw(filter='todos'){
    const items=radarItems.filter(x=>filter==='todos'||(filter==='local'&&localRegion(x))||(filter==='formal'&&x.tipo==='DEMANDA FORMAL')||(filter==='alta'&&x.prioridade==='ALTA'));
    if(!items.length){target.innerHTML='<article class="radar-empty"><h3>Nenhum registro neste filtro.</h3><p>A coleta foi concluída, mas nenhum sinal passou pelos critérios deste filtro. Isso não significa ausência de demanda no território.</p></article>';return;}
    target.innerHTML=items.map(x=>`<article class="radar-card" data-priority="${esc(x.prioridade||'')}">
      <div class="radar-card-head">
        <div class="radar-tags"><span class="radar-badge">${esc(x.tipo||'SINAL')}</span>${x.confirmacao?`<span class="radar-confirm">${esc(x.confirmacao)}</span>`:''}</div>
        <span class="radar-score">${esc(x.prioridade||'')} · ${esc(x.score||0)}/100</span>
      </div>
      <h3>${esc(x.titulo||'Oportunidade pública')}</h3>
      <div class="radar-meta"><span class="radar-location">${esc([x.municipio,x.uf].filter(Boolean).join(' / ')||'Local não informado')}</span><span>${esc(x.fonte||'Fonte pública')}</span></div>
      ${x.organizacao?`<p class="radar-org"><b>Organização</b><span>${esc(x.organizacao)}</span></p>`:''}
      <div class="radar-service-block"><b>Como a Ordone pode atuar</b><p>${esc((x.servicos_ordone||[]).join(' · ')||'Avaliação técnica inicial')}</p></div>
      <div class="radar-details">${x.prazo?`<span><b>Prazo</b> ${esc(x.prazo)}</span>`:''}${brl(x.valor_estimado)?`<span><b>Estimado</b> ${esc(brl(x.valor_estimado))}</span>`:''}${x.modalidade?`<span>${esc(x.modalidade)}</span>`:''}</div>
      <p class="radar-action">${esc(x.proxima_acao||'Abrir a fonte e validar o contexto.')}</p>
      <a class="card-link" href="${safe(x.url)}" target="_blank" rel="noopener noreferrer">Abrir fonte oficial →</a>
    </article>`).join('');
  }
  fetch(base+'dados/radar_oportunidades.json',{cache:'no-store'})
    .then(r=>{if(!r.ok) throw new Error('radar'); return r.json()})
    .then(data=>{
      radarItems=(data.items||[]).filter(x=>!generic(x)).sort((a,b)=>regionWeight(a)-regionWeight(b)||(Number(b.score)||0)-(Number(a.score)||0)).slice(0,30);
      const r=data.resumo||{};
      const boxes=document.querySelectorAll('#radar-summary article b');
      const visible={
        total:radarItems.length,
        local:radarItems.filter(localRegion).length,
        formal:radarItems.filter(x=>x.tipo==='DEMANDA FORMAL').length,
        sinais:radarItems.filter(x=>x.tipo==='SINAL AMBIENTAL'||x.tipo==='SINAL DE CONTRATAÇÃO').length
      };
      [visible.total,visible.local,visible.formal,visible.sinais].forEach((v,i)=>{if(boxes[i]) boxes[i].textContent=v});
      const stamp=document.getElementById('radar-updated-at');
      if(stamp){
        if(data.status==='coleta_concluida') stamp.textContent='Última coleta concluída: '+(data.atualizado_em||'agora');
        else stamp.textContent=data.atualizado_em?'Atualização: '+data.atualizado_em:'Radar aguardando coleta';
      }
      draw('todos');
    }).catch(()=>{
      const stamp=document.getElementById('radar-updated-at'); if(stamp) stamp.textContent='Não foi possível ler a última coleta do Radar.';
    });
  document.querySelectorAll('[data-radar-filter]').forEach(btn=>btn.addEventListener('click',()=>{
    document.querySelectorAll('[data-radar-filter]').forEach(b=>b.classList.remove('active')); btn.classList.add('active'); draw(btn.dataset.radarFilter);
  }));
})();
