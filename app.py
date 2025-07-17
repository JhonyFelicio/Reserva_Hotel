import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime, timedelta
import os
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash
import json

app = Flask(__name__)
app.secret_key = 'versao_final_estavel_e_segura'

DB_HOSPEDES = 'hospedes.xlsx';
DB_QUARTOS = 'quartos.xlsx';
DB_USUARIOS = 'usuarios.xlsx'
DB_ATIVIDADES = 'atividades.xlsx';
DB_CAIXA = 'fluxo_caixa.xlsx'


def carregar_db(arquivo, dtypes=None):
    if os.path.exists(arquivo): return pd.read_excel(arquivo, dtype=dtypes)
    if arquivo == DB_HOSPEDES: return pd.DataFrame(
        columns=['Nome', 'CPF', 'Telefone', 'Email', 'CheckIn', 'HoraCheckIn', 'CheckOut', 'HoraCheckOut', 'Quarto',
                 'StatusHospedagem'])
    if arquivo == DB_QUARTOS: return pd.DataFrame(columns=['Numero', 'Status', 'HospedeCPF', 'ValorDiaria'])
    if arquivo == DB_USUARIOS: return pd.DataFrame(columns=['Usuario', 'SenhaHash', 'Role'])
    if arquivo == DB_ATIVIDADES: return pd.DataFrame(columns=['Timestamp', 'Usuario', 'Acao', 'Detalhes'])
    if arquivo == DB_CAIXA: return pd.DataFrame(
        columns=['DataCheckout', 'Hospede', 'CPF', 'Quarto', 'DiasHospedado', 'ValorDiaria', 'ValorTotal'])
    return pd.DataFrame()


def log_activity(usuario, acao, detalhes):
    df_atividades = carregar_db(DB_ATIVIDADES)
    nova_atividade = pd.DataFrame(
        [{'Timestamp': datetime.now().strftime('%d-%m-%Y %H:%M:%S'), 'Usuario': usuario, 'Acao': acao,
          'Detalhes': detalhes}])
    df_atividades = pd.concat([df_atividades, nova_atividade], ignore_index=True);
    df_atividades.to_excel(DB_ATIVIDADES, index=False)


def verifica_conflito_de_datas(quarto, checkin_novo, checkout_novo, id_reserva_editada=None):
    df_reservas = carregar_db(DB_HOSPEDES, dtypes={'Quarto': str})
    if df_reservas.empty: return False
    checkin_novo, checkout_novo = datetime.strptime(checkin_novo, '%Y-%m-%d'), datetime.strptime(checkout_novo,
                                                                                                 '%Y-%m-%d')
    reservas_do_quarto = df_reservas[df_reservas['Quarto'] == quarto]
    if id_reserva_editada is not None: reservas_do_quarto = reservas_do_quarto.drop(index=id_reserva_editada,
                                                                                    errors='ignore')
    for index, reserva in reservas_do_quarto.iterrows():
        checkin_existente, checkout_existente = datetime.strptime(reserva['CheckIn'], '%d-%m-%Y'), datetime.strptime(
            reserva['CheckOut'], '%d-%m-%Y')
        if (checkin_novo < checkout_existente) and (checkout_novo > checkin_existente): return True
    return False


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: flash("Por favor, faça login para acessar esta página.",
                                             "error"); return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin': flash("Acesso negado. Você não tem permissão para acessar esta página.",
                                                 "error"); return redirect(url_for('index'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'logged_in' in session: return redirect(url_for('index'))
    if request.method == 'POST':
        df_usuarios, usuario_form, senha_form = carregar_db(DB_USUARIOS), request.form['username'], request.form[
            'password']
        usuario_db = df_usuarios[df_usuarios['Usuario'].str.lower() == usuario_form.lower()]
        if not usuario_db.empty and check_password_hash(usuario_db.iloc[0]['SenhaHash'], senha_form):
            session['logged_in'], session['username'], session['role'] = True, usuario_db.iloc[0]['Usuario'], \
            usuario_db.iloc[0]['Role']
            log_activity(session['username'], 'Login', 'Usuário realizou login no sistema.');
            flash("Login realizado com sucesso!", "success");
            return redirect(url_for('index'))
        flash("Usuário ou senha inválidos.", "error")
    return render_template('login.html')


@app.route('/logout')
def logout():
    log_activity(session.get('username', 'Desconhecido'), 'Logout', 'Usuário saiu do sistema.')
    session.clear();
    flash("Você saiu do sistema.", "info");
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    df_hospedes, df_quartos, df_caixa = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str}).fillna(
        ''), carregar_db(DB_QUARTOS, dtypes={'Numero': str, 'HospedeCPF': str}).fillna(''), carregar_db(DB_CAIXA)
    resumo_mensal = []
    if not df_caixa.empty and 'DataCheckout' in df_caixa.columns:
        df_caixa['DataCheckout'] = pd.to_datetime(df_caixa['DataCheckout'], format='%d-%m-%Y', errors='coerce').dropna()
        if not df_caixa.empty:
            faturamento = df_caixa.groupby(pd.Grouper(key='DataCheckout', freq='M'))['ValorTotal'].sum().reset_index()
            faturamento['Mes'] = faturamento['DataCheckout'].dt.strftime('%B/%Y').str.capitalize();
            resumo_mensal = faturamento[['Mes', 'ValorTotal']].to_dict('records')
    return render_template('index.html', hospedes=df_hospedes.to_dict('records'), quartos=df_quartos.to_dict('records'),
                           resumo_mensal=resumo_mensal, hoje_str=datetime.now().strftime('%d-%m-%Y'))


