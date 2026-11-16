"""
Backend FastAPI + Scraper + Integração Neon.db (PostgreSQL)
Sistema de Gerenciamento de Repertório Musical (Meu Cifra Club / Meu-cifra-club Club)
"""

import base64
from contextlib import asynccontextmanager
import os
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from duckduckgo_search import DDGS
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field
import requests


# ---------------------------------------------------------------------------
# Configuração e Variáveis de Ambiente
# ---------------------------------------------------------------------------

def _load_local_env() -> None:
    """Carrega variáveis de um arquivo .env local, se existir (sem depender de python-dotenv)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_local_env()


def get_database_url() -> str:
    url = os.environ.get("NEON_DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Variável de ambiente NEON_DATABASE_URL não configurada. "
                "Defina a string de conexão do Neon.db antes de iniciar o servidor."
            ),
        )
    return url


def get_db_connection():
    """Abre uma nova conexão com o PostgreSQL (Neon.db)."""
    dsn = get_database_url()
    return psycopg2.connect(dsn, cursor_factory=RealDictCursor)


def init_db() -> None:
    """Cria a tabela `musicas` automaticamente caso não exista."""
    url = os.environ.get("NEON_DATABASE_URL", "").strip()
    if not url:
        print(
            "[AVISO] NEON_DATABASE_URL não definida. "
            "A tabela 'musicas' será criada assim que a variável for configurada."
        )
        return

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS musicas (
        id SERIAL PRIMARY KEY,
        titulo VARCHAR(255) NOT NULL,
        cantor VARCHAR(255) NOT NULL,
        autor VARCHAR(255) NULL,
        tom VARCHAR(20) NOT NULL,
        cifra_completa TEXT NOT NULL,
        cifra_sem_solo TEXT NOT NULL,
        exibir_solo BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_musicas_titulo_cantor ON musicas (LOWER(TRIM(titulo)), LOWER(TRIM(cantor)));

    CREATE TABLE IF NOT EXISTS pastas (
        id SERIAL PRIMARY KEY,
        nome VARCHAR(100) NOT NULL,
        cor VARCHAR(30) DEFAULT '#ff7a18',
        created_at TIMESTAMP DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS pasta_musicas (
        pasta_id INT REFERENCES pastas(id) ON DELETE CASCADE,
        musica_id INT REFERENCES musicas(id) ON DELETE CASCADE,
        ordem INT DEFAULT 0,
        PRIMARY KEY (pasta_id, musica_id)
    );
    """
    with psycopg2.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
        conn.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Meu Cifra Club API",
    description="API de gerenciamento de repertório musical com scraping de cifras e Neon.db.",
    version="1.0.0",
    lifespan=lifespan,
)

# Habilita CORS para permitir acesso do Frontend local ou hospedado (ex: GitHub Pages)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Modelos Pydantic
# ---------------------------------------------------------------------------

class AdicionarMusicaRequest(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=255)
    cantor: str = Field(..., min_length=1, max_length=255)
    autor: Optional[str] = Field(default=None, max_length=255)
    tom: Optional[str] = Field(default=None, max_length=20)
    com_solo: bool = False
    cifra_manual: Optional[str] = None


class AtualizarMusicaRequest(BaseModel):
    titulo: Optional[str] = Field(default=None, min_length=1, max_length=255)
    cantor: Optional[str] = Field(default=None, min_length=1, max_length=255)
    autor: Optional[str] = Field(default=None, max_length=255)
    tom: Optional[str] = Field(default=None, min_length=1, max_length=20)
    cifra_completa: Optional[str] = None
    cifra_sem_solo: Optional[str] = None
    exibir_solo: Optional[bool] = None


