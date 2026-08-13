#!/usr/bin/env python3
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urlparse, unquote
import sys
ROOT=Path(__file__).resolve().parents[1]
errors=[]; htmls=list(ROOT.rglob('*.html'))
for f in htmls:
  soup=BeautifulSoup(f.read_text(encoding='utf-8',errors='ignore'),'html.parser')
  for tag,attr in [('a','href'),('img','src'),('script','src'),('link','href')]:
    for el in soup.find_all(tag):
      v=el.get(attr)
      if not v or v.startswith(('#','mailto:','tel:','javascript:','data:')): continue
      p=urlparse(v)
      if p.scheme in ('http','https'): continue
      target=(f.parent/unquote(p.path)).resolve()
      if not target.exists(): errors.append(f'{f.relative_to(ROOT)} -> {v}')
print('HTML:',len(htmls),'| erros locais:',len(errors))
for e in errors[:100]: print('ERRO',e)
if errors: sys.exit(1)
