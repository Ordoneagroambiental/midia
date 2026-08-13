
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
