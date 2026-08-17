#!/usr/bin/env python3
"""Radar Ordone V4.9 — consulta PNCP nacional com validação técnica do objeto.

Objetivo: localizar sinais e oportunidades em fontes públicas em todo o Brasil,
mantendo Goiás e Goianésia como bônus de proximidade, sem realizar contato automático. O contato comercial permanece
condicionado à validação e aprovação humana.

Principais melhorias acumuladas até a V3.7.3:
- corrige os parâmetros oficiais do endpoint PNCP de propostas abertas;
- restringe modalidades e páginas para reduzir respostas 429;
- valida melhor páginas institucionais e elimina falsos positivos genéricos;
- aprofunda links locais antes de classificá-los como oportunidade;
- preserva prioridade Goianésia → entorno → Goiás → Brasil;
- mantém contato comercial condicionado à validação humana.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
import argparse
import hashlib
import io
import json
import re
import time
import unicodedata

import requests
from bs4 import BeautifulSoup
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dados" / "radar_config.json"
PROFILE = ROOT / "dados" / "perfil_ordone.json"
OUT = ROOT / "dados" / "radar_oportunidades.json"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; OrdoneRadar/4.7; +https://ordoneagroambiental.github.io/midia/)",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}

# As modalidades são consultadas em blocos curtos para evitar centenas de requisições.
# O PNCP exige codigoModalidadeContratacao nesses endpoints de consulta.
# Modalidades relevantes para serviços, obras, projetos e contratação direta.
# Tabela de domínio PNCP: códigos válidos 1..13. Leilões (1 e 13) são omitidos.
MODALIDADES = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
MODALIDADES_NACIONAIS = (6, 8)

# Termos adicionais usados apenas para reconhecimento. Eles não substituem a lista
# configurável em dados/radar_config.json.
GENERIC_ANCHORS = {
    "ver todos os servicos", "todos os servicos", "servicos", "saiba mais",
    "leia mais", "ver mais", "acesse", "acessar", "clique aqui", "inicio",
    "home", "sobre", "sobre a cidade", "noticias", "mais noticias",
    "transparencia", "portal da transparencia", "menu", "contato",
}
GENERIC_PATH_PARTS = (
    "/servicos", "/sobre", "/contato", "/institucional", "/secretarias",
    "/transparencia", "/portal-da-transparencia",
)
NON_ENVIRONMENTAL_TERMS = (
    "fibromialgia", "carteira de fibromialgia", "saude", "vacina", "hospital",
    "medicamento", "paciente", "assistencia social", "educacao", "matricula",
    "merenda", "transporte escolar", "cultura", "esporte", "turismo",
    "certidao", "tributo", "iptu", "alvara", "nota fiscal", "contracheque",
)
UNRELATED_SECTOR_TERMS = (
    "computador", "notebook", "tablet", "monitor", "licenca de software",
    "software", "saas", "whatsapp", "inteligencia artificial", "telefonia",
    "internet", "suporte tecnico", "processamento de linguagem natural",
)
INSTITUTIONAL_PAGE_TERMS = (
    "perguntas frequentes", "escola de meio ambiente", "quem e quem",
    "estrutura organizacional", "competencias", "legislacao", "contato",
    "acesso a informacao", "servicos ao cidadao", "programas e projetos",
    "pagamento por servicos ambientais (psa)", "consultas", "glossario",
)
FORMAL_TERMS = (
    "licit", "edital", "contrat", "dispensa", "pregao", "concorrencia",
    "chamamento", "termo de referencia", "aviso de contratacao",
)
HIGH_SIGNAL_TERMS = (
    "prad", "prada", "recuperacao ambiental", "area degradada", "revegetacao",
    "restauracao florestal", "reflorestamento", "irrigacao", "gotejamento",
    "microaspersao", "fertirrigacao", "erosao", "assoreamento", "bioengenharia",
    "geoprocessamento", "georreferenciamento", "drone", "aerolevantamento",
    "licenciamento ambiental", "condicionante ambiental", "plantio compensatorio",
    "mudas nativas", "viveiro", "nascente", "outorga",
    "gestao ambiental de obras", "supervisao ambiental", "acompanhamento ambiental de obra",
    "programa ambiental da construcao", "controle ambiental de obra",
)

CONSTRUCTION_MARKET_TERMS = (
    "construtora", "construcao civil", "obra", "canteiro", "terraplenagem",
    "loteamento", "incorporadora", "rodovia", "ferrovia", "linha de transmissao",
    "usina solar", "saneamento", "adutora", "barragem", "mineracao", "infraestrutura",
    "concessionaria", "pavimentacao", "duplicacao", "implantacao",
)

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


def is_generic_title(text):
    t = norm(text)
    return (not t) or t in GENERIC_ANCHORS or len(t) < 8


def generic_url(url):
    try:
        path = norm(urlparse(url).path.replace("-", " ").replace("_", " "))
        return any(norm(x.strip("/")) in path for x in GENERIC_PATH_PARTS)
    except Exception:
        return False


def clearly_non_environmental(text):
    t = norm(text)
    return any(term in t for term in NON_ENVIRONMENTAL_TERMS)


def relevant_procurement_object(text, cfg):
    """Aceita somente objeto com um serviço técnico oferecido pela Ordone.

    Menções laterais a secretarias, APP de informática, monitores ou palavras
    ambientais soltas não transformam uma compra comum em oportunidade ambiental.
    """
    t = norm(text)
    valid_services = [x for x in services_from(text) if x != "Avaliação técnica inicial"]
    strong = [x for x in HIGH_SIGNAL_TERMS if x in t]
    if any(x in t for x in UNRELATED_SECTOR_TERMS) and not strong:
        return False
    return bool(valid_services and (strong or environmental_evidence(text, cfg)[0]))


def institutional_page(text):
    """Rejeita páginas permanentes/informativas que não representam demanda."""
    t = norm(text)
    return any(term in t for term in INSTITUTIONAL_PAGE_TERMS)


def html_formal_evidence(text, url):
    """Exige sinais de procedimento real; palavras soltas como 'contratação' não bastam."""
    t = norm(text)
    route = norm(urlparse(url).path)
    procedure = any(x in t for x in ("edital", "pregao", "concorrencia", "dispensa", "chamamento", "aviso de contratacao"))
    concrete = any(x in t for x in ("processo", "objeto", "prazo", "abertura", "sessao", "proposta", "nº", "numero"))
    routed = any(x in route for x in ("edital", "licit", "contratacao", "pregao", "concorrencia"))
    return procedure and concrete and routed


def stale_archive_title(text):
    """Rejeita páginas históricas agregadoras, como 'Editais até 2024'."""
    t = norm(text)
    years = [int(y) for y in re.findall(r"\b20\d{2}\b", t)]
    return bool(years and any(x in t for x in ("ate ", "anteriores", "arquivo", "historico"))
                and max(years) < datetime.now().year)


def environmental_evidence(text, cfg):
    """Exige evidência ambiental explícita no objeto local da publicação."""
    hits, strong, explicit = meaningful_hits(text, cfg)
    services = [x for x in services_from(text) if x != "Avaliação técnica inicial"]
    return bool(services and (strong or explicit or hits)), hits


def market_relation(text):
    """Classifica como a Ordone pode entrar comercialmente na demanda."""
    t = norm(text)
    if any(x in t for x in CONSTRUCTION_MARKET_TERMS):
        return "Prestação ambiental para obra/construtora"
    return "Contratação ambiental direta"


def meaningful_hits(text, cfg):
    hits = keyword_hits(text, cfg)
    t = norm(text)
    strong = [x for x in HIGH_SIGNAL_TERMS if x in t]
    explicit = [h for h in hits if not str(h).startswith("grupo:")]
    return hits, strong, explicit


def formal_language(text):
    t = norm(text)
    return any(x in t for x in FORMAL_TERMS)


def fetch_page_context(url, diagnostics):
    try:
        r = requests.get(url, headers=UA, timeout=16)
        diagnostics["requisicoes"] += 1
        if r.status_code == 429:
            diagnostics["avisos"].append(f"Limite temporário ao aprofundar {urlparse(url).netloc}.")
            return "", ""
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = clean((soup.title.get_text(" ", strip=True) if soup.title else ""), 260)
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        body = clean(soup.get_text(" ", strip=True), 5000)
        return title, body
    except Exception as exc:
        diagnostics["avisos"].append(f"Aprofundamento: {type(exc).__name__}: {str(exc)[:120]}")
        return "", ""


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
        return 30, "Goianésia"
    if c in {norm(x) for x in geo.get("entorno_imediato", [])}:
        return 26, "Entorno imediato"
    if c in {norm(x) for x in geo.get("regiao_ampliada", [])}:
        return 22, "Região ampliada"
    if uf == "GO":
        return 18, "Goiás"
    # O Brasil inteiro integra o escopo comercial; distância apenas ordena.
    return 14, "Brasil"


def keyword_hits(text, cfg):
    t = norm(text)
    if any(norm(x) in t for x in cfg.get("termos_excluir", [])):
        return []

    hits = []
    for kw in cfg.get("palavras_chave", []):
        normalized_kw = norm(kw)
        # Evita que APP seja encontrado dentro de WhatsApp, por exemplo.
        matched = (bool(re.search(rf"(?<!\w){re.escape(normalized_kw)}(?!\w)", t))
                   if len(normalized_kw) <= 3 else normalized_kw in t)
        if matched:
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
    add("Gestão e supervisão ambiental de obras", "gestao ambiental de obra", "supervisao ambiental", "acompanhamento ambiental de obra", "controle ambiental de obra", "programa ambiental da construcao")
    add("PGRS e gestão de resíduos da obra", "pgrs", "residuo da construcao", "residuos da construcao", "gestao de residuos")
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


def pncp_control_parts(control):
    m = re.match(r"^([A-Za-z0-9]{14})-\d+-0*(\d+)/(\d{4})$", str(control or ""))
    return m.groups() if m else None


def extract_pdf_text(content, max_pages=35):
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(io.BytesIO(content))
        return clean(" ".join((p.extract_text() or "") for p in reader.pages[:max_pages]), 120000)
    except Exception:
        return ""


def pncp_document_text(control, diagnostics):
    parts = pncp_control_parts(control)
    if not parts:
        return "", [], "LEITURA INCOMPLETA"
    cnpj, seq, year = parts
    base = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{year}/{int(seq)}/arquivos"
    try:
        r = requests.get(base, headers=UA, timeout=20)
        diagnostics["requisicoes"] += 1
        if not r.ok:
            return "", [], "LEITURA INCOMPLETA"
        docs = r.json() if "json" in r.headers.get("content-type", "") else []
        if isinstance(docs, dict):
            docs = docs.get("data") or docs.get("items") or []
        texts, names = [], []
        for i, doc in enumerate((docs or [])[:6]):
            serial = doc.get("sequencialDocumento") or doc.get("sequencial") or i + 1
            url = safe_url(doc.get("url") or doc.get("uri") or doc.get("link")) or f"{base}/{serial}"
            name = clean(doc.get("titulo") or doc.get("nome") or doc.get("descricao") or f"Anexo {i+1}", 140)
            try:
                f = requests.get(url, headers=UA, timeout=25)
                diagnostics["requisicoes"] += 1
                if not f.ok or len(f.content) > 15_000_000:
                    continue
                is_pdf = "pdf" in f.headers.get("content-type", "").lower() or url.lower().endswith(".pdf")
                body = extract_pdf_text(f.content) if is_pdf else clean(f.text, 30000)
                if body:
                    texts.append(body)
                    names.append(name)
                if len(texts) >= 3:
                    break
            except Exception:
                continue
        joined = clean(" ".join(texts), 180000)
        return joined, names, ("ANALISADO" if len(joined) >= 500 else "LEITURA INCOMPLETA")
    except Exception as exc:
        diagnostics["avisos"].append(f"Anexos PNCP: {type(exc).__name__}: {str(exc)[:100]}")
        return "", [], "LEITURA INCOMPLETA"


REQUIREMENT_RULES = {
    "Registro profissional": ("crea", "conselho profissional", "registro profissional"),
    "ART / responsabilidade técnica": ("anotacao de responsabilidade tecnica", "responsavel tecnico"),
    "Atestado de capacidade técnica": ("atestado de capacidade tecnica", "capacidade tecnico-operacional", "capacidade tecnico-profissional"),
    "CAT / acervo técnico": ("certidao de acervo tecnico", "acervo tecnico"),
    "Equipe técnica mínima": ("equipe tecnica", "engenheiro agronomo", "engenheiro florestal", "engenheiro ambiental", "engenheiro civil"),
    "Visita técnica": ("visita tecnica", "vistoria tecnica"),
    "Qualificação econômico-financeira": ("qualificacao economico-financeira", "balanco patrimonial", "patrimonio liquido"),
    "Garantia": ("garantia de proposta", "garantia contratual"),
    "Consórcio": ("participacao em consorcio",),
    "Subcontratação": ("subcontratacao", "subcontratar"),
    "ME/EPP": ("microempresa", "empresa de pequeno porte", "me/epp"),
}


def analyze_requirements(text, profile):
    t = norm(text)
    found = [label for label, terms in REQUIREMENT_RULES.items() if any(term in t for term in terms)]
    pend = []
    confirmed = set(norm(x) for x in profile.get("comprovacoes_confirmadas", []))
    if "Atestado de capacidade técnica" in found and "atestado de capacidade tecnica" not in confirmed:
        pend.append("Confirmar atestado compatível com o objeto")
    if "CAT / acervo técnico" in found and "cat / acervo tecnico" not in confirmed:
        pend.append("Confirmar CAT/acervo técnico")
    if "Qualificação econômico-financeira" in found:
        pend.append("Validar índices e documentos financeiros")
    if not text:
        return found, "LEITURA INCOMPLETA", ["Abrir edital e anexos manualmente"]
    return found, ("VERIFICAR DOCUMENTOS" if pend else "ANÁLISE PRELIMINAR FAVORÁVEL"), pend


def pncp_request(endpoint, params, diagnostics):
    try:
        r = requests.get(endpoint, params=params, headers=UA, timeout=6)
        diagnostics["requisicoes"] += 1
        if r.status_code in (204, 404, 422):
            return {"data": [], "totalPaginas": 0}
        if r.status_code == 429:
            diagnostics["avisos"].append("PNCP respondeu 429 (limite temporário); uma repetição será tentada.")
            time.sleep(1)
            r = requests.get(endpoint, params=params, headers=UA, timeout=6)
            diagnostics["requisicoes"] += 1
            if r.status_code == 429:
                diagnostics["avisos"].append("PNCP manteve 429; consulta parcial preservada.")
                return {"data": [], "totalPaginas": 0}
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        diagnostics["erros"].append(f"PNCP: {type(exc).__name__}: {exc}"[:250])
        return {"data": [], "totalPaginas": 0}


def pncp_collect(cfg, mode, diagnostics):
    """Coleta PNCP em camadas, seguindo os parâmetros oficiais dos endpoints."""
    assert mode in ("proposta", "publicacao")
    base = f"https://pncp.gov.br/api/consulta/v1/contratacoes/{mode}"
    today = datetime.now().date()
    publication_ini = (today - timedelta(days=14)).strftime("%Y%m%d")
    publication_end = today.strftime("%Y%m%d")

    # Brasil vem primeiro e recebe maior profundidade. Goiás e Goianésia servem
    # para reforçar a proximidade, não para limitar a descoberta.
    scopes = [
        # Cinco datas de encerramento e duas modalidades nacionais prioritárias.
        # A publicação recente usa somente a primeira página de cada modalidade.
        ("Brasil", {}, MODALIDADES_NACIONAIS, 5 if mode == "proposta" else 1),
    ]
    out, seen = [], set()
    profile = load_json(PROFILE, {})
    scan_deadline = time.monotonic() + 90

    for scope_name, scope_params, modalidades, max_pages in scopes:
        for modalidade in modalidades:
            for page in range(1, max_pages + 1):
                if time.monotonic() >= scan_deadline:
                    diagnostics["avisos"].append(
                        f"PNCP {mode}: limite de 90 segundos atingido; resultado parcial preservado."
                    )
                    return out
                query_page = 1 if mode == "proposta" else page
                proposal_date = (today + timedelta(days=page - 1)).strftime("%Y%m%d")
                params = {
                    "dataFinal": proposal_date if mode == "proposta" else publication_end,
                    "codigoModalidadeContratacao": modalidade,
                    "pagina": query_page,
                    # A API oficial rejeita tamanhoPagina=100 com HTTP 400.
                    "tamanhoPagina": 50,
                    **scope_params,
                }
                if mode == "publicacao":
                    params["dataInicial"] = publication_ini

                data = pncp_request(base, params, diagnostics)
                # Evita rajadas que acionam o limite temporário HTTP 429.
                time.sleep(0.15)
                rows = data.get("data") or []
                if not rows:
                    if mode == "proposta":
                        continue
                    break
                diagnostics["pncp_registros_examinados"] += len(rows)

                for x in rows:
                    key = str(x.get("numeroControlePNCP") or "")
                    if key and key in seen:
                        continue
                    unit = x.get("unidadeOrgao") or {}
                    city = unit.get("municipioNome") or unit.get("nomeMunicipio") or ""
                    uf = unit.get("ufSigla") or unit.get("siglaUf") or scope_params.get("uf", "")
                    if not city and scope_name == "Goianésia":
                        city = "Goianésia"

                    # A decisão de relevância usa apenas o objeto e seu complemento.
                    # Nome do órgão/unidade não pode gerar falso positivo.
                    text = " ".join([
                        str(x.get("objetoCompra") or ""),
                        str(x.get("informacaoComplementar") or ""),
                    ])
                    if not relevant_procurement_object(text, cfg):
                        continue
                    hits, strong, explicit = meaningful_hits(text, cfg)
                    if not hits or (not strong and len(explicit) < 1):
                        continue

                    deadline = str(x.get("dataEncerramentoProposta") or "")
                    kind = "DEMANDA FORMAL" if mode == "proposta" else "SINAL DE CONTRATAÇÃO"
                    score, region, hits = score_item(city, uf, text, "DEMANDA FORMAL" if mode == "proposta" else "SINAL AMBIENTAL", cfg, deadline)
                    if mode == "publicacao" and score < 45:
                        continue

                    source = pncp_url_from_control(key) or safe_url(x.get("linkSistemaOrigem")) or "https://pncp.gov.br/app/editais"
                    edital_text, docs_read, reading_status = pncp_document_text(key, diagnostics)
                    requirements, eligibility, pending_docs = analyze_requirements(edital_text, profile)
                    out.append({
                        "id": key or f"pncp-{mode}-{scope_name}-{modalidade}-{len(out)+1}",
                        "tipo": kind,
                        "confirmacao": "CONFIRMADO" if docs_read and reading_status != "LEITURA INCOMPLETA" else "PRÉ-SELECIONADO",
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
                        "relacao_comercial": market_relation(text),
                        "status_leitura_edital": reading_status,
                        "documentos_analisados": docs_read,
                        "requisitos_minimos": requirements,
                        "analise_elegibilidade": eligibility,
                        "pendencias_identificadas": pending_docs,
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
                            "Abrir a publicação oficial e verificar se há prazo de proposta, futura licitação, contratação direta ou oportunidade institucional."
                        ),
                    })
                    if key:
                        seen.add(key)

                total = int(data.get("totalPaginas") or 1)
                if mode == "publicacao" and page >= total:
                    break
            time.sleep(0.15)

    diagnostics[f"pncp_{mode}"] = len(out)
    return out

def html_signals(cfg, diagnostics):
    sources = [
        ("PNCP", "https://pncp.gov.br/app/editais", "", "BR"),
        ("MMA", "https://www.gov.br/mma/pt-br/assuntos", "", "BR"),
        ("Ibama", "https://www.gov.br/ibama/pt-br/assuntos/noticias", "", "BR"),
        ("ICMBio", "https://www.gov.br/icmbio/pt-br/assuntos/noticias", "", "BR"),
        ("BNDES Floresta Viva", "https://www.bndes.gov.br/wps/portal/site/home/desenvolvimento-sustentavel/parcerias/floresta-viva", "", "BR"),
        ("Fundo Amazônia", "https://www.fundoamazonia.gov.br/pt/projetos/", "", "BR"),
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
    deep_checked = set()

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
            anchor = clean(a.get_text(" ", strip=True), 260)
            href = safe_url(urljoin(url, a["href"]))
            if not href or urlparse(href).netloc != urlparse(url).netloc:
                continue
            if href.rstrip("/") == url.rstrip("/") or href.endswith("#"):
                continue

            # O texto local é deliberadamente curto. Usar o corpo inteiro da página
            # fazia termos ambientais do menu contaminarem links de saúde e serviços.
            parent_text = clean(a.parent.get_text(" ", strip=True) if a.parent else "", 420)
            initial = f"{anchor} {parent_text}".strip()
            if clearly_non_environmental(initial) or institutional_page(initial) or stale_archive_title(initial):
                continue
            initial_hits, initial_strong, _ = meaningful_hits(initial, cfg)
            initial_formal = formal_language(initial)
            route = norm(urlparse(href).path)
            route_hint = any(x in route for x in ("edital", "licit", "publica", "noticia", "meioambiente", "ambient"))

            if is_generic_title(anchor) and not route_hint:
                continue
            if generic_url(href) and not initial_formal and not initial_strong:
                continue
            if not initial_hits and not route_hint:
                continue

            page_title, page_body = "", ""
            if href not in deep_checked and len(deep_checked) < 24:
                deep_checked.add(href)
                page_title, page_body = fetch_page_context(href, diagnostics)
            page_lead = clean(page_body, 1600)
            local_object = " ".join(x for x in (anchor, parent_text, page_title, page_lead) if x)
            if clearly_non_environmental(" ".join((anchor, page_title, page_lead))):
                continue
            if institutional_page(" ".join((anchor, page_title))):
                continue
            if stale_archive_title(" ".join((anchor, page_title))):
                continue
            env_ok, local_hits = environmental_evidence(local_object, cfg)
            if not env_ok:
                continue

            combined = local_object
            hits, strong, explicit = meaningful_hits(combined, cfg)
            formal = html_formal_evidence(" ".join((anchor, parent_text, page_title, page_lead)), href)

            if formal:
                if not hits or (not strong and len(explicit) < 1):
                    continue
                kind = "DEMANDA FORMAL"
            else:
                if not strong and len(explicit) < 2:
                    continue
                kind = "SINAL AMBIENTAL"

            display_title = page_title or anchor
            if is_generic_title(display_title):
                display_title = clean(parent_text, 260)
            if is_generic_title(display_title):
                continue
            if clearly_non_environmental(display_title) or stale_archive_title(display_title):
                continue

            k = (norm(display_title), href)
            if k in seen:
                continue
            seen.add(k)

            city = default_city
            for name in local_names:
                if norm(name) in norm(combined):
                    city = name
                    break

            score, region, hits = score_item(city, default_uf, combined, kind, cfg, "")
            if kind == "SINAL AMBIENTAL":
                score = max(0, score - 8)
            if score < 45:
                continue

            out.append({
                "id": "web-" + hashlib.sha1(("||".join(k)).encode("utf-8")).hexdigest()[:12],
                "tipo": kind,
                "confirmacao": "CONFIRMADO" if kind == "DEMANDA FORMAL" else "PROVÁVEL",
                "fonte": fonte,
                "titulo": display_title,
                "municipio": city,
                "uf": default_uf,
                "regiao_prioridade": region,
                "organizacao": fonte,
                "data_publicacao": "",
                "prazo": "",
                "valor_estimado": None,
                "modalidade": "",
                "servicos_ordone": [x for x in services_from(combined) if x != "Avaliação técnica inicial"],
                "relacao_comercial": (
                    market_relation(combined) if kind == "DEMANDA FORMAL"
                    else "Possível aderência ambiental — validar"
                ),
                "palavras_encontradas": hits[:10],
                "score": score,
                "prioridade": priority(score),
                "url": href,
                "proxima_acao": (
                    "Abrir a publicação oficial e confirmar objeto, prazo e condições antes de qualquer abordagem."
                    if kind == "DEMANDA FORMAL" else
                    "Validar o contexto e confirmar se o sinal representa demanda técnica real antes de classificar como oportunidade comercial."
                ),
            })
            if len(out) >= 24:
                break

    diagnostics["html_sinais"] = len(out)
    diagnostics["paginas_aprofundadas"] = len(deep_checked)
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
        "versao": "4.7",
        "atualizado_em": datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M"),
        "status": "coleta_concluida",
        "prioridade": "Brasil inteiro → bônus de proximidade para Goiás e Goianésia",
        "resumo": {
            "total": len(items),
            "brasil": len(items),
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
    assert is_generic_title("Ver todos os serviços")
    assert is_generic_title("Saiba mais")
    assert not is_generic_title("Recuperação de área degradada em nascente")
    assert clearly_non_environmental("Solicitar Carteira de Fibromialgia")
    assert stale_archive_title("Editais e Publicações até 2024")
    ok, _ = environmental_evidence("Contratação de recuperação de área degradada", cfg)
    assert ok
    bad, _ = environmental_evidence("Solicitar Carteira de Fibromialgia", cfg)
    assert not bad
    assert "pncp.gov.br/app/editais/" in pncp_url_from_control("07954605000160-1-000176/2026")
    req, elig, pend = analyze_requirements("Exige CREA, responsável técnico e atestado de capacidade técnica", {})
    assert "Registro profissional" in req and "Atestado de capacidade técnica" in req and pend
    assert institutional_page("Perguntas Frequentes - Ibama")
    assert institutional_page("Escola de Meio Ambiente (Emago)")
    assert not html_formal_evidence("contratação ambiental direta", "https://exemplo.gov.br/assuntos")
    assert html_formal_evidence("Edital nº 12 objeto e prazo para propostas", "https://exemplo.gov.br/licitacoes/edital-12")
    false_objects = (
        "Locação de computadores, notebooks, tablets e monitores para a Secretaria de Meio Ambiente",
        "Solução SaaS de atendimento por WhatsApp com inteligência artificial",
        "Locação de caminhão coletor e compactador de resíduos sólidos",
    )
    assert not any(relevant_procurement_object(x, cfg) for x in false_objects)
    assert relevant_procurement_object("Execução de PRAD e revegetação de área degradada", cfg)
    print("SELF-TEST OK V4.9", s, r, len(h), "falsos positivos bloqueados")


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
        "pncp_registros_examinados": 0,
        "html_sinais": 0,
        "paginas_aprofundadas": 0,
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
    print("Radar V4.9 atualizado:", len(items), "itens; registros PNCP examinados:", diagnostics["pncp_registros_examinados"], "requisições:", diagnostics["requisicoes"])


if __name__ == "__main__":
    main()