@app.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar():
    if request.method == 'POST':
        quarto_selecionado, checkin_str, checkout_str = request.form['quarto'], request.form['checkin_date'], \
        request.form['checkout_date']
        if verifica_conflito_de_datas(quarto_selecionado, checkin_str, checkout_str):
            flash(
                f"ERRO: O quarto {quarto_selecionado} já está reservado no período selecionado. A reserva não foi salva.",
                'error');
            return redirect(url_for('adicionar'))
        df_hospedes, cpf_submetido = carregar_db(DB_HOSPEDES, dtypes={'CPF': str}), request.form['cpf'].strip()
        novo_hospede = {'Nome': request.form['nome'], 'CPF': cpf_submetido, 'Telefone': request.form['telefone'],
                        'Email': request.form['email'],
                        'CheckIn': datetime.strptime(checkin_str, '%Y-%m-%d').strftime('%d-%m-%Y'),
                        'HoraCheckIn': request.form['checkin_time'],
                        'CheckOut': datetime.strptime(checkout_str, '%Y-%m-%d').strftime('%d-%m-%Y'),
                        'HoraCheckOut': request.form['checkout_time'], 'Quarto': quarto_selecionado,
                        'StatusHospedagem': 'Agendado'}
        df_hospedes = pd.concat([df_hospedes, pd.DataFrame([novo_hospede])], ignore_index=True)
        df_hospedes.to_excel(DB_HOSPEDES, index=False)
        log_activity(session['username'], 'Agendamento',
                     f"Hóspede: {novo_hospede['Nome']} (CPF: {cpf_submetido}) agendado no quarto {quarto_selecionado}.")
        flash(f"Reserva para '{novo_hospede['Nome']}' criada com sucesso!", 'success');
        return redirect(url_for('index'))

    df_quartos, df_reservas = carregar_db(DB_QUARTOS, dtypes={'Numero': str}), carregar_db(DB_HOSPEDES,
                                                                                           dtypes={'Quarto': str})
    quartos_ja_reservados = []
    if not df_reservas.empty: quartos_ja_reservados = df_reservas['Quarto'].unique().tolist()
    quartos_disponiveis = df_quartos[~df_quartos['Numero'].isin(quartos_ja_reservados)]['Numero'].tolist()
    return render_template('adicionar.html', hoje=datetime.now().strftime('%Y-%m-%d'),
                           quartos_disponiveis=quartos_disponiveis)


@app.route('/confirmar_hospedagem/<int:hospede_id>')
@login_required
def confirmar_hospedagem(hospede_id):
    df_hospedes, df_quartos = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str}), carregar_db(DB_QUARTOS,
                                                                                                        dtypes={
                                                                                                            'Numero': str})
    hospede = df_hospedes.loc[hospede_id]
    df_hospedes.loc[hospede_id, 'StatusHospedagem'] = 'Hospedado';
    df_quartos.loc[df_quartos['Numero'] == str(hospede['Quarto']), 'Status'] = 'Ocupado'
    df_quartos.loc[df_quartos['Numero'] == str(hospede['Quarto']), 'HospedeCPF'] = hospede['CPF']
    df_hospedes.to_excel(DB_HOSPEDES, index=False);
    df_quartos.to_excel(DB_QUARTOS, index=False)
    log_activity(session['username'], 'Confirmação Check-In',
                 f"Hóspede: {hospede['Nome']} (Quarto: {hospede['Quarto']}) confirmado como 'Hospedado'.")
    flash(f"Hóspede '{hospede['Nome']}' confirmado como 'Hospedado'!", 'success');
    return redirect(url_for('index'))


