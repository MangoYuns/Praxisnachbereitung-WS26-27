import pandas as pd

df = pd.read_excel("excel/Aufgaben.xlsx", sheet_name="Gesamt")
print(df.shape)
print(df.to_string())