"""
03a_split_dwa_scores_by_year.py

OBJETIVO
--------
Convertir la matriz ancha de scores DWA (`detailed_work_activities_scores.gzip`,
un score por combinacion syllabus-id x Detailed Work Activity) a formato largo
y segmentarla en archivos anuales (skills_by_year/skills_<year>.csv).

CORRECCION CLAVE (respecto a 006.py original)
------------------------------------------------
El script original inferia el anio de cada syllabus con una expresion
regular sobre el propio `id` (`id.str.extract(r'(\\d{4})$')`), asumiendo que
el anio estaba codificado en los ultimos 4 digitos del identificador. Se
verifico contra la tabla de metadata real (`institution_fos_year.gzip`, que
SI trae una columna `year` correcta por syllabus) que este supuesto es falso:
por ejemplo el id 102000 pertenece en realidad al anio 2013 (no 2000), el id
102005 al anio 2003 (no 2005), y el id 102017 al anio 2002 (no 2017). Los ids
son simplemente correlativos, sin relacion con el anio.

El impacto medido: `skills_2000.csv` (version anterior) contenia solo 28 ids
unicos "anio 2000" fabricados por la regex, contra un universo real de 8,052
syllabi de 2000 -> 0% de solapamiento real. Esto invalidaba todo el pipeline
de medicion de frontera (03b), exposicion (04) y modelos de historia de
eventos (05), que dependen de un join id -> anio correcto.

Este script reemplaza esa logica por un merge explicito contra
`institution_fos_year.gzip` (columnas id, year), que tiene cobertura del
100% de los ids de la matriz de scores (281,153 de 281,153 verificado).

AUTOR: Roberto Cantillan Carrasco
FECHA: Junio 2026
"""
import pandas as pd
import os

RAW_SCORES_PATH = "data/raw/detailed_work_activities_scores.gzip"
META_PATH = "data/raw/institution_fos_year.gzip"
OUTPUT_DIR = "data/interim/skills_by_year"

YEAR_MIN, YEAR_MAX = 2000, 2017


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Cargando mapa id -> year real desde institution_fos_year.gzip...")
    id_year_map = pd.read_csv(META_PATH, compression="gzip", usecols=["id", "year"])
    id_year_map["id"] = id_year_map["id"].astype(str)
    id_year_map = id_year_map.drop_duplicates(subset="id").set_index("id")["year"]

    # Reiniciar archivos de salida para permitir escritura incremental limpia
    for y in range(YEAR_MIN, YEAR_MAX + 1):
        path = os.path.join(OUTPUT_DIR, f"skills_{y}.csv")
        if os.path.exists(path):
            os.remove(path)

    n_total_rows = 0
    n_unmatched_ids = set()
    chunk_size = 2000
    for chunk in pd.read_csv(RAW_SCORES_PATH, compression="gzip", chunksize=chunk_size):
        chunk.rename(columns={chunk.columns[0]: "id"}, inplace=True)
        chunk["id"] = chunk["id"].astype(str)

        chunk_long = chunk.melt(id_vars=["id"], var_name="skill", value_name="score")
        chunk_long = chunk_long[chunk_long["score"] > 0]

        # Asignar el anio REAL via merge contra la metadata de syllabi,
        # en vez de parsearlo del id.
        chunk_long["year"] = chunk_long["id"].map(id_year_map)

        unmatched = chunk_long[chunk_long["year"].isna()]["id"].unique()
        n_unmatched_ids.update(unmatched)
        chunk_long = chunk_long.dropna(subset=["year"])
        chunk_long["year"] = chunk_long["year"].astype(int)
        chunk_long = chunk_long[chunk_long["year"].between(YEAR_MIN, YEAR_MAX)]

        for year, group in chunk_long.groupby("year"):
            csv_path = os.path.join(OUTPUT_DIR, f"skills_{year}.csv")
            header = not os.path.exists(csv_path)
            group[["id", "skill", "score"]].to_csv(csv_path, mode="a", index=False, header=header)
            n_total_rows += len(group)

    print(f"Filas escritas en total: {n_total_rows:,}")
    print(f"Ids sin match en metadata (deberian ser 0): {len(n_unmatched_ids)}")
    print(f"Segmentacion temporal completada. Archivos anuales en: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