@app.route('/gerenciar_reserva/<int:hospede_id>')
@login_required
def gerenciar_reserva(hospede_id):
    df_hospedes = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str});
    hospede = df_hospedes.loc[hospede_id].to_dict()
    return render_template('gerenciar_reserva.html', hospede=hospede, hospede_id=hospede_id)


@app.route('/cancelar_reserva/<int:hospede_id>', methods=['POST'])
@login_required
def cancelar_reserva(hospede_id):
    df_hospedes, df_quartos = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str}), carregar_db(DB_QUARTOS,
                                                                                                        dtypes={
                                                                                                            'Numero': str})
    hospede, observacao = df_hospedes.loc[hospede_id], request.form.get('observacao')
    if hospede['StatusHospedagem'] == 'Hospedado': df_quartos.loc[
        df_quartos['Numero'] == str(hospede['Quarto']), ['Status', 'HospedeCPF']] = ['Disponível',
                                                                                     '']; df_quartos.to_excel(
        DB_QUARTOS, index=False)
    df_hospedes = df_hospedes.drop(df_hospedes.index[hospede_id]).reset_index(drop=True);
    df_hospedes.to_excel(DB_HOSPEDES, index=False)
    log_activity(session['username'], 'Cancelamento',
                 f"Reserva do hóspede {hospede['Nome']} (Quarto: {hospede['Quarto']}) cancelada. Motivo: {observacao}")
    flash(f"Reserva de '{hospede['Nome']}' foi cancelada com sucesso!", 'success');
    return redirect(url_for('index'))


@app.route('/editar_reserva/<int:hospede_id>', methods=['GET', 'POST'])
@login_required
def editar_reserva(hospede_id):
    df_hospedes = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str})
    if hospede_id >= len(df_hospedes): flash("Reserva não encontrada.", "error"); return redirect(url_for('index'))
    hospede_original = df_hospedes.loc[hospede_id].to_dict()
    if request.method == 'POST':
        checkin_str, checkout_str, quarto = request.form['checkin_date'], request.form['checkout_date'], \
        hospede_original['Quarto']
        if verifica_conflito_de_datas(quarto, checkin_str, checkout_str, id_reserva_editada=hospede_id):
            flash(f"ERRO: A nova data conflita com outra reserva para o quarto {quarto}. A edição não foi salva.",
                  'error');
            return redirect(url_for('editar_reserva', hospede_id=hospede_id))
        dados_novos = {'Nome': request.form['nome'], 'CPF': request.form['cpf'], 'Telefone': request.form['telefone'],
                       'Email': request.form['email'],
                       'CheckIn': datetime.strptime(checkin_str, '%Y-%m-%d').strftime('%d-%m-%Y'),
                       'HoraCheckIn': request.form['checkin_time'],
                       'CheckOut': datetime.strptime(checkout_str, '%Y-%m-%d').strftime('%d-%m-%Y'),
                       'HoraCheckOut': request.form['checkout_time'], 'Quarto': quarto,
                       'StatusHospedagem': hospede_original['StatusHospedagem']}
        for chave, valor in dados_novos.items(): df_hospedes.loc[hospede_id, chave] = valor
        df_hospedes.to_excel(DB_HOSPEDES, index=False)
        log_activity(session['username'], 'Edição de Reserva',
                     f"Reserva do hóspede {hospede_original['Nome']} foi alterada.");
        flash(f"Reserva de '{hospede_original['Nome']}' atualizada com sucesso!", 'success');
        return redirect(url_for('index'))

    # ### CORREÇÃO: Lógica do JSON removida ###
    # Apenas passa os dados do hóspede e a data de hoje.
    return render_template('editar_reserva.html', hospede=hospede_original, hospede_id=hospede_id,
                           hoje=datetime.now().strftime('%Y-%m-%d'))


