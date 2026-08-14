#!/usr/bin/env python3
"""Radar Ordone V3.7.1.

Objetivo: localizar sinais e oportunidades em fontes públicas, com prioridade para
Goianésia e região, sem realizar contato automático. O contato comercial permanece
condicionado à validação e aprovação humana.

Principais melhorias da V3.7.1:
- informa dataInicial E dataFinal nas consultas do PNCP;
- consulta propostas abertas e contratações recém-publicadas;
- reduz chamadas redundantes para evitar execuções muito longas;
- amplia o reconhecimento de linguagem ambiental, agronômica e de irrigação;
- registra diagnóstico da coleta para facilitar auditoria quando houver 0 resultados.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
import argparse
import hashlib
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dados" / "radar_config.json"
OUT = ROOT / "dados" / "radar_oportunidades.json"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; OrdoneRadar/3.7.1; +https://ordoneagroambiental.github.io/midia/)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

# As modalidades são consultadas em blocos curtos para evitar centenas de requisições.
# O PNCP exige codigoModalidadeContratacao nesses endpoints de consulta.
MODALIDADES = tuple(range(1, 16))

# Termos adicionais usados apenas para reconhecimento. Eles não substituem a lista
# configurável em dados/radar_config.json.
EXTRA_PATTERNS = {
    "ambiental": [
        r"\bambient\w*", r"\bflorest\w*", r"\breveget\w*", r"\breflorest\w*",
        r"\brestaura\w*", r"\brecupera\w*\s+(?:de\s+)?(?:area|areas|app|nascente)",
        r"\bprad\b", r"\bprada\b", r"\bcompensa\w*\s+ambient\w*",
        r"\blicenciamento\s+ambient\w*", r"\bcondicionante\w*\s+ambient\w*",
        r"\bsupress\w*\s+veget\w*", r"\binventario\s+florest\w*",
        r"\bhidrossemeadur\w*", r"\bmudas?\s+nativ\w*", r"\bviveir\w*",
        r"\barboriza\w*", r"\barea\w*\s+verde\w*",
    ],
    "solo_agua": [
        r"\beros\w*", r"\bassore\w*", r"\bsediment\w*", r"\bdrenag\w*",
        r"\bconserva\w*\s+(?:do\s+)?solo", r"\bfertilidade\s+(?:do\s+)?solo",
        r"\banalise\s+(?:de\s+)?solo", r"\bnascente\w*", r"\brecursos?\s+hidric\w*",
        r"\boutorga\w*", r"\bapp\b", r"\barea\s+de\s+preservacao\s+permanente",
    ],
    "irrigacao": [
        r"\birriga\w*", r"\bgotej\w*", r"\bmicroaspers\w*", r"\baspers\w*",
        r"\bfertirriga\w*", r"\bbombeamento\w*", r"\bbomba\w*\s+(?:de\s+)?agua",
        r"\breservatorio\w*", r"\bautomacao\w*\s+(?:de\s+)?irriga\w*",
        r"\bsistema\w*\s+(?:de\s+)?irriga\w*",
    ],
    "geotecnologia": [
        r"\bgeoprocess\w*", r"\bgeorreferenc\w*", r"\btopograf\w*",
        r"\baerolevant\w*", r"\bdrone\w*", r"\bmapeamento\w*",
        r"\bsensoriamento\s+remoto",
    ],
    "bioengenharia": [
        r"\bbioengenharia\w*", r"\bpalicad\w*", r"\bcontrole\s+de\s+sediment\w*",
        r"\bconten\w*\s+(?:de\s+)?eros\w*",
    ],
}


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm(text):
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", s).strip()


def clean(text, n=600):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


def safe_url(u):
    try:
        x = urlparse(str(u or ""))
        return str(u) if x.scheme in ("http", "https") and x.netloc else ""
    except Exception:
        return ""


def money(v):
    try:
        return round(float(v), 2)
    except Exception:
        return None


def geography_score(city, uf, cfg):
    c = norm(city)
    uf = (uf or "").upper()
    geo = cfg["prioridade_geografica"]
    if c == norm("Goianésia"):
        return 25, "Goianésia"
    if c in {norm(x) for x in geo.get("entorno_imediato", [])}:
        return 20, "Entorno imediato"
    if c in {norm(x) for x in geo.get("regiao_ampliada", [])}:
        return 15, "Região ampliada"
    if uf == "GO":
        return 10, "Goiás"
    return 5, "Brasil"


def keyword_hits(text, cfg):
    t = norm(text)
    if any(norm(x) in t for x in cfg.get("termos_excluir", [])):
        return []

    hits = []
    for kw in cfg.get("palavras_chave", []):
        if norm(kw) in t:
            hits.append(kw)

    for group, patterns in EXTRA_PATTERNS.items():
        if any(re.search(p, t, flags=re.I) for p in patterns):
            hits.append(f"grupo:{group}")

    # Combinações comerciais relevantes que aparecem frequentemente em objetos públicos.
    combos = [
        ("serviços ambientais", ("servic", "ambient")),
        ("engenharia ambiental", ("engenharia", "ambient")),
        ("recuperação de áreas", ("recuper", "area")),
        ("manutenção de áreas verdes", ("manutenc", "area", "verde")),
        ("projeto de irrigação", ("projet", "irriga")),
    ]
    for label, parts in combos:
        if all(p in t for p in parts):
            hits.append(label)

    seen, out = set(), []
    for h in hits:
        k = norm(h)
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def services_from(text):
    t = norm(text)
    out = []

    def add(label, *terms):
        if any(norm(x) in t for x in terms) and label not in out:
            out.append(label)

    add("Recuperação ambiental / PRAD", "recuperacao ambiental", "area degradada", "prad", "prada", "restauracao", "revegetacao", "reflorestamento", "hidrossemeadura")
    add("Irrigação e automação", "irrigacao", "gotejamento", "aspersao", "microaspersao", "fertirrigacao", "automacao", "bombeamento", "reservatorio")
    add("Solo e conservação", "erosao", "assoreamento", "conservacao do solo", "analise de solo", "fertilidade do solo", "drenagem")
    add("Bioengenharia e controle de sedimentos", "palicada", "bioengenharia", "sedimento", "assoreamento")
    add("Geotecnologia / drone", "geoprocessamento", "georreferenciamento", "topografia", "drone", "aerolevantamento", "mapeamento", "sensoriamento remoto")
    add("Licenciamento e regularização", "licenciamento ambiental", "regularizacao ambiental", "condicionante ambiental", "outorga", "supressao vegetal")
    add("Plantio, viveiros e compensação", "plantio compensatorio", "mudas nativas", "viveiro", "compensacao ambiental", "inventario florestal", "arborizacao", "area verde")
    add("Recursos hídricos e nascentes", "nascente", "recursos hidricos", "app", "area de preservacao permanente")
    add("Monitoramento ambiental", "monitoramento ambiental")
    return out or ["Avaliação técnica inicial"]


def priority(score):
    if score >= 80:
        return "ALTA"
    if score >= 60:
        return "MÉDIA"
    if score >= 40:
        return "ACOMPANHAR"
    return "INTELIGÊNCIA"


def score_item(city, uf, text, kind, cfg, deadline=""):
    score, region = geography_score(city, uf, cfg)
    hits = keyword_hits(text, cfg)
    # Grupos e expressões ampliadas não devem inflar excessivamente o score.
    explicit = [h for h in hits if not h.startswith("grupo:")]
    groups = [h for h in hits if h.startswith("grupo:")]
    score += min(48, 10 * len(explicit) + 6 * len(groups))
    if kind == "DEMANDA FORMAL":
        score += 15
    if deadline:
        try:
            d = datetime.fromisoformat(str(deadline).replace("Z", "+00:00")).date()
            days = (d - datetime.now().date()).days
            if 0 <= days <= 15:
                score += 10
            elif 16 <= days <= 45:
                score += 5
        except Exception:
            pass
    return min(100, score), region, hits


def pncp_url_from_control(control):
    """Monta URL pública do PNCP quando o número de controle segue o padrão oficial."""
    m = re.match(r"^([A-Za-z0-9]{14})-\d+-0*(\d+)/(\d{4})$", str(control or ""))
    if not m:
        return ""
    cnpj, seq, year = m.groups()
    return f"https://pncp.gov.br/app/editais/{cnpj}/{year}/{int(seq)}"


def pncp_request(endpoint, params, diagnostics):
    try:
        r = requests.get(endpoint, params=params, headers=UA, timeout=18)
        diagnostics["requisicoes"] += 1
        if r.status_code in (204, 404, 422):
            return {"data": [], "totalPaginas": 0}
        if r.status_code == 429:
            diagnostics["avisos"].append("PNCP respondeu 429 (limite temporário).")
            time.sleep(2)
            return {"data": [], "totalPaginas": 0}
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        diagnostics["erros"].append(f"PNCP: {type(exc).__name__}: {exc}"[:250])
        return {"data": [], "totalPaginas": 0}


def pncp_collect(cfg, mode, diagnostics):
    """Coleta PNCP em camadas locais, estaduais e nacionais.

    mode='proposta': oportunidades ainda recebendo propostas.
    mode='publicacao': contratações recém-publicadas, úteis para inteligência antecipada.
    """
    assert mode in ("proposta", "publicacao")
    base = f"https://pncp.gov.br/api/consulta/v1/contratacoes/{mode}"
    today = datetime.now().date()
    if mode == "proposta":
        date_ini = today.strftime("%Y%m%d")
        date_end = (today + timedelta(days=120)).strftime("%Y%m%d")
    else:
        date_ini = (today - timedelta(days=60)).strftime("%Y%m%d")
        date_end = today.strftime("%Y%m%d")

    scopes = [
        ("Goianésia", {"uf": "GO", "codigoMunicipioIbge": 5208608}, 2),
        ("Goiás", {"uf": "GO"}, 2),
        ("Brasil", {}, 1),
    ]
    out, seen = [], set()

    for scope_name, scope_params, max_pages in scopes:
        for modalidade in MODALIDADES:
            for page in range(1, max_pages + 1):
                params = {
                    "dataInicial": date_ini,
                    "dataFinal": date_end,
                    "codigoModalidadeContratacao": modalidade,
                    "pagina": page,
                    "tamanhoPagina": 100,
                    **scope_params,
                }
                data = pncp_request(base, params, diagnostics)
                rows = data.get("data") or []
                if not rows:
                    break

                for x in rows:
                    key = str(x.get("numeroControlePNCP") or "")
                    if key and key in seen:
                        continue
                    unit = x.get("unidadeOrgao") or {}
                    city = unit.get("municipioNome") or unit.get("nomeMunicipio") or ""
                    uf = unit.get("ufSigla") or unit.get("siglaUf") or scope_params.get("uf", "")
                    if not city and scope_name == "Goianésia":
                        city = "Goianésia"

                    text = " ".join([
                        str(x.get("objetoCompra") or ""),
                        str(x.get("informacaoComplementar") or ""),
                        str((x.get("orgaoEntidade") or {}).get("razaoSocial") or ""),
                        str(unit.get("nomeUnidade") or ""),
                        str(x.get("modalidadeNome") or ""),
                    ])
                    hits = keyword_hits(text, cfg)
                    if not hits:
                        continue

                    deadline = str(x.get("dataEncerramentoProposta") or "")
                    kind = "DEMANDA FORMAL" if mode == "proposta" else "SINAL DE CONTRATAÇÃO"
                    score, region, hits = score_item(city, uf, text, "DEMANDA FORMAL" if mode == "proposta" else "SINAL AMBIENTAL", cfg, deadline)
                    # Publicação sem proposta aberta precisa de aderência um pouco maior.
                    if mode == "publicacao" and score < 40:
                        continue

                    source = pncp_url_from_control(key) or safe_url(x.get("linkSistemaOrigem")) or "https://pncp.gov.br/app/editais"
                    out.append({
                        "id": key or f"pncp-{mode}-{scope_name}-{modalidade}-{len(out)+1}",
                        "tipo": kind,
                        "confirmacao": "CONFIRMADO",
                        "fonte": "PNCP",
                        "titulo": clean(x.get("objetoCompra"), 320),
                        "municipio": clean(city, 80),
                        "uf": clean(uf, 2),
                        "regiao_prioridade": region,
                        "organizacao": clean((x.get("orgaoEntidade") or {}).get("razaoSocial"), 180),
                        "data_publicacao": clean(x.get("dataPublicacaoPncp"), 40),
                        "prazo": clean(deadline, 40),
                        "valor_estimado": money(x.get("valorTotalEstimado")),
                        "modalidade": clean(x.get("modalidadeNome"), 80),
                        "servicos_ordone": services_from(text),
                        "palavras_encontradas": hits[:10],
                        "score": score,
                        "prioridade": priority(score),
                        "url": source,
                        "numero_controle_pncp": key,
                        "escopo_coleta": scope_name,
                        "fase_pncp": mode,
                        "proxima_acao": (
                            "Abrir o edital/aviso oficial, validar escopo, habilitação, prazo, local de execução e viabilidade de proposta."
                            if mode == "proposta" else
                            "Abrir a publicação oficial e verificar se há prazo de proposta, futura licitação, contratação direta ou oportunidade para relacionamento institucional."
                        ),
                    })
                    if key:
                        seen.add(key)

                total = int(data.get("totalPaginas") or 1)
                if page >= total:
                    break
            time.sleep(0.05)

    diagnostics[f"pncp_{mode}"] = len(out)
    return out


def html_signals(cfg, diagnostics):
    sources = [
        ("Prefeitura de Goianésia", "https://goianesia.go.gov.br/", "Goianésia", "GO"),
        ("Editais de Goianésia", "https://goianesia.go.gov.br/editais-e-publicacoes/", "Goianésia", "GO"),
        ("SEMAD Goiás", "https://goias.gov.br/meioambiente/", "", "GO"),
    ]
    out, seen = [], set()
    local_names = (
        cfg["prioridade_geografica"].get("prioridade_1", [])
        + cfg["prioridade_geografica"].get("entorno_imediato", [])
        + cfg["prioridade_geografica"].get("regiao_ampliada", [])
    )

    for fonte, url, default_city, default_uf in sources:
        try:
            r = requests.get(url, headers=UA, timeout=18)
            diagnostics["requisicoes"] += 1
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as exc:
            diagnostics["erros"].append(f"{fonte}: {type(exc).__name__}: {exc}"[:250])
            continue

        for a in soup.find_all("a", href=True):
            title = clean(a.get_text(" ", strip=True), 260)
            # Captura também um pouco do contexto do bloco, pois muitos portais usam títulos curtos.
            parent_text = clean(a.parent.get_text(" ", strip=True) if a.parent else "", 500)
            combined = f"{title} {parent_text}".strip()
            if len(combined) < 20:
                continue
            href = safe_url(urljoin(url, a["href"]))
            if not href or urlparse(href).netloc != urlparse(url).netloc:
                continue
            hits = keyword_hits(combined, cfg)
            if not hits:
                continue
            k = (norm(title or parent_text), href)
            if k in seen:
                continue
            seen.add(k)

            city = default_city
            for name in local_names:
                if norm(name) in norm(combined):
                    city = name
                    break
            nt = norm(combined)
            formal = any(x in nt for x in ("licit", "edital", "contrat", "dispensa", "pregao", "concorrencia"))
            kind = "DEMANDA FORMAL" if formal else "SINAL AMBIENTAL"
            score, region, hits = score_item(city, default_uf, combined, kind, cfg, "")
            if score < 40:
                continue
            out.append({
                "id": "web-" + hashlib.sha1(("||".join(k)).encode("utf-8")).hexdigest()[:12],
                "tipo": kind,
                "confirmacao": "CONFIRMADO",
                "fonte": fonte,
                "titulo": title or parent_text[:260],
                "municipio": city,
                "uf": default_uf,
                "regiao_prioridade": region,
                "organizacao": fonte,
                "data_publicacao": "",
                "prazo": "",
                "valor_estimado": None,
                "modalidade": "",
                "servicos_ordone": services_from(combined),
                "palavras_encontradas": hits[:10],
                "score": score,
                "prioridade": priority(score),
                "url": href,
                "proxima_acao": "Abrir a publicação oficial e confirmar se existe demanda técnica, contratação ou apenas informação institucional.",
            })
            if len(out) >= 30:
                break

    diagnostics["html_sinais"] = len(out)
    return out


def dedupe_sort(items):
    seen, out = set(), []
    for x in sorted(items, key=lambda z: (-int(z.get("score", 0)), z.get("municipio", ""), z.get("titulo", ""))):
        key = (norm(x.get("titulo")), norm(x.get("organizacao")), norm(x.get("municipio")))
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out[:60]


def build_output(cfg, items, diagnostics):
    local = set(norm(x) for x in (
        cfg["prioridade_geografica"].get("prioridade_1", [])
        + cfg["prioridade_geografica"].get("entorno_imediato", [])
        + cfg["prioridade_geografica"].get("regiao_ampliada", [])
    ))
    return {
        "versao": "3.7.1",
        "atualizado_em": datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M"),
        "status": "coleta_concluida",
        "prioridade": "Goianésia e entorno → Goiás → Brasil",
        "resumo": {
            "total": len(items),
            "goianesia_regiao": sum(norm(x.get("municipio")) in local for x in items),
            "goias": sum((x.get("uf") or "").upper() == "GO" for x in items),
            "demandas_formais": sum(x.get("tipo") == "DEMANDA FORMAL" for x in items),
            "sinais_ambientais": sum(x.get("tipo") in ("SINAL AMBIENTAL", "SINAL DE CONTRATAÇÃO") for x in items),
        },
        "diagnostico_coleta": diagnostics,
        "items": items,
        "fontes_monitoradas": [
            {"nome": x["nome"], "url": x["url"], "automatica": x["automatica"]}
            for x in cfg.get("fontes_publicas", [])
        ],
        "aviso": "Sinal público não é cliente confirmado. O radar organiza oportunidades a partir de fontes públicas; qualquer contato comercial depende de validação e aprovação humana.",
    }


def self_test(cfg):
    s, r, h = score_item(
        "Goianésia", "GO",
        "contratação de serviços de recuperação ambiental com irrigação, drone e geoprocessamento",
        "DEMANDA FORMAL", cfg, ""
    )
    assert s >= 60 and r == "Goianésia" and h
    s2, r2, h2 = score_item("Goiânia", "GO", "notícia institucional sem serviço relacionado", "SINAL AMBIENTAL", cfg, "")
    assert s2 < 40 and not h2
    assert safe_url("javascript:alert(1)") == ""
    assert "pncp.gov.br/app/editais/" in pncp_url_from_control("07954605000160-1-000176/2026")
    print("SELF-TEST OK", s, r, len(h))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    cfg = load_json(CONFIG, {})
    if args.self_test:
        self_test(cfg)
        return

    diagnostics = {
        "requisicoes": 0,
        "pncp_proposta": 0,
        "pncp_publicacao": 0,
        "html_sinais": 0,
        "erros": [],
        "avisos": [],
    }
    items = []
    successes = 0

    try:
        p = pncp_collect(cfg, "proposta", diagnostics)
        items += p
        successes += 1
        print("PNCP propostas:", len(p))
    except Exception as exc:
        diagnostics["erros"].append(f"Falha geral PNCP proposta: {exc}"[:250])

    try:
        p2 = pncp_collect(cfg, "publicacao", diagnostics)
        items += p2
        successes += 1
        print("PNCP publicações:", len(p2))
    except Exception as exc:
        diagnostics["erros"].append(f"Falha geral PNCP publicação: {exc}"[:250])

    try:
        h = html_signals(cfg, diagnostics)
        items += h
        successes += 1
        print("Sinais HTML:", len(h))
    except Exception as exc:
        diagnostics["erros"].append(f"Falha geral HTML: {exc}"[:250])

    items = dedupe_sort(items)
    if successes == 0:
        print("Todas as fontes falharam; preservando resultado anterior.")
        return

    data = build_output(cfg, items, diagnostics)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Radar V3.7.1 atualizado:", len(items), "itens; requisições:", diagnostics["requisicoes"])


if __name__ == "__main__":
    main()