class CriarPastaRequest(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    cor: Optional[str] = Field(default="#ff7a18", max_length=30)


class AdicionarMusicaPastaRequest(BaseModel):
    musica_id: int


# ---------------------------------------------------------------------------
# Motor Musical: Detecção de Acordes, Tom e Transposição
# ---------------------------------------------------------------------------

SHARP_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NOTES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"}

NOTE_TO_INDEX = {
    "C": 0, "B#": 0,
    "C#": 1, "Db": 1,
    "D": 2,
    "D#": 3, "Eb": 3,
    "E": 4, "Fb": 4,
    "F": 5, "E#": 5,
    "F#": 6, "Gb": 6,
    "G": 7,
    "G#": 8, "Ab": 8,
    "A": 9,
    "A#": 10, "Bb": 10,
    "B": 11, "Cb": 11,
}

# Expressão regular para identificar acordes musicais válidos (incluindo baixos invertidos)
CHORD_TOKEN_RE = re.compile(
    r"^(?P<root>[A-G](?:#|b)?)"
    r"(?P<quality>(?:m|maj|min|dim|aug|sus|add|M|º|°|\+|[0-9]|(?:\([^)]+\)))*)"
    r"(?:/(?P<bass>[A-G](?:#|b)?))?$"
)

# Tokens comuns em linhas de cifra que não são acordes (ex: repetições, barras)
CHORD_LINE_FILLERS = {"|", "/", "-", "–", "x", "X", "(", ")", "[", "]", "~", "•", "*"}


def normalize_key_name(raw_key: str) -> Optional[str]:
    """Normaliza uma string de tonalidade (ex: 'am' -> 'Am', 'f#' -> 'F#')."""
    if not raw_key:
        return None
    cleaned = raw_key.strip()
    m = re.match(r"^([A-Ga-g])([#b]?)(m?)$", cleaned)
    if not m:
        return None
    note = m.group(1).upper() + m.group(2)
    minor = "m" if m.group(3).lower() == "m" else ""
    if note not in NOTE_TO_INDEX:
        return None
    return f"{note}{minor}"


def parse_key_semitone(key_str: str) -> Optional[tuple[int, bool]]:
    """Retorna (indice_semitom, eh_menor) para uma tonalidade."""
    norm = normalize_key_name(key_str)
    if not norm:
        return None
    is_minor = norm.endswith("m")
    root = norm[:-1] if is_minor else norm
    return NOTE_TO_INDEX[root], is_minor


def is_chord_token(token: str) -> bool:
    """Verifica se um token isolado representa um acorde válido."""
    stripped = token.strip("()[].,;:")
    if not stripped:
        return False
    # Evita falsos positivos como palavras comuns "A", "E", "Em" isoladas sem contexto?
    # Aqui validamos a sintaxe estrita do acorde; o contexto da linha decide se é linha de cifra.
    return bool(CHORD_TOKEN_RE.match(stripped))


def is_chord_line(line: str) -> bool:
    """Determina se uma linha é composta predominantemente por acordes."""
    stripped = line.strip()
    if not stripped:
        return False
    # Ignora linhas de tablatura
    if "|" in stripped and "---" in stripped:
        return False

    # Remove rótulos de seção no início da linha, ex: "[Intro] G D Em C" ou "Intro: G D"
    cleaned = re.sub(r"^\[[^\]]+\]\s*", "", stripped)
    cleaned = re.sub(r"^(?:Intro|Refrão|Estrofe|Solo|Ponte|Final|Pré-refrão)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    if not cleaned:
        return False

    tokens = cleaned.split()
    chord_count = 0
    non_chord_count = 0
    for tok in tokens:
        if tok in CHORD_LINE_FILLERS or re.match(r"^[0-9]+x$", tok, re.IGNORECASE):
            continue
        if is_chord_token(tok):
            chord_count += 1
        else:
            non_chord_count += 1

    if chord_count == 0:
        return False
    # Se todos os tokens significativos são acordes, ou ampla maioria (>= 70%)
    return non_chord_count == 0 or (chord_count / (chord_count + non_chord_count)) >= 0.7


def extract_chords_from_text(texto_cifra: str) -> list[str]:
    """Extrai a sequência de acordes encontrados nas linhas de cifra."""
    chords: list[str] = []
    for line in texto_cifra.splitlines():
        if not is_chord_line(line):
            continue
        cleaned = re.sub(r"^\[[^\]]+\]\s*", "", line.strip())
        for tok in cleaned.split():
            tok_clean = tok.strip("()[].,;:")
            if is_chord_token(tok_clean):
                chords.append(tok_clean)
    return chords


def detectar_tom(texto_cifra: str, tom_pagina: Optional[str] = None) -> str:
    """
    Detecta o tom original da cifra.
    Prioriza o tom extraído da página (se válido); caso contrário, analisa os acordes do texto.
    """
    if tom_pagina:
        norm = normalize_key_name(tom_pagina)
        if norm:
            return norm

    chords = extract_chords_from_text(texto_cifra)
    if not chords:
        return "C"

    scores: dict[str, float] = {}
    for idx, chord in enumerate(chords):
        m = CHORD_TOKEN_RE.match(chord)
        if not m:
            continue
        root = m.group("root")
        quality = m.group("quality") or ""
        is_minor = quality.startswith("m") and not quality.startswith("maj")
        candidate = f"{root}{'m' if is_minor else ''}"

        weight = 1.0
        if idx == 0:
            weight += 2.5  # Primeiro acorde tem forte peso harmônico
        if idx == len(chords) - 1:
            weight += 2.0  # Último acorde costuma resolver na tônica
        scores[candidate] = scores.get(candidate, 0.0) + weight

    if not scores:
        return "C"
    return max(scores.items(), key=lambda item: item[1])[0]


def transpose_note(note: str, semitones: int, use_flats: bool = False) -> str:
    """Transpõe uma única nota (ex: 'F#' + 1 -> 'G')."""
    idx = NOTE_TO_INDEX.get(note)
    if idx is None:
        return note
    new_idx = (idx + semitones) % 12
    scale = FLAT_NOTES if use_flats else SHARP_NOTES
    return scale[new_idx]


def transpose_chord(chord: str, semitones: int, use_flats: bool = False) -> str:
    """Transpõe um acorde completo preservando qualidade e baixo invertido."""
    m = CHORD_TOKEN_RE.match(chord)
    if not m:
        return chord
    new_root = transpose_note(m.group("root"), semitones, use_flats)
    quality = m.group("quality") or ""
    bass = m.group("bass")
    if bass:
        new_bass = transpose_note(bass, semitones, use_flats)
        return f"{new_root}{quality}/{new_bass}"
    return f"{new_root}{quality}"


def transpor_linha_acordes(line: str, semitones: int, use_flats: bool = False) -> str:
    """
    Transpõe todos os acordes de uma linha preservando ao máximo
    o alinhamento horizontal sobre as sílabas da letra.
    """
    if semitones % 12 == 0:
        return line

    result: list[str] = []
    pos = 0
    pending_delta = 0

    for m in re.finditer(r"\S+", line):
        start, end = m.span()
        space_len = start - pos

        # Ajusta espaços seguintes se o acorde anterior mudou de largura
        if space_len > 0 and pending_delta != 0:
            adjusted = max(1, space_len - pending_delta)
            pending_delta -= (space_len - adjusted)
            result.append(" " * adjusted)
        else:
            result.append(line[pos:start])

        token = m.group(0)
        # Separa pontuações envolventes como parênteses
        lead_match = re.match(r"^([(\[]*)(.+?)([)\],;:]*)$", token)
        if lead_match:
            prefix, core, suffix = lead_match.groups()
        else:
            prefix, core, suffix = "", token, ""

        if is_chord_token(core):
            new_core = transpose_chord(core, semitones, use_flats)
            new_token = f"{prefix}{new_core}{suffix}"
            pending_delta += len(new_token) - len(token)
            result.append(new_token)
        else:
            result.append(token)

        pos = end

    result.append(line[pos:])
    return "".join(result)


def transpor_cifra(texto_cifra: str, semitones: int, target_key: Optional[str] = None) -> str:
    """Transpõe todas as linhas de acordes de uma cifra."""
    if semitones % 12 == 0:
        return texto_cifra
    use_flats = bool(target_key and target_key in FLAT_KEYS)
    output_lines = []
    for line in texto_cifra.splitlines():
        if is_chord_line(line):
            output_lines.append(transpor_linha_acordes(line, semitones, use_flats))
        else:
            output_lines.append(line)
    return "\n".join(output_lines)


# ---------------------------------------------------------------------------
# Limpeza Inteligente de Solo / Tablatura
# ---------------------------------------------------------------------------

# Linha típica de corda de tablatura: "E|---0-2---", "e|-----", "B|---3/5---", "G:|---"
TAB_STAFF_RE = re.compile(
    r"^\s*(?:[EADGBeadgb][#b]?|[1-6])?\s*[:|]\s*[-~0-9hHpPbBrRsS/\\xX()^.*|\s]{3,}\s*$"
)

# Linha de continuação/fechamento de tablatura sem letra de corda no início: "|---5-7---|"
TAB_CONTINUATION_RE = re.compile(
    r"^\s*\|[-~0-9hHpPbBrRsS/\\xX()^.*|\s]{3,}\|\s*$"
)

# Cabeçalhos explicitamente de tablatura/parte de solo
EXPLICIT_TAB_HEADER_RE = re.compile(
    r"^\s*(?:"
    r"\[(?:Tab|Tablatura|Riff|Solo\s*\d*)[^\]]*\]"
    r"|Tab\s*[-–:].*"
    r"|Parte\s+\d+\s+de\s+\d+"
    r"|(?:Solo|Riff|Tablatura)\s*:\s*$"
    r")\s*$",
    re.IGNORECASE,
)

# Cabeçalhos genéricos como [Intro], [Solo], [Ponte], [Final] que podem anteceder uma tablatura
SECTION_HEADER_ONLY_RE = re.compile(
    r"^\s*\[(?:Intro|Introdução|Solo|Riff|Interlúdio|Final|Outro|Dedilhado)[^\]]*\]\s*$",
    re.IGNORECASE,
)


def _is_tab_line(line: str) -> bool:
    """Identifica se uma linha pertence a um bloco de tablatura ASCII."""
    if TAB_STAFF_RE.match(line) or TAB_CONTINUATION_RE.match(line):
        # Garante que há traços típicos de tablatura para não confundir com compasso de acordes "| G | D |"
        return "-" in line
    return False


def remover_tablaturas(texto_cifra: str) -> str:
    """
    Remove blocos de tablatura ASCII e marcações exclusivas de solo/tab
    (ex: E|---, B|---, [Solo], Tab -, Parte 1 de 2), preservando
    perfeitamente o alinhamento dos acordes acima das sílabas da letra.
    """
    if not texto_cifra:
        return ""

    lines = texto_cifra.splitlines()
    n = len(lines)
    remove_mask = [False] * n

    # 1ª passagem: marca todas as linhas de tablatura ASCII e cabeçalhos explícitos de Tab
    for i, line in enumerate(lines):
        if _is_tab_line(line) or EXPLICIT_TAB_HEADER_RE.match(line):
            remove_mask[i] = True

    # 2ª passagem: remove cabeçalhos de seção (ex: [Intro], [Solo]) apenas quando
    # são seguidos diretamente (ignorando linhas em branco) por um bloco de tablatura removido,
    # sem acordes ou letras no meio.
    for i, line in enumerate(lines):
        if remove_mask[i]:
            continue
        if SECTION_HEADER_ONLY_RE.match(line):
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n and remove_mask[j]:
                remove_mask[i] = True

    # 3ª passagem: remove legendas auxiliares de tablatura (ex: "h = hammer-on", "p = pull-off")
    tab_legend_re = re.compile(
        r"^\s*(?:[hpbrs~/\\x]\s*[:=]\s*|Legenda\s*:).*(?:hammer|pull|slide|bend|vibrato|abafad)",
        re.IGNORECASE,
    )
    for i, line in enumerate(lines):
        if not remove_mask[i] and tab_legend_re.search(line):
            remove_mask[i] = True

    # Reconstrói preservando espaços iniciais/alinhamento das linhas mantidas
    kept_lines: list[str] = []
    blank_streak = 0
    for i, line in enumerate(lines):
        if remove_mask[i]:
            continue
        if not line.strip():
            blank_streak += 1
            if blank_streak <= 2:
                kept_lines.append("")
        else:
            blank_streak = 0
            kept_lines.append(line.rstrip())

    # Remove linhas vazias sobrando no início e no fim
    while kept_lines and not kept_lines[0]:
        kept_lines.pop(0)
    while kept_lines and not kept_lines[-1]:
        kept_lines.pop()

    return "\n".join(kept_lines)


# ---------------------------------------------------------------------------
# Motor de Busca e Scraping na Internet
# ---------------------------------------------------------------------------

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

PREFERRED_DOMAINS = (
    "losacordes.com",
    "cifraclub.com.br",
    "cifras.com.br",
    "bananacifras.com",
    "e-chords.com",
    "ciframelodica.com.br",
    "letras.mus.br",
)

EXCLUDED_DOMAINS = (
    "quarto.org",
    "wikipedia.org",
    "youtube.com",
    "dicio.com.br",
    "dicionarioinformal.com.br",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "olx.com.br",
    "pinterest.com",
    "madeiramadeira.com.br",
)


def _decode_bing_url(href: str) -> str:
    """Decodifica URLs de redirecionamento do Bing (parâmetro u=a1...)."""
    qs = parse_qs(urlparse(href).query)
    if "u" in qs and qs["u"][0].startswith("a1"):
        b64 = qs["u"][0][2:]
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        try:
            return base64.urlsafe_b64decode(b64).decode("utf-8", "ignore")
        except Exception:
            return href
    return href


def _search_bing_urls(query: str) -> list[str]:
    """Busca alternativa no Bing quando o DuckDuckGo não retorna resultados."""
    try:
        resp = requests.get(
            "https://www.bing.com/search",
            params={"q": query},
            headers=HTTP_HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        found: list[str] = []
        for a in soup.select("li.b_algo h2 a"):
            href = a.get("href") or ""
            if href:
                found.append(_decode_bing_url(href))
        return found
    except requests.RequestException:
        return []


def _search_candidate_urls(titulo: str, cantor: str) -> list[str]:
    """Busca URLs candidatas de cifras usando DuckDuckGo com fallback para Bing."""
    queries = [
        f"site:cifraclub.com.br {titulo} {cantor}",
        f"{titulo} {cantor} cifra",
    ]
    urls: list[str] = []
    seen: set[str] = set()

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(query, region="br-pt", max_results=6)
            except Exception:
                continue
            for item in results or []:
                href = item.get("href") or item.get("link") or ""
                if not href or href in seen:
                    continue
                seen.add(href)
                urls.append(href)

    # Fallback para Bing caso DuckDuckGo retorne vazio (ex: rate-limit 202)
    if not urls:
        for query in queries:
            for href in _search_bing_urls(query):
                if href and href not in seen:
                    seen.add(href)
                    urls.append(href)

    # Filtra domínios irrelevantes e prioriza domínios conhecidos de cifras
    filtered_urls = []
    for u in urls:
        host = urlparse(u).netloc.lower()
        if any(bad in host for bad in EXCLUDED_DOMAINS):
            continue
        filtered_urls.append(u)

    def domain_priority(url: str) -> int:
        host = urlparse(url).netloc.lower()
        for idx, dom in enumerate(PREFERRED_DOMAINS):
            if dom in host:
                return idx
        return len(PREFERRED_DOMAINS)

    filtered_urls.sort(key=domain_priority)
    return filtered_urls


def _extract_cifra_from_html(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    Extrai o conteúdo da tag <pre> (cifra) e o tom da página (quando disponível).
    Retorna (texto_cifra, tom_pagina).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Tenta capturar o tom explícito (padrão Cifra Club)
    tom_pagina: Optional[str] = None
    tom_el = (
        soup.select_one("#cifra_tom a")
        or soup.select_one("#cifra_tom")
        or soup.select_one(".cifra_tom a")
        or soup.select_one("[data-cy='cifra-tom']")
    )
    if tom_el:
        tom_pagina = normalize_key_name(tom_el.get_text(strip=True))

    # Prioriza <pre> dentro dos containers principais de cifra
    pre_candidates = (
        soup.select(".cifra_cnt pre")
        or soup.select("#cifra_cnt pre")
        or soup.find_all("pre")
    )

    best_text: Optional[str] = None
    for pre in pre_candidates:
        # Converte <br> explícitos em quebras de linha, se existirem
        for br in pre.find_all("br"):
            br.replace_with("\n")
        raw_text = pre.get_text()
        lines = [ln.rstrip() for ln in raw_text.splitlines()]
        cleaned = "\n".join(lines).strip("\n")

        # Validações estritas para garantir que é uma cifra e não código/tutorial/YAML
        if len(cleaned) < 40 or "\n" not in cleaned:
            continue

        # Rejeita blocos de código/YAML (ex: quarto.org, tutoriais de programação)
        lower_cleaned = cleaned.lower()
        if any(marker in lower_cleaned for marker in ("code-fold:", "observable plot", "fileattachment(", "plot.plot(")):
            continue

        # Verifica se o texto realmente contém acordes musicais válidos
        chords_found = extract_chords_from_text(cleaned)
        if len(chords_found) < 3:
            continue

        if best_text is None or len(cleaned) > len(best_text):
            best_text = cleaned

    return best_text, tom_pagina


def buscar_cifra_na_web(titulo: str, cantor: str) -> tuple[str, Optional[str], str]:
    """
    Pesquisa e faz scraping da cifra na web.
    Retorna (cifra_completa, tom_pagina, url_fonte).
    """
    urls = _search_candidate_urls(titulo, cantor)
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Não foram encontrados resultados na web para '{titulo} - {cantor}'. "
                "Você pode colar a cifra manualmente no campo 'Cifra Manual' para salvar."
            ),
        )

    saw_forbidden = False
    for url in urls[:8]:
        try:
            resp = requests.get(url, headers=HTTP_HEADERS, timeout=12)
            if resp.status_code == 403:
                saw_forbidden = True
                continue
            if resp.status_code != 200:
                continue
            cifra_text, tom_pagina = _extract_cifra_from_html(resp.text)
            if cifra_text:
                return cifra_text, tom_pagina, url
        except requests.RequestException:
            continue

    if saw_forbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"O site de cifras bloqueou o acesso automático (HTTP 403) para '{titulo} - {cantor}'. "
                "Copie a cifra no navegador e cole no campo 'Cifra Manual' para salvar normalmente."
            ),
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Não foi possível extrair a cifra automaticamente para '{titulo} - {cantor}'. "
            "Verifique o nome da música/artista ou cole a cifra no campo 'Cifra Manual'."
        ),
    )