@app.route('/checkout/<int:hospede_id>')
@login_required
def checkout(hospede_id):
    df_hospedes, df_quartos = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str}), carregar_db(DB_QUARTOS,
                                                                                                        dtypes={
                                                                                                            'Numero': str,
                                                                                                            'ValorDiaria': float})
    if hospede_id >= len(df_hospedes): flash("Hóspede não encontrado.", "error"); return redirect(url_for('index'))
    hospede, quarto_info_df = df_hospedes.loc[hospede_id], df_quartos[
        df_quartos['Numero'] == str(df_hospedes.loc[hospede_id, 'Quarto'])]
    if quarto_info_df.empty: flash(f"Erro: Quarto {hospede['Quarto']} não encontrado.", "error"); return redirect(
        url_for('index'))
    quarto_info = quarto_info_df.iloc[0]
    try:
        checkin, checkout = datetime.strptime(hospede['CheckIn'], '%d-%m-%Y'), datetime.strptime(hospede['CheckOut'],
                                                                                                 '%d-%m-%Y')
        dias_hospedado = (checkout - checkin).days;
        dias_hospedado = 1 if dias_hospedado <= 0 else dias_hospedado
    except (ValueError, TypeError):
        dias_hospedado = 0
    return render_template('checkout.html', hospede=hospede, hospede_id=hospede_id, quarto=quarto_info,
                           dias=dias_hospedado, total=dias_hospedado * quarto_info['ValorDiaria'])


@app.route('/finalizar_checkout/<int:hospede_id>', methods=['POST'])
@login_required
def finalizar_checkout(hospede_id):
    df_hospedes = carregar_db(DB_HOSPEDES, dtypes={'CPF': str, 'Quarto': str})
    if hospede_id >= len(df_hospedes): flash("Hóspede não encontrado.", "error"); return redirect(url_for('index'))
    hospede = df_hospedes.loc[hospede_id]
    quarto_a_liberar, dias_hospedado, valor_diaria, valor_total = str(
        request.form.get('quarto_numero')), request.form.get('dias_hospedado', type=int), request.form.get(
        'valor_diaria', type=float), request.form.get('valor_total', type=float)
    df_caixa = pd.concat([carregar_db(DB_CAIXA), pd.DataFrame(
        [{'DataCheckout': hospede['CheckOut'], 'Hospede': hospede['Nome'], 'CPF': hospede['CPF'],
          'Quarto': quarto_a_liberar, 'DiasHospedado': dias_hospedado, 'ValorDiaria': valor_diaria,
          'ValorTotal': valor_total}])], ignore_index=True)
    df_caixa.to_excel(DB_CAIXA, index=False)
    df_quartos = carregar_db(DB_QUARTOS, dtypes={'Numero': str});
    df_quartos.loc[df_quartos['Numero'] == quarto_a_liberar, ['Status', 'HospedeCPF']] = ['Disponível', ''];
    df_quartos.to_excel(DB_QUARTOS, index=False)
    nome_hospede = hospede['Nome'];
    df_hospedes = df_hospedes.drop(df_hospedes.index[hospede_id]).reset_index(drop=True);
    df_hospedes.to_excel(DB_HOSPEDES, index=False)
    log_activity(session['username'], 'Check-Out',
                 f"Hóspede: {nome_hospede} (Quarto: {quarto_a_liberar}). Faturamento: R$ {valor_total:.2f}")
    flash(f"Check-out de '{nome_hospede}' finalizado! Valor de R$ {valor_total:,.2f} registrado.", 'success');
    return redirect(url_for('index'))


