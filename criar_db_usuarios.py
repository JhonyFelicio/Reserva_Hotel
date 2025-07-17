import pandas as pd
from werkzeug.security import generate_password_hash

# --- CONFIGURE SEU PRIMEIRO USUÁRIO AQUI ---
primeiro_usuario = 'admin'
primeira_senha = 'admin' # Mude para uma senha forte em produção

# Gera o hash seguro da senha
senha_hash = generate_password_hash(primeira_senha)

# Cria o DataFrame com os dados, incluindo a nova coluna 'Role'
usuarios_db = pd.DataFrame([{
    'Usuario': primeiro_usuario,
    'SenhaHash': senha_hash,
    'Role': 'admin'  # Define a função do usuário como 'admin'
}])

# Salva no arquivo Excel
usuarios_db.to_excel('usuarios.xlsx', index=False)

print(f"Arquivo 'usuarios.xlsx' criado/atualizado com sucesso!")
print(f"Usuário '{primeiro_usuario}' cadastrado com a função de 'admin'.")