# ---------------------------------------------------------------------------
# Endpoints REST
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    """Verifica status da API e conexão com o Neon.db."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 AS ok;")
                cur.fetchone()
        return {"status": "ok", "database": "connected"}
    except HTTPException as exc:
        return {"status": "error", "database": exc.detail}
    except Exception as exc:
        return {"status": "error", "database": str(exc)}


@app.post("/api/adicionar-musica", status_code=status.HTTP_201_CREATED)
def adicionar_musica(payload: AdicionarMusicaRequest):
    """
    Busca a cifra na internet, remove tablaturas para a versão limpa,
    detecta/transpõe o tom e salva ambos os formatos no Neon.db.
    """
    titulo = payload.titulo.strip()
    cantor = payload.cantor.strip()
    autor = payload.autor.strip() if payload.autor and payload.autor.strip() else None
    tom_usuario = normalize_key_name(payload.tom) if payload.tom and payload.tom.strip() else None

    if payload.tom and payload.tom.strip() and not tom_usuario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tom inválido: '{payload.tom}'. Use formatos como C, G, Am, F#m, Bb.",
        )

    # 1. Usa cifra manual se fornecida; caso contrário, busca automaticamente na internet
    if payload.cifra_manual and payload.cifra_manual.strip():
        cifra_bruta = "\n".join(ln.rstrip() for ln in payload.cifra_manual.splitlines()).strip("\n")
        tom_pagina = None
    else:
        cifra_bruta, tom_pagina, _url_fonte = buscar_cifra_na_web(titulo, cantor)

    # 2. Detecção do tom original
    tom_original = detectar_tom(cifra_bruta, tom_pagina)

    # 3. Transposição caso o usuário tenha informado um tom específico
    cifra_completa = cifra_bruta
    tom_final = tom_original

    if tom_usuario:
        orig_parsed = parse_key_semitone(tom_original)
        dest_parsed = parse_key_semitone(tom_usuario)
        if orig_parsed and dest_parsed:
            semitones = (dest_parsed[0] - orig_parsed[0]) % 12
            if semitones != 0:
                cifra_completa = transpor_cifra(cifra_bruta, semitones, target_key=tom_usuario)
        tom_final = tom_usuario

    # 4. Geração da versão limpa (sem tablaturas/solos)
    cifra_sem_solo = remover_tablaturas(cifra_completa)
    if not cifra_sem_solo.strip():
        cifra_sem_solo = cifra_completa

    # 5. Persistência no Neon.db (upsert seguro para evitar duplicação)
    insert_sql = """
    INSERT INTO musicas (titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo, exibir_solo)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (LOWER(TRIM(titulo)), LOWER(TRIM(cantor)))
    DO UPDATE SET
        autor = COALESCE(EXCLUDED.autor, musicas.autor),
        tom = EXCLUDED.tom,
        cifra_completa = EXCLUDED.cifra_completa,
        cifra_sem_solo = EXCLUDED.cifra_sem_solo,
        exibir_solo = EXCLUDED.exibir_solo
    RETURNING id, titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo, exibir_solo, created_at;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        titulo,
                        cantor,
                        autor,
                        tom_final,
                        cifra_completa,
                        cifra_sem_solo,
                        payload.com_solo,
                    ),
                )
                saved = cur.fetchone()
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar música no Neon.db: {exc}",
        )

    return dict(saved)


