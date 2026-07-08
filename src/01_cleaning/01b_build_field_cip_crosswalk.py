"""
01b_build_field_cip_crosswalk.py

OBJETIVO
--------
Construir un crosswalk real entre las 62 categorias `field_name`/`field_code`
del Course-Skill Atlas y los codigos CIP de 2 digitos usados por el archivo
de graduados IPEDS (`cipcode`).

CORRECCION CLAVE (respecto a 02_panel_construction.R original)
----------------------------------------------------------------
El script anterior mezclaba `skills_dt` (nivel syllabus, con `field_name`)
y `panel_inst` (nivel graduados IPEDS, con `cipcode`) mediante un join
`on = .(unitid, year)` con `allow.cartesian = TRUE`, SIN ninguna llave de
campo de estudio en comun. Esto generaba un producto cartesiano: cada
syllabus de una institucion-anio se multiplicaba por las ~41 filas de
graduados de esa institucion-anio (una por cada cipcode), emparejando por
ejemplo un syllabus de "Medicine" con graduados de "Agriculture". La celda
"institucion x campo x anio" que el proyecto define como unidad de analisis
no existia realmente en el panel resultante.

Este script resuelve el problema construyendo una llave `cip2` (familia CIP
de 2 digitos) a partir de `field_code`, para poder unir Atlas <-> IPEDS por
(unitid, year, cip2) en vez de solo (unitid, year).

LOGICA DE PARSEO
-----------------
`field_code` es una lista de codigos CIP separados por "/", por ejemplo:
  "51.00/51.01/.../51.99"  -> familia dominante 51
  "23"                      -> familia 23
  "32.0101/32.0104/.../53" -> mezcla 32 y 53 (familia MIXTA)

Para cada field_code se extraen los primeros 2 digitos de cada token (antes
del punto). Si todos los tokens comparten la misma familia de 2 digitos, el
crosswalk queda "limpio" (cip2 unico). Si hay mas de una familia presente
(ambiguo), se asigna la familia MODAL (la mas frecuente entre los tokens) y
se marca `is_ambiguous = True` para que puedan excluirse en un chequeo de
robustez.

AUTOR: Roberto Cantillan Carrasco
FECHA: Junio 2026
"""
import pandas as pd
import re
from collections import Counter

RAW_PATH = "data/raw/institution_fos_year.gzip"
OUT_PATH = "data/interim/field_cip_crosswalk.csv"


def parse_cip2_families(field_code: str):
    tokens = [t.strip() for t in str(field_code).split("/") if t.strip()]
    families = []
    for t in tokens:
        m = re.match(r"(\d{2})", t)
        if m:
            families.append(m.group(1))
    return families


def build_crosswalk(fields: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in fields.iterrows():
        families = parse_cip2_families(r["field_code"])
        if not families:
            rows.append({
                "field_name": r["field_name"],
                "field_code": r["field_code"],
                "cip2": None,
                "is_ambiguous": True,
                "n_distinct_families": 0,
            })
            continue
        counts = Counter(families)
        modal_family, modal_n = counts.most_common(1)[0]
        rows.append({
            "field_name": r["field_name"],
            "field_code": r["field_code"],
            "cip2": modal_family,
            "is_ambiguous": len(counts) > 1,
            "n_distinct_families": len(counts),
        })
    return pd.DataFrame(rows)


def main():
    fields = pd.read_csv(RAW_PATH, compression="gzip", usecols=["field_name", "field_code"]).drop_duplicates()
    crosswalk = build_crosswalk(fields).sort_values("field_name").reset_index(drop=True)

    n_ambiguous = crosswalk["is_ambiguous"].sum()
    print(f"Categorias field_name totales: {len(crosswalk)}")
    print(f"Categorias con familia CIP ambigua (>1 familia de 2 digitos): {n_ambiguous}")
    if n_ambiguous:
        print(crosswalk[crosswalk["is_ambiguous"]][["field_name", "field_code", "cip2"]].to_string(index=False))

    crosswalk.to_csv(OUT_PATH, index=False)
    print(f"Crosswalk guardado en: {OUT_PATH}")


if __name__ == "__main__":
    main()
