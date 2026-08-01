import math

# def csv_colunm_foramt(val):
#     if str(val).find("$") >= 0:
#         return float(val.replace("$", "").replace(",", ""))
#     if str(val).find("¥") >= 0:
#         return float(val.replace("¥", "").replace(",", ""))
#     return val
import pandas as pd


def csv_colunm_foramt(val):
    try:
        if pd.isna(val):
            return math.nan
        if str(val).find("$") >= 0:
            return float(val.replace("$", "").replace(",", ""))
        if str(val).find("¥") >= 0:
            return float(val.replace("¥", "").replace(",", ""))
        return val
    except ValueError:
        return val


def clean_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize messy Excel/CSV object columns before handing the df to DuckDB.

    DuckDB infers object-column types from sampled values; a stray
    whitespace-only or numeric-as-text cell in a numeric column then
    fails the scan with a cast error (e.g. "Could not convert string
    ' ' to INT32"). Strip strings, turn blank strings into NULL, and
    promote columns whose non-null values are all numeric-like so
    numeric columns stay computable. Columns containing real text are
    left untouched (no silent coercion to NaN).
    """
    for col in df.columns:
        if df[col].dtype != object:
            continue
        series = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)
        series = series.map(lambda v: None if isinstance(v, str) and not v else v)
        numeric = pd.to_numeric(series, errors="coerce")
        if series.isna().equals(numeric.isna()):
            # Coercion introduced no new NaN: every non-null value is numeric.
            series = numeric
        df[col] = series
    return df