@app.get("/api/musicas")
def listar_musicas():
    """Retorna todas as músicas cadastradas no Neon.db ordenadas por título."""
    query = """
    SELECT id, titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo, exibir_solo, created_at
    FROM musicas
    ORDER BY LOWER(titulo) ASC, LOWER(cantor) ASC;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
        return [dict(row) for row in rows]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar músicas no Neon.db: {exc}",
        )


@app.put("/api/musicas/{musica_id}")
def atualizar_musica(musica_id: int, payload: AtualizarMusicaRequest):
    """Permite editar manualmente cifra, tom, autor, título ou preferência de solo."""
    updates: list[str] = []
    values: list[object] = []

    if payload.titulo is not None:
        updates.append("titulo = %s")
        values.append(payload.titulo.strip())
    if payload.cantor is not None:
        updates.append("cantor = %s")
        values.append(payload.cantor.strip())
    if payload.autor is not None:
        updates.append("autor = %s")
        values.append(payload.autor.strip() or None)
    if payload.tom is not None:
        norm_tom = normalize_key_name(payload.tom)
        if not norm_tom:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tom inválido: '{payload.tom}'.",
            )
        updates.append("tom = %s")
        values.append(norm_tom)
    if payload.cifra_completa is not None:
        updates.append("cifra_completa = %s")
        values.append(payload.cifra_completa)
        # Se a versão sem solo não foi enviada junto, recalcula automaticamente
        if payload.cifra_sem_solo is None:
            limpa = remover_tablaturas(payload.cifra_completa)
            updates.append("cifra_sem_solo = %s")
            values.append(limpa or payload.cifra_completa)
    if payload.cifra_sem_solo is not None:
        updates.append("cifra_sem_solo = %s")
        values.append(payload.cifra_sem_solo)
    if payload.exibir_solo is not None:
        updates.append("exibir_solo = %s")
        values.append(payload.exibir_solo)

    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhum campo informado para atualização.",
        )

    values.append(musica_id)
    update_sql = f"""
    UPDATE musicas
    SET {', '.join(updates)}
    WHERE id = %s
    RETURNING id, titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo, exibir_solo, created_at;
    """

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(update_sql, tuple(values))
                updated = cur.fetchone()
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao atualizar música: {exc}",
        )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Música com id={musica_id} não encontrada.",
        )
    return dict(updated)


@app.delete("/api/musicas/{musica_id}")
def excluir_musica(musica_id: int):
    """Exclui uma música do Neon.db pelo ID."""
    delete_sql = "DELETE FROM musicas WHERE id = %s RETURNING id, titulo;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (musica_id,))
                deleted = cur.fetchone()
            conn.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir música: {exc}",
        )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Música com id={musica_id} não encontrada.",
        )
    return {"deleted": True, "id": deleted["id"], "titulo": deleted["titulo"]}


# ---------------------------------------------------------------------------
# Endpoints de Pastas / Repertórios
# ---------------------------------------------------------------------------

@app.get("/api/pastas")
def listar_pastas():
    """Retorna todas as pastas cadastradas e os IDs das músicas contidas em cada uma."""
    query_pastas = """
    SELECT p.id, p.nome, p.cor, p.created_at,
           COALESCE(ARRAY_AGG(pm.musica_id ORDER BY pm.ordem, pm.musica_id) FILTER (WHERE pm.musica_id IS NOT NULL), '{}') AS musicas_ids
    FROM pastas p
    LEFT JOIN pasta_musicas pm ON p.id = pm.pasta_id
    GROUP BY p.id, p.nome, p.cor, p.created_at
    ORDER BY p.id ASC;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query_pastas)
                rows = cur.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar pastas: {exc}",
        )


