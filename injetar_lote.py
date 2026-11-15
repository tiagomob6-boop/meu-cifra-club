import os
import re
import psycopg2
from bs4 import BeautifulSoup

# =========================================================================
# COLE SUA CONNECTION STRING DO NEON.DB ABAIXO:
# =========================================================================
NEON_DATABASE_URL = "postgresql://neondb_owner:npg_dJQ0Z3rKctvs@ep-little-brook-b6n36s4u-pooler.c-2.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
}

# Lista com as 13 músicas e suas URLs diretas: (Titulo, Cantor, Autor, URL)
MUSICAS_DIRETAS = [
    ("Boate Azul", "Bruno & Marrone", "Benedito Seviero / Tomaz", "https://www.cifraclub.com.br/bruno-e-marrone/boate-azul/"),
    ("Largado às Traças", "Zé Neto & Cristiano", "André Vox / Philipe Pancadinha / Victor Hugo", "https://www.cifraclub.com.br/ze-neto-e-cristiano/largado-as-tracas/"),
    ("Cuida Bem Dela", "Henrique & Juliano", "Marília Mendonça / Juliano Tchula / Daniel Rangel / Maraisa", "https://www.cifraclub.com.br/henrique-e-juliano/cuida-bem-dela/"),
    ("Cheiro de Culpado", "Gusttavo Lima", "Thallys Pacheco / Denner Ferrari / Felipe Goffi / Jimmy Luzzo", "https://www.cifraclub.com.br/gusttavo-lima/cheiro-de-culpado/"),
    ("Vou Ter Que Superar", "Matheus & Kauan (part. Marília Mendonça)", "Matheus Aleixo / Thales Lessa / Waléria Leão / Blener Maycom", "https://www.cifraclub.com.br/matheus-e-kauan/vou-ter-que-superar/"),
    ("Eu Era", "Marcos & Belutti", "Léo Targino / Carlos Dias / Rodrigo Reys / Thiago Teg", "https://www.cifraclub.com.br/marcos-e-belutti/eu-era/"),
    ("Pensa em Mim", "Leandro & Leonardo", "Douglas Maio / José Ribeiro / Mário Soares", "https://www.cifraclub.com.br/leandro-e-leonardo/pensa-em-mim/"),
    ("Na Hora da Raiva", "Henrique & Juliano", "Cinara Sousa / Gustavo Moura / Rafael Moura / Matheus Costa", "https://www.cifraclub.com.br/henrique-e-juliano/na-hora-da-raiva/"),
    ("Isso Cê Não Conta", "Bruno & Marrone", "Celi Junior / Douglas Mello / Flavinho Tinto / Nando Marx", "https://www.cifraclub.com.br/bruno-e-marrone/isso-ce-nao-conta/"),
    ("Pós", "Diego & Victor Hugo", None, "https://www.cifraclub.com.br/diego-e-victor-hugo/pos/"),
    ("Postinho de Gasolina", "Thales Lessa", None, "https://www.cifraclub.com.br/thales-lessa/postinho-de-gasolina/"),
    ("Medo Bobo", "Maiara & Maraisa", "Juliano Tchula / Maraisa / Vinicius Poeta / Benício Neto / Junior Pepato", "https://www.cifraclub.com.br/maiara-e-maraisa/medo-bobo/"),
    ("Nova York", "Chrystian & Ralf", "Chrystian / Ralf", "https://www.cifraclub.com.br/chrystian-e-ralf/nova-york/"),
]


def remover_tablaturas(texto: str) -> str:
    """Remove linhas de tablatura ASCII (E|---, B|---, etc.) e cabeçalhos de solo."""
    linhas_limpas = []
    # Padrão típico de cordas de tablatura: e|---, B|---, G|---, D|---, A|---, E|---, Eb|---
    padrao_tab = re.compile(r"^\s*[A-Ga-g][#b]?\s*\|[-0-9hHpPbBrRsS/\\~xX()\s|]+\s*$")
    padrao_header_solo = re.compile(r"^\s*(\[?(Solo|Tab|Intro\s*-\s*Solo|Parte\s+\d+\s+de\s+\d+)\]?:?)\s*$", re.IGNORECASE)

    for linha in texto.splitlines():
        if padrao_tab.match(linha):
            continue
        if padrao_header_solo.match(linha):
            continue
        linhas_limpas.append(linha)

    # Limpa excesso de linhas em branco seguidas (máximo 2)
    resultado = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas_limpas))
    return resultado.strip()


