import pandas as pd
colunas = ['Nome', 'CPF', 'Telefone', 'Email', 'CheckIn', 'HoraCheckIn', 'CheckOut', 'HoraCheckOut', 'Quarto', 'StatusHospedagem']
pd.DataFrame(columns=colunas).to_excel('hospedes.xlsx', index=False)
print("Arquivo 'hospedes.xlsx' recriado com sucesso!")