# ... (O restante das rotas de admin permanecem iguais)
@app.route('/gerenciar_usuarios', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_usuarios():
    if request.method == 'POST':
        df_usuarios, usuario_novo, senha_nova = carregar_db(DB_USUARIOS), request.form['username'], request.form[
            'password']
        if not df_usuarios.empty and (df_usuarios['Usuario'].str.lower() == usuario_novo.lower()).any():
            flash(f"Erro: O nome de usuário '{usuario_novo}' já existe!", 'error')
        else:
            df_usuarios = pd.concat([df_usuarios, pd.DataFrame(
                [{'Usuario': usuario_novo, 'SenhaHash': generate_password_hash(senha_nova), 'Role': 'comum'}])],
                                    ignore_index=True)
            df_usuarios.to_excel(DB_USUARIOS, index=False);
            log_activity(session['username'], 'Criação de Usuário', f"Novo usuário '{usuario_novo}' foi criado.")
            flash(f"Usuário '{usuario_novo}' criado com sucesso!", 'success')
        return redirect(url_for('gerenciar_usuarios'))
    return render_template('gerenciar_usuarios.html', usuarios=carregar_db(DB_USUARIOS).to_dict('records'))


@app.route('/editar_senha/<username>', methods=['POST'])
@login_required
@admin_required
def editar_senha(username):
    df_usuarios, nova_senha = carregar_db(DB_USUARIOS), request.form.get('new_password')
    idx_usuario = df_usuarios.index[df_usuarios['Usuario'] == username].tolist()
    if idx_usuario:
        df_usuarios.loc[idx_usuario[0], 'SenhaHash'] = generate_password_hash(nova_senha);
        df_usuarios.to_excel(DB_USUARIOS, index=False)
        log_activity(session['username'], 'Alteração de Senha', f"A senha do usuário '{username}' foi alterada.")
        flash(f"Senha do usuário '{username}' alterada com sucesso.", 'success')
    return redirect(url_for('gerenciar_usuarios'))


@app.route('/excluir_usuario/<username>')
@login_required
@admin_required
def excluir_usuario(username):
    if username == 'admin':
        flash("Ação não permitida: o usuário 'admin' não pode ser excluído.", 'error')
    elif username == session['username']:
        flash("Ação não permitida: você não pode excluir a si mesmo.", 'error')
    else:
        df_usuarios = carregar_db(DB_USUARIOS);
        df_usuarios = df_usuarios[df_usuarios['Usuario'] != username]
        df_usuarios.to_excel(DB_USUARIOS, index=False);
        log_activity(session['username'], 'Exclusão de Usuário', f"O usuário '{username}' foi excluído.")
        flash(f"Usuário '{username}' excluído com sucesso.", 'success')
    return redirect(url_for('gerenciar_usuarios'))


@app.route('/consultar_atividades', methods=['GET', 'POST'])
@login_required
@admin_required
def consultar_atividades():
    df_atividades = carregar_db(DB_ATIVIDADES).sort_values(by='Timestamp', ascending=False)
    acoes_disponiveis = []
    if not df_atividades.empty: acoes_disponiveis = sorted(df_atividades['Acao'].unique().tolist())
    data_selecionada, acoes_selecionadas, atividades_filtradas = '', [], df_atividades
    if request.method == 'POST':
        data_selecionada, acoes_selecionadas = request.form.get('data_consulta'), request.form.getlist('acoes')
        if data_selecionada:
            data_formatada = datetime.strptime(data_selecionada, '%Y-%m-%d').strftime('%d-%m-%Y')
            atividades_filtradas['Data'] = pd.to_datetime(atividades_filtradas['Timestamp'],
                                                          format='%d-%m-%Y %H:%M:%S').dt.strftime('%d-%m-%Y')
            atividades_filtradas = atividades_filtradas[atividades_filtradas['Data'] == data_formatada]
        if acoes_selecionadas: atividades_filtradas = atividades_filtradas[
            atividades_filtradas['Acao'].isin(acoes_selecionadas)]
    return render_template('consultar_atividades.html', atividades=atividades_filtradas.to_dict('records'),
                           data_selecionada=data_selecionada, acoes_disponiveis=acoes_disponiveis,
                           acoes_selecionadas=acoes_selecionadas)


@app.route('/gerenciar_quartos', methods=['GET', 'POST'])
@login_required
@admin_required
def gerenciar_quartos():
    if request.method == 'POST':
        df_quartos = carregar_db(DB_QUARTOS, dtypes={'Numero': str});
        alteracoes = []
        for index, row in df_quartos.iterrows():
            nova_diaria_str = request.form.get(f"diaria_{row['Numero']}")
            if nova_diaria_str:
                try:
                    nova_diaria, diaria_antiga = float(nova_diaria_str), row['ValorDiaria']
                    if nova_diaria != diaria_antiga: df_quartos.loc[
                        index, 'ValorDiaria'] = nova_diaria; alteracoes.append(
                        f"Quarto {row['Numero']}: R${diaria_antiga:.2f} -> R${nova_diaria:.2f}")
                except (ValueError, TypeError):
                    continue
        if alteracoes:
            df_quartos.to_excel(DB_QUARTOS, index=False); log_activity(session['username'], 'Alteração de Diárias',
                                                                       "; ".join(alteracoes)); flash(
                "Valores das diárias atualizados com sucesso!", 'success')
        else:
            flash("Nenhum valor foi alterado.", 'info')
        return redirect(url_for('gerenciar_quartos'))
    return render_template('gerenciar_quartos.html',
                           quartos=carregar_db(DB_QUARTOS, dtypes={'Numero': str}).to_dict('records'))


if __name__ == '__main__':
    app.run(debug=True)