#!/usr/bin/env python3
"""National agricultural-drone service radar. No contact or proposal submission.

Official APIs: https://pncp.gov.br/api/consulta/swagger-ui/index.html
https://dadosabertos.compras.gov.br/swagger-ui/index.html
Coverage is bounded and reported, never described as all Brazilian procurements.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import io
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "dados/radar_drones_config.json"
OUTPUT = ROOT / "dados/radar_drones.json"
TZ = ZoneInfo("America/Sao_Paulo")
PNCP = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
COMPRAS = "https://dadosabertos.compras.gov.br/modulo-contratacoes/1_consultarContratacoes_PNCP_14133"
UA = "OrdoneDroneRadar/1.0 (+https://ordoneagroambiental.github.io/midia/)"
CLASSES = ("oportunidade_formal", "parceria", "analise_pendente", "prospeccao")


def now():
    return datetime.now(TZ)


def norm(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()).strip()


def clean(value, limit=None):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:limit] if limit else value


def parse_deadline(value):
    # A date without a time is NOT a verified submission deadline.
    if not value or not re.search(r"\d{2}:\d{2}", str(value)):
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (result if result.tzinfo else result.replace(tzinfo=TZ)).astimezone(TZ)
    except (ValueError, TypeError):
        return None


def control_parts(value):
    match = re.fullmatch(r"([A-Za-z0-9]{14})-\d+-0*(\d+)/(\d{4})", str(value or ""))
    return match.groups() if match else None


def official_url(control):
    parts = control_parts(control)
    if not parts:
        return ""
    cnpj, seq, year = parts
    return f"https://pncp.gov.br/app/editais/{cnpj}/{year}/{int(seq)}"


def drone_services(objeto):
    """Object must explicitly contract execution, agricultural context AND drone.

    Reject purchase/training as principal object even when the specification says
    the machine can spray. Do not infer drone work from generic aerial spraying.
    """
    text = norm(objeto)
    if not re.search(r"\bdrones?\b|\barps?\b|\brpas?\b|aeronaves? remotamente pilotad|veiculos? aereos? nao tripulad", text):
        return []
    if not re.search(r"\bservic\w*|\bexecucao\b|\bprestacao\b|\bcredenciamento\b|contratacao de (?:empresa|pessoa juridica|profissional)", text):
        return []
    excluded = (
        r"\b(?:aquisicao|compra)\b.{0,65}\b(?:drones?|aeronaves?|equipamentos?|pecas?|baterias?)\b",
        r"\b(?:manutencao|conserto|reparo|assistencia tecnica)\b.{0,45}\b(?:drones?|aeronaves?|equipamentos?)\b",
        r"\b(?:curso|cursos|capacitacao|treinamento|formacao de pilotos)\b",
        r"\b(?:filmagem|fotografia|vigilancia|aerolevantamento|fotogrametria|mapeamento|inspecao de estruturas)\b",
        r"\b(?:dengue|aedes|pragas urbanas|desinfeccao|dedetizacao)\b",
        r"\blocacao\b.{0,40}\bsem (?:piloto|operador)\b",
    )
    if any(re.search(pattern, text) for pattern in excluded):
        return []
    # Anchor drone to an application clause, rather than an unrelated item of a package.
    action = r"pulveriz\w*|semeadur\w*|semeio|dispersao de sementes|distribuicao de (?:sementes|fertilizantes|insumos)|aplicacao de (?:herbicidas|fungicidas|inseticidas|defensivos|agroquimicos|fertilizantes|adubos|insumos)|adubacao|aplicacao agricola|aplicacao aeroagricola"
    drone = r"drone\w*|aeronave\w* remotamente pilotad\w*|\barp\b|\brpa\b"
    if not re.search(rf"(?:{action}).{{0,160}}(?:{drone})|(?:{drone}).{{0,160}}(?:{action})", text):
        return []
    if not re.search(r"agric\w*|aeroagric\w*|pastage\w*|florest\w*|lavour\w*|rura\w*|cultivo\w*|reveget\w*|reflorest\w*|area\w* degradad\w*|herbicid\w*|fungicid\w*|fertiliz\w*|adub\w*|sement\w*|defensiv\w*", text):
        return []
    services = []
    if re.search(r"pulveriz\w*|herbicid\w*|fungicid\w*|inseticid\w*|defensiv\w*|agroquimic\w*", text):
        services.append("Aplicação agrícola / florestal")
    if re.search(r"semeadur\w*|semeio|sement\w*", text):
        services.append("Semeadura / distribuição de sementes")
    if re.search(r"fertiliz\w*|adub\w*", text):
        services.append("Aplicação de fertilizantes")
    if not services:
        services.append("Aplicação de insumos agrícolas")
    return services


def envelope(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "resultado", "resultados", "items", "contratacoes"):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def candidate(row, source, reference_time):
    if str(row.get("contratacaoExcluida", "")).lower() in ("true", "1", "sim"):
        return None
    situation = norm(row.get("situacaoCompraNome") or row.get("situacaoCompraNomePncp"))
    if re.search(r"encerrad|homologad|revogad|anulad|cancelad|suspens|fracassad|desert", situation):
        return None
    # In PNCP domain: only 1 (Divulgada) is an active procurement.
    if row.get("situacaoCompraId") not in (None, 1, "1"):
        return None
    text = clean(row.get("objetoCompra") or row.get("objeto") or row.get("descricaoObjeto"))
    services = drone_services(text)
    if not services:
        return None
    deadline = parse_deadline(row.get("dataEncerramentoPropostaPncp") or row.get("dataEncerramentoProposta") or row.get("dataFimProposta"))
    if not deadline or deadline <= reference_time:
        return None
    control = clean(row.get("numeroControlePNCP") or row.get("numeroControlePncp") or row.get("numero_controle_pncp"))
    if not official_url(control):
        return None
    unit = row.get("unidadeOrgao") or {}
    org = row.get("orgaoEntidade") or {}
    uf = clean(unit.get("ufSigla") or row.get("unidadeOrgaoUfSigla") or row.get("ufSigla")).upper()
    value = row.get("valorTotalEstimado", row.get("valorTotalEstimadoPncp"))
    try:
        value = float(value) if value is not None else None
    except (ValueError, TypeError):
        value = None
    return {
        "id": control, "classificacao": "analise_pendente", "titulo": text,
        "objeto": text, "contratante": clean(org.get("razaoSocial") or row.get("orgaoEntidadeRazaoSocial") or row.get("nomeOrgao")) or None,
        "municipio": clean(unit.get("municipioNome") or row.get("unidadeOrgaoMunicipioNome") or row.get("municipioNome")) or None,
        "uf": uf or None, "servicos": services, "prazo_final": deadline.isoformat(),
        "valor_estimado": value, "modalidade": clean(row.get("modalidadeNome") or row.get("modalidadeNomePncp") or row.get("modalidadeCompraNome")) or None,
        "numero_processo": clean(row.get("processo") or row.get("numeroProcesso")) or None,
        "plataforma": clean(row.get("nomeUsuario")) or ("Compras.gov.br" if source.startswith("Compras") else "Consultar processo oficial"),
        "url_oficial": official_url(control), "url_participacao": row.get("linkSistemaOrigem") if str(row.get("linkSistemaOrigem", "")).startswith("https://") else None,
        "fonte": source, "verificado_em": reference_time.isoformat(),
        "aderencia": 70 + (15 if uf == "GO" else 10 if uf in ("DF", "MG") else 0),
        "pontos_pendentes": ["Conferir edital, habilitação, acervo e disponibilidade operacional; capacidade da Ordone ainda não comprovada para este processo."],
        "acao_recomendada": "Abrir o processo oficial e validar documentos antes de decidir pela participação.",
        "documentos": {"status": "nao_analisada", "links": [], "trechos": [], "paginas_lidas": 0, "falhas": []},
        "requisitos": {"area_hectares": None, "equipamentos": [], "equipe": [], "registros": [], "acervo": [], "insumos": [], "parceria": []},
    }


class Fetcher:
    def __init__(self, until, timeout=12, attempts=2):
        self.until = until
        self.timeout = timeout
        self.attempts = attempts

    def get(self, url, params=None, as_json=True, max_bytes=12_000_000):
        if not url.startswith("https://"):
            raise ValueError("Documento sem HTTPS não lido automaticamente")
        if params:
            url += "?" + urlencode(params)
        last = "limite de tempo"
        for attempt in range(self.attempts):
            remaining = self.until - time.monotonic()
            if remaining < 1:
                break
            try:
                with urlopen(Request(url, headers={"User-Agent": UA, "Accept": "application/json,*/*"}), timeout=min(self.timeout, remaining)) as response:
                    if response.status == 204:
                        return {"data": [], "totalPaginas": 0} if as_json else b""
                    body = response.read(max_bytes + 1)
                    if len(body) > max_bytes:
                        raise ValueError("Arquivo excede limite de leitura")
                    return json.loads(body.decode("utf-8")) if as_json else body
            except HTTPError as exc:
                last = f"HTTP {exc.code}"
                if exc.code not in (408, 429, 500, 502, 503, 504):
                    break
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                last = type(exc).__name__ + ": " + clean(str(exc), 130)
            if attempt + 1 < self.attempts:
                time.sleep(max(0, min(1.5 * (attempt + 1), self.until - time.monotonic())))
        raise RuntimeError(last)


def scan_source(kind, cfg, reference_time):
    pc = kind == "PNCP"
    source = cfg["fontes"]["pncp" if pc else "compras_gov"]
    url = PNCP if pc else COMPRAS
    until = time.monotonic() + source["limite_segundos"]
    fetcher = Fetcher(until, cfg["timeout_segundos"], cfg["tentativas"])
    diag = {"nome": kind, "url": url, "status": "nao_consultada", "paginas_consultadas": 0,
            "registros_examinados": 0, "candidatos": 0, "falhas": [], "detalhes": [],
            "dias_publicacao": source["dias_publicacao"], "modalidades_planejadas": source["modalidades"],
            "consultas": [], "cobertura_completa": False}
    today = reference_time.date()
    start = today - timedelta(days=source["dias_publicacao"])
    candidates = []
    # Round robin visits each modality before advancing pages, preventing a huge
    # modality from starving the others. First + newest pages when total is known.
    queues = {mod: [1] for mod in source["modalidades"]}
    known_totals = {}
    exhausted = set()
    while queues and diag["paginas_consultadas"] < source["max_paginas"]:
        progressed = False
        for mod in list(queues):
            if time.monotonic() >= until or diag["paginas_consultadas"] >= source["max_paginas"]:
                break
            if not queues[mod]:
                continue
            page = queues[mod].pop(0)
            params = {"pagina": page, "tamanhoPagina": 50 if pc else 500}
            if pc:
                params.update(dataInicial=start.strftime("%Y%m%d"), dataFinal=today.strftime("%Y%m%d"), codigoModalidadeContratacao=mod)
            else:
                params.update(dataPublicacaoPncpInicial=start.isoformat(), dataPublicacaoPncpFinal=today.isoformat(), codigoModalidade=mod)
            try:
                payload = fetcher.get(url, params)
                rows = envelope(payload)
                if not isinstance(payload, dict) or not any(k in payload for k in ("data", "resultado", "resultados", "items", "contratacoes")):
                    raise ValueError("Envelope da API não reconhecido")
                total = payload.get("totalPaginas")
                total = int(total) if total is not None else None
                diag["paginas_consultadas"] += 1
                diag["registros_examinados"] += len(rows)
                diag["consultas"].append({"modalidade": mod, "pagina": page, "total_paginas": total, "registros": len(rows)})
                progressed = True
                for row in rows:
                    item = candidate(row, kind, reference_time)
                    if item:
                        candidates.append(item)
                if page == 1:
                    known_totals[mod] = total
                    if total is None:
                        diag["detalhes"].append(f"Modalidade {mod}: API sem total de páginas; cobertura desconhecida.")
                    else:
                        # Tail pages then the middle: broad recent discovery within a cap.
                        queues[mod] = list(range(total, 1, -1))
                if total == 0 or (total is not None and not queues[mod]):
                    exhausted.add(mod)
            except Exception as exc:
                diag["falhas"].append(f"Modalidade {mod}, página {page}: {clean(exc, 180)}")
                # Do not retry this group forever. Fetcher already attempted twice.
                queues[mod] = []
            if time.monotonic() < until:
                time.sleep(0.35)
        if not progressed or not any(queues.values()) or time.monotonic() >= until:
            break
    diag["candidatos"] = len(candidates)
    diag["cobertura_completa"] = len(exhausted) == len(source["modalidades"]) and not diag["falhas"]
    diag["status"] = "completa_no_recorte" if diag["cobertura_completa"] else "parcial" if diag["paginas_consultadas"] else "falha"
    if not diag["cobertura_completa"]:
        diag["detalhes"].append("Limite de tempo/páginas, falha ou paginação desconhecida: esta fonte NÃO foi consultada integralmente.")
    diag["detalhes"].append(f"Brasil, publicações de {start.isoformat()} a {today.isoformat()}; modalidades {source['modalidades']}.")
    return candidates, diag


def pdf_text(content, max_pages):
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", 0, "Leitor PDF indisponível"
    try:
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > max_pages:
            return "", 0, f"PDF excede {max_pages} páginas; exige leitura complementar"
        pages = [page.extract_text() or "" for page in reader.pages]
        # Scans (even a partially scanned attachment) stay pending; no inferred text.
        if any(len(clean(page)) < 20 for page in pages):
            return "\n".join(pages), len(pages), "PDF contém página sem texto extraível; conferir visualmente"
        return "\n".join(pages), len(pages), ""
    except Exception as exc:
        return "", 0, "Falha de leitura PDF: " + type(exc).__name__


def collect_documents(item, cfg, fetcher):
    parts = control_parts(item["id"])
    cnpj, seq, year = parts
    base = f"https://pncp.gov.br/pncp-api/v1/orgaos/{cnpj}/compras/{year}/{int(seq)}/arquivos"
    result = {"status": "indisponivel", "links": [], "trechos": [], "paginas_lidas": 0, "falhas": []}
    try:
        catalogue = fetcher.get(base)
        docs = catalogue if isinstance(catalogue, list) else envelope(catalogue)
        docs = [d for d in docs if d.get("ativo", True) is not False and d.get("statusAtivo", True) is not False]
        if not docs:
            result["falhas"].append("Catálogo oficial sem documentos acessíveis")
            return result, ""
        if len(docs) > cfg["max_anexos_por_processo"]:
            result["falhas"].append("Catálogo excede limite de anexos; leitura parcial")
        texts = []
        for doc in docs[:cfg["max_anexos_por_processo"]]:
            serial = doc.get("sequencialDocumento") or doc.get("sequencial")
            url = doc.get("url") or doc.get("uri") or (f"{base}/{serial}" if serial else "")
            title = clean(doc.get("titulo") or doc.get("nome") or f"Anexo {serial}", 200)
            if not url:
                result["falhas"].append(f"{title}: endereço não informado")
                continue
            result["links"].append({"titulo": title, "url": url})
            try:
                content = fetcher.get(url, as_json=False)
                if not content.startswith(b"%PDF-"):
                    result["falhas"].append(f"{title}: formato sem leitura automática integral (ex.: ZIP/planilha)")
                    continue
                text, pages, error = pdf_text(content, cfg["max_paginas_pdf"])
                result["paginas_lidas"] += pages
                if error:
                    result["falhas"].append(f"{title}: {error}")
                if text:
                    texts.append(text)
                    for line in re.split(r"[\n\r]+", text):
                        if re.search(r"drone|pulveriz|semeadur|fertilizan|defensiv", norm(line)):
                            result["trechos"].append({"documento": title, "texto": clean(line, 450)})
            except Exception as exc:
                result["falhas"].append(f"{title}: {clean(exc, 150)}")
        result["trechos"] = result["trechos"][:12]
        result["status"] = "completa" if texts and not result["falhas"] else "parcial" if texts else "indisponivel"
        return result, "\n".join(texts)
    except Exception as exc:
        result["falhas"].append("Catálogo PNCP: " + clean(exc, 180))
        return result, ""


def classify(item, documents, text):
    item["documentos"] = documents
    if documents["status"] != "completa":
        item["pontos_pendentes"].append("Leitura dos anexos " + documents["status"] + "; não publicar como oportunidade formal validada.")
        return item
    # Principal-object exclusions belong to the procurement object. Applying
    # them to an entire edital would reject a valid spray service just because
    # its operator must hold a CAAR course or use mapping to plan the operation.
    # Confirm the exact already-screened object or an independent service clause.
    clauses = re.split(r"[.;]\s+|\n\s*\n", text)
    object_repeated = norm(item["objeto"]).rstrip(".;") in norm(text)
    confirmed_service = object_repeated or any(drone_services(clause) for clause in clauses)
    if not confirmed_service:
        item["pontos_pendentes"].append("Anexos lidos, mas o serviço não pôde ser confirmado automaticamente no texto; revisão humana necessária.")
        return item
    normalized = norm(text)
    # Extract verbatim context only. No synthetic legal eligibility assertions.
    patterns = {
        "equipamentos": r"drone|aeronave|distribuidor de solidos",
        "equipe": r"piloto|operador|engenheiro agronomo",
        "registros": r"\bcrea\b|\bart\b|\bcaar\b|sipeagro|sarpas|\banac\b|\bmapa\b",
        "acervo": r"atestado|acervo|\bcat\b",
        "insumos": r"fornecimento.{0,30}(?:insumos|defensivos|sementes)|(?:insumos|defensivos|sementes).{0,35}contratante",
    }
    for key, pattern in patterns.items():
        for line in re.split(r"[\n\r]+", text):
            if re.search(pattern, norm(line)):
                value = clean(line, 450)
                if value not in item["requisitos"][key]:
                    item["requisitos"][key].append(value)
        item["requisitos"][key] = item["requisitos"][key][:5]
    if re.search(r"(?:minimo|simultaneamente).{0,35}(?:[2-9]|dois|tres|quatro)\s*drones|(?:[2-9]|dois|tres|quatro)\s*drones.{0,35}simultan", normalized):
        item["classificacao"] = "parceria"
        item["requisitos"]["parceria"] = ["Capacidade adicional de drones e equipe: verificar exigência de operação simultânea e possibilidade de subcontratação/consórcio."]
        item["acao_recomendada"] = "Confirmar quantidade de equipamentos, janela operacional e regra de parceria antes de negociar apoio."
    else:
        item["classificacao"] = "oportunidade_formal"
        item["acao_recomendada"] = "Validar habilitação, acervo, capacidade e custos de mobilização; depois preparar orçamento."
    item["aderencia"] = min(100, item["aderencia"] + 10)
    return item


def deduplicate(items):
    unique = {}
    for item in items:
        # PNCP current record wins over replicated Compras.gov record.
        if item["id"] not in unique or item["fonte"] == "PNCP":
            unique[item["id"]] = item
    return list(unique.values())


def run(cfg, output_path=OUTPUT):
    reference_time = now()
    previous = {}
    if output_path.exists():
        try:
            previous = json.loads(output_path.read_text())
        except (OSError, ValueError):
            pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda source: scan_source(source, cfg, reference_time), ("PNCP", "Compras.gov.br")))
    candidates = deduplicate([item for items, _ in results for item in items])
    candidates.sort(key=lambda x: (-x["aderencia"], x["prazo_final"]))
    sources = [diag for _, diag in results]
    fetcher = Fetcher(time.monotonic() + cfg["limite_anexos_segundos"], cfg["timeout_segundos"], cfg["tentativas"])
    for item in candidates:
        if time.monotonic() < fetcher.until:
            documents, text = collect_documents(item, cfg, fetcher)
            classify(item, documents, text)
        else:
            item["pontos_pendentes"].append("Limite de tempo da leitura de anexos atingido.")
    # Recheck after collection; never preserve unverified former records as current.
    candidates = [item for item in candidates if parse_deadline(item["prazo_final"]) > now()]
    success = any(source["paginas_consultadas"] for source in sources)
    complete = all(source["cobertura_completa"] for source in sources)
    state = "completa_no_recorte" if complete else "parcial" if success else "falha"
    stamp = now().isoformat()
    counts = Counter(item["classificacao"] for item in candidates)
    warnings = ["Cobertura nacional por fontes públicas integradas e recorte temporal; não representa todas as contratações do Brasil.",
                "Agendamento previsto a cada 2 horas; execução e publicação podem sofrer atrasos do GitHub Actions.",
                "Portais privados, BLL, Licitanet e Portal de Compras Públicas ainda não possuem integração direta nesta versão.",
                "Oportunidade formal confirma demanda e leitura de anexos; não comprova habilitação da Ordone nem garante contratação."]
    if not complete:
        warnings.append("Coleta incompleta: veja cobertura e falhas por fonte. Ausência de resultados não comprova ausência de demanda.")
    if not success:
        warnings.append("Nenhuma fonte respondeu validamente nesta tentativa; registros antigos não foram apresentados como atuais.")
    payload = {
        "versao": "1.0", "gerado_em": stamp, "ultima_coleta_concluida_em": stamp if success else previous.get("ultima_coleta_concluida_em"),
        "status_coleta": state, "abrangencia": "Brasil", "atualizacao_programada_horas": 2,
        "limites": {"pncp": cfg["fontes"]["pncp"], "compras_gov": cfg["fontes"]["compras_gov"], "anexos_segundos": cfg["limite_anexos_segundos"]},
        "avisos": warnings, "fontes": sources,
        "resumo": {"oportunidades_formais": counts["oportunidade_formal"], "parcerias": counts["parceria"], "analise_pendente": counts["analise_pendente"], "prospeccao": counts["prospeccao"]},
        "oportunidades": candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    print(json.dumps({"status": state, "resumo": payload["resumo"], "paginas": sum(s["paginas_consultadas"] for s in sources), "registros": sum(s["registros_examinados"] for s in sources)}, ensure_ascii=False))
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(json.loads(CONFIG.read_text(encoding="utf-8")), args.output)
