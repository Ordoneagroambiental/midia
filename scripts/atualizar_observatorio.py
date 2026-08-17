#!/usr/bin/env python3
"""Observatório Ordone: curadoria pública e rastreável de restauração ambiental."""
from __future__ import annotations
import hashlib, json, re, sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dados" / "observatorio_ambiental.json"
UA = {"User-Agent": "OrdoneObservatorio/1.0 (+https://ordoneagroambiental.github.io/midia/)"}
KEYWORDS = {
 "Mineração": ["mine", "mining", "minera", "tailings", "reclamation", "superfund", "barragem"],
 "Desertos e solos": ["desert", "desertification", "soil", "land degradation", "semiarid", "seca"],
 "Florestas e biodiversidade": ["forest", "florest", "biodiversity", "restoration", "restaura", "reveget"],
 "Rios e águas": ["river", "water", "watershed", "wetland", "rio ", "bacia", "hidric", "sediment"],
 "Costa e oceanos": ["mangrove", "coastal", "ocean", "coral", "manguez", "marinho"],
 "Tecnologia e monitoramento": ["remote sensing", "satellite", "monitoring", "technology", "innovation", "sensoriamento", "monitoramento"]
}
SOURCES = [
 ("UNEP", "Global", "https://www.unep.org/news-and-stories", "Instituição multilateral"),
 ("EPA Estados Unidos", "Estados Unidos", "https://www.epa.gov/newsreleases/search", "Órgão público"),
 ("USGS", "Estados Unidos", "https://www.usgs.gov/news", "Instituto científico público"),
 ("Chinese Academy of Sciences", "China", "https://english.cas.cn/newsroom/research_news/", "Academia pública de ciências"),
 ("CAS Eco-Environment", "China", "https://english.egi.cas.cn/ns/", "Instituto científico público"),
 ("MMA", "Brasil", "https://www.gov.br/mma/pt-br/assuntos/noticias", "Órgão público"),
 ("Embrapa", "Brasil", "https://www.embrapa.br/noticias", "Empresa pública de pesquisa"),
 ("SGB", "Brasil", "https://www.sgb.gov.br/sala-de-imprensa/noticias", "Serviço geológico público"),
]
SEEDS = [
 {"titulo":"Monitoramento do programa chinês de restauração de desertos Three-North", "resumo":"Pesquisadores chineses avaliaram o progresso de áreas-chave do programa de cinturões florestais e controle de desertificação.", "aplicacao":"Referência para combinar revegetação, controle e monitoramento de longo prazo em paisagens secas.", "pais":"China", "categoria":"Desertos e solos", "fonte":"Chinese Academy of Sciences", "tipo_fonte":"Instituto científico público", "data":"2026-06-17", "url":"https://english.iae.cas.cn/newsevents/news/202606/t20260617_1169163.html", "tipo":"Atualidade"},
 {"titulo":"Restauração de manguezais com ciência e participação comunitária", "resumo":"A UNEP reúne resultados recentes de restauração costeira, incluindo monitoramento de sobrevivência de mudas e gestão comunitária.", "aplicacao":"Modelo para projetos costeiros com indicadores verificáveis, capacitação local e manutenção posterior.", "pais":"Global", "categoria":"Costa e oceanos", "fonte":"UNEP", "tipo_fonte":"Instituição multilateral", "data":"2026-07-24", "url":"https://www.unep.org/news-and-stories/story/mangroves-are-making-comeback-heres-whats-working", "tipo":"Atualidade"},
 {"titulo":"Tecnologias para recuperação de áreas de mineração abandonadas", "resumo":"A EPA mantém referências técnicas sobre caracterização, contaminação, remediação, modelagem de impactos e recuperação de áreas mineradas.", "aplicacao":"Biblioteca-base para diagnóstico, PRAD, solo e água em passivos de mineração.", "pais":"Estados Unidos", "categoria":"Mineração", "fonte":"EPA Estados Unidos", "tipo_fonte":"Órgão público", "data":"2026-08-01", "url":"https://www.epa.gov/superfund/abandoned-mine-lands-technical-resources", "tipo":"Referência técnica"},
 {"titulo":"Sistema Florescer apoia restauração ecológica em Minas Gerais", "resumo":"Ferramenta pública foi lançada para apoiar políticas de restauração, regularização e recuperação de áreas degradadas.", "aplicacao":"Acompanhar oportunidades de planejamento territorial, restauração e produção de evidências técnicas no Brasil.", "pais":"Brasil", "categoria":"Tecnologia e monitoramento", "fonte":"Sisema Minas Gerais", "tipo_fonte":"Órgão público", "data":"2026-05-29", "url":"https://meioambiente.mg.gov.br/w/sisema-abre-semana-do-meio-ambiente-com-lancamento-do-sistema-florescer", "tipo":"Atualidade"},
 {"titulo":"Recuperação ambiental nas bacias do Rio Doce e Paraopeba", "resumo":"Programas públicos vinculam reparação, biodiversidade, segurança hídrica e saneamento em territórios impactados.", "aplicacao":"Referência brasileira para integrar restauração ecológica, recursos hídricos, obras e acompanhamento territorial.", "pais":"Brasil", "categoria":"Rios e águas", "fonte":"IGAM Minas Gerais", "tipo_fonte":"Órgão público", "data":"2026-06-25", "url":"https://igam.mg.gov.br/w/reparacao-transforma-territorios-e-impulsiona-recuperacao-de-ecossistemas-em-minas-gerais", "tipo":"Atualidade"}
]