@app.post("/api/pastas", status_code=status.HTTP_201_CREATED)
def criar_pasta(payload: CriarPastaRequest):
    """Cria uma nova pasta no Neon.db."""
    insert_sql = """
    INSERT INTO pastas (nome, cor)
    VALUES (%s, %s)
    RETURNING id, nome, cor, created_at;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(insert_sql, (payload.nome.strip(), payload.cor.strip()))
                nova = cur.fetchone()
            conn.commit()
        res = dict(nova)
        res["musicas_ids"] = []
        return res
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao criar pasta: {exc}",
        )


@app.delete("/api/pastas/{pasta_id}")
def excluir_pasta(pasta_id: int):
    """Exclui uma pasta (as músicas associadas continuam salvas na tabela musicas)."""
    sql = "DELETE FROM pastas WHERE id = %s RETURNING id, nome;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (pasta_id,))
                deleted = cur.fetchone()
            conn.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao excluir pasta: {exc}",
        )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pasta id={pasta_id} não encontrada.",
        )
    return {"deleted": True, "id": deleted["id"], "nome": deleted["nome"]}


@app.post("/api/pastas/{pasta_id}/musicas")
def adicionar_musica_na_pasta(pasta_id: int, payload: AdicionarMusicaPastaRequest):
    """Associa uma música a uma pasta."""
    sql = """
    INSERT INTO pasta_musicas (pasta_id, musica_id, ordem)
    VALUES (%s, %s, (SELECT COALESCE(MAX(ordem), 0) + 1 FROM pasta_musicas WHERE pasta_id = %s))
    ON CONFLICT (pasta_id, musica_id) DO NOTHING;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (pasta_id, payload.musica_id, pasta_id))
            conn.commit()
        return {"status": "ok", "pasta_id": pasta_id, "musica_id": payload.musica_id}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao adicionar música na pasta: {exc}",
        )


@app.delete("/api/pastas/{pasta_id}/musicas/{musica_id}")
def remover_musica_da_pasta(pasta_id: int, musica_id: int):
    """Remove a associação de uma música de dentro de uma pasta."""
    sql = "DELETE FROM pasta_musicas WHERE pasta_id = %s AND musica_id = %s RETURNING musica_id;"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (pasta_id, musica_id))
                removed = cur.fetchone()
            conn.commit()
        return {"removed": bool(removed), "pasta_id": pasta_id, "musica_id": musica_id}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao remover música da pasta: {exc}",
        )

