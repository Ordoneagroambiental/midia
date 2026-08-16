#!/usr/bin/env python3
"""Atualiza títulos públicos de fontes oficiais para exibição no GitHub Pages.
Não interpreta normas nem produz recomendação técnica; apenas coleta links/títulos.
Falhas de coleta preservam o JSON anterior.
"""
from pathlib import Path
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone
import json, re, requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'dados'/'atualidades.json'
SOURCES=[
  {'fonte':'MMA','url':'https://www.gov.br/mma/pt-br','allow':['/mma/pt-br/noticias/','/mma/pt-br/noticias-defeso-eleitoral/'],'deny':['ultimas-noticias']},
  {'fonte':'Embrapa','url':'https://www.embrapa.br/noticias','allow':['/-/noticia/','/busca-de-noticias/-/noticia/'],'deny':[]},
  {'fonte':'SEMAD Goiás','url':'https://goias.gov.br/meioambiente/','allow':['goias.gov.br/meioambiente/'],'deny':['/categoria/','/wp-content/','/tag/','/author/']},
]
HEAD={'User-Agent':'Mozilla/5.0 (compatible; OrdoneAgroambiental/2.0; +https://ordoneagroambiental.github.io/midia/)'}

def clean(text): return re.sub(r'\s+',' ',text or '').strip()
def allowed(href,s):
    absolute=urljoin(s['url'],href)
    if not absolute.startswith('http'): return False
    low=absolute.lower()
    if not any(x.lower() in low for x in s['allow']): return False
    if any(x.lower() in low for x in s['deny']): return False
    return True

def collect(s,limit=4):
    r=requests.get(s['url'],headers=HEAD,timeout=25)
    r.raise_for_status(); soup=BeautifulSoup(r.text,'html.parser')
    out=[]; seen=set()
    for a in soup.find_all('a',href=True):
        title=clean(a.get_text(' ',strip=True)); href=a['href']
        if len(title)<25 or len(title)>220 or not allowed(href,s): continue
        url=urljoin(s['url'],href).split('#')[0]
        key=(title.lower(),url)
        if key in seen: continue
        seen.add(key)
        out.append({'fonte':s['fonte'],'data':'','titulo':title,'url':url})
        if len(out)>=limit: break
    return out

def main():
    old={'items':[]}
    if OUT.exists():
        try: old=json.loads(OUT.read_text(encoding='utf-8'))
        except Exception: pass
    items=[]
    for source in SOURCES:
        try: items.extend(collect(source))
        except Exception as exc: print('Falha em',source['fonte'],exc)
    if not items:
        print('Nenhuma coleta nova; preservando arquivo anterior.'); return
    now=datetime.now(timezone.utc).astimezone().strftime('%d/%m/%Y %H:%M')
    data={'atualizado_em':now,'items':items[:9]}
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Atualizado:',len(data['items']),'itens')
if __name__=='__main__': main()
