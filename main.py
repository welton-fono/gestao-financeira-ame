import streamlit as st
import pandas as pd
from datetime import datetime
import json
import firebase_admin
from firebase_admin import credentials, firestore, storage

# --- CONFIGURAÇÃO DO FIREBASE ---
# Verifica se o app já foi iniciado para não dar erro de duplicidade
if not firebase_admin._apps:
    creds_dict = json.loads(st.secrets["firebase_key"])
    cred = credentials.Certificate(creds_dict)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'chamador-amesaude.appspot.com' 
    })

db = firestore.client()
bucket = storage.bucket()

# --- INTERFACE ---
st.set_page_config(page_title="Financeiro AME", page_icon="💰", layout="wide")
st.title("🏥 AME - Sistema de Comprovantes Online")

aba_recepcao, aba_financeiro = st.tabs(["📥 Recepção (Envio)", "🔍 Financeiro (Consulta)"])

with aba_recepcao:
    st.subheader("Registrar Novo Pagamento")
    # O form ajuda a limpar os campos após o envio
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente")
        valor = st.number_input("Valor Recebido (R$)", min_value=0.0, format="%.2f")
        
        # AQUI ESTÁ O CAMPO QUE FALTAVA:
        arquivo = st.file_uploader("Anexe a foto ou PDF do comprovante", type=["png", "jpg", "jpeg", "pdf"])
        
        obs = st.text_area("Observações (Ex: Referente a quais exames?)")
        
        enviado = st.form_submit_button("Enviar para o Financeiro")
        
        if enviado:
            if cliente and valor > 0 and arquivo:
                try:
                    # 1. Enviar a foto para o Firebase Storage
                    nome_arquivo = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cliente}.jpg"
                    blob = bucket.blob(f"comprovantes/{nome_arquivo}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    
                    # Torna o link da foto público para o financeiro conseguir abrir
                    blob.make_public()
                    url_foto = blob.public_url
                    
                    # 2. Salvar os dados e o link da foto no Firestore
                    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
                    db.collection("pagamentos").add({
                        "data": data_hoje,
                        "cliente": cliente,
                        "valor": valor,
                        "comprovante_url": url_foto,
                        "status": "Pendente",
                        "observacoes": obs
                    })
                    
                    st.success(f"✅ Sucesso! O comprovante de {cliente} foi enviado.")
                except Exception as e:
                    st.error(f"Erro ao enviar: {e}")
            else:
                st.warning("⚠️ Por favor, preencha o nome, o valor e anexe o arquivo.")

with aba_financeiro:
    st.subheader("Painel de Consulta")
    if st.button("🔄 Atualizar Lista"):
        # Busca os dados do Firebase
        docs = db.collection("pagamentos").order_by("data", direction="DESCENDING").stream()
        lista_pagamentos = [doc.to_dict() for doc in docs]
        
        if lista_pagamentos:
            df = pd.DataFrame(lista_pagamentos)
            
            # Filtro de busca por nome
            busca = st.text_input("Filtrar por nome do cliente")
            if busca:
                df = df[df['cliente'].str.contains(busca, case=False)]
            
            # Exibe a tabela com o link clicável para a foto
            st.dataframe(df, column_config={
                "comprovante_url": st.column_config.LinkColumn("Ver Foto")
            })
        else:
            st.info("Nenhum pagamento registrado ainda.")