def clean(s): return re.sub(r"\s+", " ", unescape(s or "")).strip()
def classify(text):
 t=text.casefold(); scores={k:sum(1 for w in ws if w in t) for k,ws in KEYWORDS.items()}
 cat,n=max(scores.items(), key=lambda x:x[1]); return (cat,n)
def relevance(text):
 t=text.casefold(); core=sum(t.count(w) for w in ["restoration","restore","reclamation","remediation","restaura","recupera","reabilita"])
 return core*12 + classify(text)[1]*4
def collect_source(name,country,index_url,source_type):
 r=requests.get(index_url,headers=UA,timeout=25); r.raise_for_status()
 soup=BeautifulSoup(r.text,"html.parser"); found=[]; host=urlparse(index_url).netloc
 for a in soup.select("a[href]"):
  title=clean(a.get_text(" ")); href=urljoin(index_url,a.get("href"))
  if len(title)<24 or urlparse(href).netloc!=host: continue
  score=relevance(title)
  if score<12: continue
  cat,_=classify(title); key=hashlib.sha1(href.encode()).hexdigest()[:12]
  found.append({"id":key,"titulo":title[:180],"resumo":"Conteúdo técnico identificado pela curadoria automática. Abra a fonte oficial para verificar método, escala e resultados.","aplicacao":"Avaliar a transferência da técnica para condições brasileiras antes de qualquer recomendação.","pais":country,"categoria":cat,"fonte":name,"tipo_fonte":source_type,"data":"","url":href,"tipo":"Atualidade","pontuacao":min(100,40+score)})
 dedup={x["url"]:x for x in found}; return sorted(dedup.values(),key=lambda x:x["pontuacao"],reverse=True)[:5]
def main():
 items=[]; status=[]
 for src in SOURCES:
  try:
   got=collect_source(*src); items.extend(got); status.append({"fonte":src[0],"ok":True,"itens":len(got)})
  except Exception as e: status.append({"fonte":src[0],"ok":False,"erro":str(e)[:120]})
 for x in SEEDS:
  y=dict(x); y["id"]=hashlib.sha1(y["url"].encode()).hexdigest()[:12]; y["pontuacao"]=85; items.append(y)
 unique={x["url"]:x for x in items}; items=sorted(unique.values(),key=lambda x:(x.get("data",""),x.get("pontuacao",0)),reverse=True)[:30]
 if not items and OUT.exists(): return
 payload={"versao":"1.0","atualizado_em":datetime.now(timezone.utc).isoformat(),"criterios":{"escopo":"Brasil e mundo","frequencia":"a cada 6 horas","regra":"Somente fontes institucionais, científicas ou oficiais; validação humana antes de uso técnico."},"status_fontes":status,"itens":items}
 OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(f"Observatório atualizado: {len(items)} itens")
if __name__=="__main__":
 if "--self-test" in sys.argv:
  assert classify("mine reclamation and water monitoring")[0] in KEYWORDS; print("Teste interno OK")
 else: main()
