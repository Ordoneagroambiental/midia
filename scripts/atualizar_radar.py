#!/usr/bin/env python3
"""Radar Ordone V3.7.

Coleta apenas informações públicas. Não envia e-mails, mensagens ou contatos.
O resultado público é sanitizado e serve como triagem de sinais/oportunidades.
Contato comercial só ocorre depois de validação e aprovação humana.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
import argparse, json, re, time, hashlib
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'dados'/'radar_config.json'
OUT=ROOT/'dados'/'radar_oportunidades.json'
UA={'User-Agent':'Mozilla/5.0 (compatible; OrdoneRadar/3.7; +https://ordoneagroambiental.github.io/midia/)','Accept':'application/json,text/html;q=0.9,*/*;q=0.8'}


def load_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except Exception: return default

def norm(text):
    import unicodedata
    s=unicodedata.normalize('NFKD',str(text or '')).encode('ascii','ignore').decode('ascii').lower()
    return re.sub(r'\s+',' ',s).strip()

def clean(text, n=600):
    return re.sub(r'\s+',' ',str(text or '')).strip()[:n]

def safe_url(u):
    try:
        x=urlparse(str(u or ''))
        return str(u) if x.scheme in ('http','https') and x.netloc else ''
    except Exception: return ''

def money(v):
    try: return round(float(v),2)
    except Exception: return None

def geography_score(city, uf, cfg):
    c=norm(city); uf=(uf or '').upper()
    geo=cfg['prioridade_geografica']
    if c==norm('Goianésia'): return 25,'Goianésia'
    if c in {norm(x) for x in geo['entorno_imediato']}: return 20,'Entorno imediato'
    if c in {norm(x) for x in geo['regiao_ampliada']}: return 15,'Região ampliada'
    if uf=='GO': return 10,'Goiás'
    return 5,'Brasil'

def keyword_hits(text,cfg):
    t=norm(text)
    if any(norm(x) in t for x in cfg.get('termos_excluir',[])):
        return []
    hits=[]
    for kw in cfg['palavras_chave']:
        if norm(kw) in t:
            hits.append(kw)
    # remove duplicatas preservando ordem
    seen=set(); out=[]
    for h in hits:
        k=norm(h)
        if k not in seen: seen.add(k); out.append(h)
    return out

def services_from(text):
    t=norm(text); out=[]
    def add(label,*terms):
        if any(norm(x) in t for x in terms) and label not in out: out.append(label)
    add('Recuperação ambiental / PRAD','recuperacao ambiental','area degradada','prad','prada','restauracao florestal','revegetacao','reflorestamento')
    add('Irrigação e automação','irrigacao','gotejamento','aspersao','fertirrigacao','automacao','bombeamento','reservatorio')
    add('Solo e conservação','erosao','assoreamento','conservacao do solo','analise de solo','fertilidade do solo','drenagem')
    add('Bioengenharia e controle de sedimentos','palicada','bioengenharia','sedimento','assoreamento')
    add('Geotecnologia / drone','geoprocessamento','georreferenciamento','topografia','drone','aerolevantamento','mapeamento')
    add('Licenciamento e regularização','licenciamento ambiental','regularizacao ambiental','condicionante ambiental','outorga','supressao vegetal')
    add('Plantio, viveiros e compensação','plantio compensatorio','mudas nativas','viveiro','compensacao ambiental','inventario florestal')
    add('Recursos hídricos e nascentes','nascente','recursos hidricos','app')
    add('Monitoramento ambiental','monitoramento ambiental')
    return out or ['Avaliação técnica inicial']

def priority(score):
    if score>=80: return 'ALTA'
    if score>=60: return 'MÉDIA'
    if score>=40: return 'ACOMPANHAR'
    return 'INTELIGÊNCIA'

def score_item(city,uf,text,kind,cfg,deadline=''):
    score,region=geography_score(city,uf,cfg)
    hits=keyword_hits(text,cfg)
    score += min(45, 9*len(hits))
    if kind=='DEMANDA FORMAL': score += 15
    if deadline:
        try:
            d=datetime.fromisoformat(deadline.replace('Z','+00:00')).date()
            days=(d-datetime.now().date()).days
            if 0<=days<=15: score += 10
            elif 16<=days<=45: score += 5
        except Exception: pass
    return min(100,score),region,hits

def pncp_rows(cfg):
    """Consulta propostas abertas no PNCP em três camadas.

    1) Goianésia pelo código IBGE, com maior profundidade;
    2) todo o Estado de Goiás;
    3) amostra nacional para não perder oportunidades de grande aderência.

    A API oficial exige modalidade; códigos sem resposta útil são ignorados.
    """
    base='https://pncp.gov.br/api/consulta/v1/contratacoes/proposta'
    final=(datetime.now().date()+timedelta(days=90)).strftime('%Y%m%d')
    out=[]; seen=set()
    # A ordem materializa a prioridade comercial. O código 5208608 é Goianésia/GO (IBGE).
    scopes=[
        ('Goianésia', {'uf':'GO','codigoMunicipioIbge':5208608}, 4),
        ('Goiás', {'uf':'GO'}, 3),
        ('Brasil', {}, 1),
    ]
    for scope_name,scope_params,max_pages in scopes:
      for modalidade in range(1,21):
        page=1
        while page<=max_pages:
            params={'dataFinal':final,'codigoModalidadeContratacao':modalidade,'pagina':page,'tamanhoPagina':500,**scope_params}
            try:
                r=requests.get(base,params=params,headers=UA,timeout=25)
                if r.status_code in (204,404,422): break
                if r.status_code==429:
                    time.sleep(4); break
                if r.status_code>=400: break
                data=r.json()
            except Exception as exc:
                print('PNCP falhou',scope_name,modalidade,page,exc); break
            rows=data.get('data') or []
            for x in rows:
                key=str(x.get('numeroControlePNCP') or '')
                if key and key in seen: continue
                text=' '.join([
                    str(x.get('objetoCompra') or ''),
                    str(x.get('informacaoComplementar') or ''),
                    str((x.get('orgaoEntidade') or {}).get('razaoSocial') or ''),
                    str((x.get('unidadeOrgao') or {}).get('nomeUnidade') or '')
                ])
                hits=keyword_hits(text,cfg)
                if not hits: continue
                unit=x.get('unidadeOrgao') or {}
                city=unit.get('municipioNome') or unit.get('nomeMunicipio') or ''
                uf=unit.get('ufSigla') or unit.get('siglaUf') or (scope_params.get('uf') or '')
                # Quando a consulta é municipal e o retorno não repete o nome, podemos usar
                # somente o município que foi explicitamente usado como filtro da API oficial.
                if not city and scope_name=='Goianésia': city='Goianésia'
                deadline=str(x.get('dataEncerramentoProposta') or '')
                score,region,hits=score_item(city,uf,text,'DEMANDA FORMAL',cfg,deadline)
                source=safe_url(x.get('linkSistemaOrigem')) or 'https://pncp.gov.br/app/editais'
                item={
                    'id':key or f'pncp-{scope_name}-{modalidade}-{len(out)+1}',
                    'tipo':'DEMANDA FORMAL','confirmacao':'CONFIRMADO','fonte':'PNCP',
                    'titulo':clean(x.get('objetoCompra'),240),
                    'municipio':clean(city,80),'uf':clean(uf,2),'regiao_prioridade':region,
                    'organizacao':clean((x.get('orgaoEntidade') or {}).get('razaoSocial'),160),
                    'data_publicacao':clean(x.get('dataPublicacaoPncp'),40),'prazo':clean(deadline,40),
                    'valor_estimado':money(x.get('valorTotalEstimado')),
                    'modalidade':clean(x.get('modalidadeNome'),80),
                    'servicos_ordone':services_from(text),'palavras_encontradas':hits[:8],
                    'score':score,'prioridade':priority(score),'url':source,
                    'numero_controle_pncp':key,'escopo_coleta':scope_name,
                    'proxima_acao':'Abrir o aviso/edital na fonte oficial, validar escopo, habilitação, prazo e viabilidade de proposta.'
                }
                out.append(item)
                if key: seen.add(key)
            total=int(data.get('totalPaginas') or 1)
            if not rows or page>=total: break
            page+=1
        time.sleep(.12)
    return out

def html_signals(cfg):
    sources=[
      ('Prefeitura de Goianésia','https://goianesia.go.gov.br/','Goianésia','GO'),
      ('Editais de Goianésia','https://goianesia.go.gov.br/editais-e-publicacoes/','Goianésia','GO'),
      ('SEMAD Goiás','https://goias.gov.br/meioambiente/','','GO'),
    ]
    out=[]; seen=set()
    for fonte,url,default_city,default_uf in sources:
        try:
            r=requests.get(url,headers=UA,timeout=25); r.raise_for_status()
            soup=BeautifulSoup(r.text,'html.parser')
        except Exception as exc:
            print('HTML falhou',fonte,exc); continue
        for a in soup.find_all('a',href=True):
            title=clean(a.get_text(' ',strip=True),260)
            if len(title)<24: continue
            href=safe_url(urljoin(url,a['href']))
            if not href or urlparse(href).netloc!=urlparse(url).netloc: continue
            hits=keyword_hits(title,cfg)
            if not hits: continue
            k=(norm(title),href)
            if k in seen: continue
            seen.add(k)
            city=default_city
            # Reconhece cidade explicitamente mencionada; não deduz endereço de terceiros.
            for name in cfg['prioridade_geografica']['prioridade_1']+cfg['prioridade_geografica']['entorno_imediato']+cfg['prioridade_geografica']['regiao_ampliada']:
                if norm(name) in norm(title): city=name; break
            formal='licit' in norm(title) or 'edital' in norm(title) or 'contrat' in norm(title)
            kind='DEMANDA FORMAL' if formal else 'SINAL AMBIENTAL'
            score,region,hits=score_item(city,default_uf,title,kind,cfg,'')
            if score<40: continue
            out.append({
              'id':'web-'+hashlib.sha1(('||'.join(k)).encode('utf-8')).hexdigest()[:12], 'tipo':kind,'confirmacao':'CONFIRMADO','fonte':fonte,
              'titulo':title,'municipio':city,'uf':default_uf,'regiao_prioridade':region,'organizacao':fonte,
              'data_publicacao':'','prazo':'','valor_estimado':None,'modalidade':'',
              'servicos_ordone':services_from(title),'palavras_encontradas':hits[:8],
              'score':score,'prioridade':priority(score),'url':href,
              'proxima_acao':'Abrir a publicação oficial e confirmar se existe demanda técnica, contratação ou apenas informação institucional.'
            })
            if len(out)>=18: break
    return out

def dedupe_sort(items):
    seen=set(); out=[]
    for x in sorted(items,key=lambda z:(-int(z.get('score',0)), z.get('municipio',''),z.get('titulo',''))):
        key=(norm(x.get('titulo')),norm(x.get('organizacao')),norm(x.get('municipio')))
        if key in seen: continue
        seen.add(key); out.append(x)
    return out[:30]

def build_output(cfg,items):
    local=set(norm(x) for x in cfg['prioridade_geografica']['prioridade_1']+cfg['prioridade_geografica']['entorno_imediato']+cfg['prioridade_geografica']['regiao_ampliada'])
    return {
      'versao':'3.7','atualizado_em':datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M'),
      'status':'coleta_concluida', 'prioridade':'Goianésia e entorno → Goiás → Brasil',
      'resumo':{
        'total':len(items),
        'goianesia_regiao':sum(norm(x.get('municipio')) in local for x in items),
        'goias':sum((x.get('uf') or '').upper()=='GO' for x in items),
        'demandas_formais':sum(x.get('tipo')=='DEMANDA FORMAL' for x in items),
        'sinais_ambientais':sum(x.get('tipo')=='SINAL AMBIENTAL' for x in items)
      },
      'items':items,
      'fontes_monitoradas':[{'nome':x['nome'],'url':x['url'],'automatica':x['automatica']} for x in cfg['fontes_publicas']],
      'aviso':'Sinal público não é cliente confirmado. O radar organiza oportunidades a partir de fontes públicas; qualquer contato comercial depende de validação e aprovação humana.'
    }

def self_test(cfg):
    s,r,h=score_item('Goianésia','GO','contratação de recuperação ambiental com irrigação e geoprocessamento','DEMANDA FORMAL',cfg,'')
    assert s>=60 and r=='Goianésia' and h
    s2,r2,h2=score_item('Goiânia','GO','notícia institucional sem serviço relacionado','SINAL AMBIENTAL',cfg,'')
    assert s2<40 and not h2
    assert safe_url('javascript:alert(1)')==''
    print('SELF-TEST OK',s,r,len(h))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--self-test',action='store_true'); args=ap.parse_args()
    cfg=load_json(CONFIG,{})
    if args.self_test: self_test(cfg); return
    previous=load_json(OUT,{'items':[]})
    items=[]; successes=0
    try:
        p=pncp_rows(cfg); items+=p; successes+=1; print('PNCP:',len(p))
    except Exception as exc: print('Falha geral PNCP',exc)
    try:
        h=html_signals(cfg); items+=h; successes+=1; print('Sinais HTML:',len(h))
    except Exception as exc: print('Falha geral HTML',exc)
    items=dedupe_sort(items)
    if not items and successes==0:
        print('Todas as fontes falharam; preservando resultado anterior.'); return
    data=build_output(cfg,items)
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Radar atualizado:',len(items),'itens')

if __name__=='__main__': main()
