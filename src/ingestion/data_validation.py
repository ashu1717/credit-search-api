import pandas as pd

df = pd.read_parquet('/Users/ashutoshpatel/Documents/Workspace/Netwitt/Project/data/processed/ingested.parquet')

print(df.shape)
print(df.head)
print(df.columns.tolist())

print("Shape:", df.shape)
print("Columns:", df.columns.tolist())
print(df.head())
