import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Função para conectar na Planilha que eu criei para você
def conecta_planilha():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Aqui usamos as 'secrets' do Streamlit para não precisar do arquivo .json solto
    import json
    creds_dict = json.loads(st.secrets["textkey"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("Controle de Comprovantes e Notas Fiscais - AME").sheet1

st.set_page_config(page_title="Financeiro AME", page_icon="💰")
st.title("🏥 AME - Sistema de Comprovantes")

# Interface do Caixa
with st.form("form_caixa", clear_on_submit=True):
    st.subheader("Registrar Novo Pagamento")
    cliente = st.text_input("Nome da Empresa ou Cliente")
    valor = st.number_input("Valor Recebido (R$)", min_value=0.0, format="%.2f")
    obs = st.text_area("Observações")
    
    enviado = st.form_submit_button("Enviar para o Financeiro")
    
    if enviado:
        if cliente and valor > 0:
            try:
                sheet = conecta_planilha()
                data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
                sheet.append_row([data_hoje, cliente, valor, "Anexado no sistema", "Pendente", obs])
                st.success(f"O pagamento de {cliente} foi registrado na planilha!")
            except Exception as e:
                st.error("Erro de conexão. Verifique as credenciais.")
        else:
            st.warning("Preencha o nome e o valor.")