def detectar_tom(soup: BeautifulSoup, cifra_texto: str) -> str:
    """Captura o tom oficial da página ou o primeiro acorde válido."""
    tom_el = soup.find(id="cifra_tom")
    if tom_el and tom_el.get_text(strip=True):
        return tom_el.get_text(strip=True)

    match_acorde = re.search(r"\b([A-G][#b]?m?)\b", cifra_texto)
    return match_acorde.group(1) if match_acorde else "G"


def garantir_tabela(conn):
    """Garante que a tabela musicas existe com todas as colunas esperadas."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS musicas (
                id SERIAL PRIMARY KEY,
                titulo VARCHAR(150) NOT NULL,
                cantor VARCHAR(150) NOT NULL,
                autor VARCHAR(150),
                tom VARCHAR(15) NOT NULL DEFAULT 'G',
                cifra_completa TEXT NOT NULL,
                cifra_sem_solo TEXT NOT NULL,
                exibir_solo BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
    conn.commit()


def slug_from_url(url: str) -> str:
    """Extrai o nome do arquivo .txt a partir da URL (ex: boate-azul.txt)."""
    partes = [p for p in url.strip("/").split("/") if p]
    return f"{partes[-1]}.txt" if partes else "musica.txt"


def importar_de_arquivo_e_salvar(conn, titulo: str, cantor: str, autor: str | None, url: str, pasta_txt: str):
    nome_arquivo = slug_from_url(url)
    caminho = os.path.join(pasta_txt, nome_arquivo)

    if not os.path.exists(caminho):
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("")
        return "⏭️ Criado vazio (cole a cifra no .txt)", None, nome_arquivo

    with open(caminho, "r", encoding="utf-8") as f:
        cifra_completa = f.read().strip()

    if not cifra_completa:
        return "⏭️ Aguardando cifra no .txt", None, nome_arquivo

    cifra_sem_solo = remover_tablaturas(cifra_completa)
    if not cifra_sem_solo:
        cifra_sem_solo = cifra_completa

    # Detecta o tom pelo primeiro acorde válido (ou padrão G)
    match_acorde = re.search(r"\b([A-G][#b]?m?)\b", cifra_sem_solo)
    tom = match_acorde.group(1) if match_acorde else "G"

    with conn.cursor() as cur:
        # Busca por título para atualizar também quando o cantor/intérprete for ajustado
        cur.execute(
            "SELECT id FROM musicas WHERE LOWER(titulo) = LOWER(%s)",
            (titulo,),
        )
        existente = cur.fetchone()

        if existente:
            cur.execute(
                """
                UPDATE musicas
                SET cantor = %s, autor = %s, tom = %s, cifra_completa = %s, cifra_sem_solo = %s, exibir_solo = FALSE
                WHERE id = %s
                """,
                (cantor, autor, tom, cifra_completa, cifra_sem_solo, existente[0]),
            )
            status = "🔄 Atualizada"
        else:
            cur.execute(
                """
                INSERT INTO musicas (titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo, exibir_solo)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """,
                (titulo, cantor, autor, tom, cifra_completa, cifra_sem_solo),
            )
            status = "✅ Inserida"

    conn.commit()
    return status, tom, nome_arquivo


def main():
    if "SEU_USUARIO" in NEON_DATABASE_URL:
        print("⚠️ Cole sua NEON_DATABASE_URL válida na linha 11 antes de executar!")
        return

    pasta_txt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cifras_txt")
    os.makedirs(pasta_txt, exist_ok=True)

    print("🔌 Conectando ao Neon.db...")
    conn = psycopg2.connect(NEON_DATABASE_URL)
    garantir_tabela(conn)

    total = len(MUSICAS_DIRETAS)
    print(f"📂 Lendo cifras da pasta '{pasta_txt}' ({total} músicas configuradas)...\n")

    importadas = 0
    pendentes = 0
    try:
        for idx, (titulo, cantor, autor, url) in enumerate(MUSICAS_DIRETAS, start=1):
            try:
                status, tom, nome_arq = importar_de_arquivo_e_salvar(conn, titulo, cantor, autor, url, pasta_txt)
                if tom:
                    importadas += 1
                    print(f"[{idx}/{total}] {status}: {titulo} - {cantor} [Tom: {tom}] ({nome_arq})")
                else:
                    pendentes += 1
                    print(f"[{idx}/{total}] {status}: {nome_arq} -> {url}")
            except Exception as e:
                print(f"[{idx}/{total}] ❌ Erro em '{titulo}': {e}")
    finally:
        conn.close()
        print(f"\n🏁 Concluído! Importadas/Atualizadas: {importadas} | Pendentes (cole nos .txt): {pendentes}")
        print("Dê um F5 na sua página HTML para ver todas as músicas carregadas.")


if __name__ == "__main__":
    main()