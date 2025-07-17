import pandas as pd
NUMERO_DE_QUARTOS = 10; DIARIA_PADRAO = 150.00
quartos = [{'Numero': f'{100 + i}', 'Status': 'Disponível', 'HospedeCPF': '', 'ValorDiaria': DIARIA_PADRAO + (i * 5)} for i in range(1, NUMERO_DE_QUARTOS + 1)]
pd.DataFrame(quartos).to_excel('quartos.xlsx', index=False)
print("Arquivo 'quartos.xlsx' recriado com sucesso!")