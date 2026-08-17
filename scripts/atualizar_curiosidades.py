#!/usr/bin/env python3
"""Atualiza e valida o quadro Você Sabia? com fontes oficiais."""
import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"dados"/"curiosidades_produtor.json"
UA={"User-Agent":"OrdoneCuriosidades/1.0 (+https://ordoneagroambiental.github.io/midia/)"}

def main():
    payload=json.loads(OUT.read_text(encoding="utf-8"))
    now=datetime.now(timezone.utc)
    for item in payload.get("itens",[]):
        try:
            r=requests.get(item["url"],headers=UA,timeout=25,allow_redirects=True)
            item["fonte_disponivel"]=r.status_code<400
            item["http_status"]=r.status_code
        except Exception:
            item["fonte_disponivel"]=False
        item["verificado_em"]=now.date().isoformat()
        if item.get("status")=="ABERTO" and not item.get("prazo"):
            item["status"]="EM VERIFICAÇÃO"
    payload["atualizado_em"]=now.isoformat()
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Curiosidades verificadas:",len(payload.get("itens",[])))

if __name__=="__main__":
    main()
