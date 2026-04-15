import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        # Lê a chave que você colou no Secrets
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'chamador-amesaude.appspot.com' 
        })
    except Exception as e:
        st.error(f"Erro na chave de segurança: {e}")

db = firestore.client()
bucket = storage.bucket()

# --- INTERFACE ---
st.set_page_config(page_title="AME - Sistema de Comprovantes", layout="wide")
st.title("🏥 AME - Gestão de Comprovantes Online")

aba_recepcao, aba_financeiro = st.tabs(["📥 Recepção (Envio)", "🔍 Financeiro (Consulta)"])

with aba_recepcao:
    st.subheader("Registrar Novo Pagamento")
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente")
        valor = st.number_input("Valor Recebido (R$)", min_value=0.0, format="%.2f")
        arquivo = st.file_uploader("Anexe a foto do comprovante", type=["png", "jpg", "jpeg", "pdf"])
        obs = st.text_area("Observações")
        
        enviado = st.form_submit_button("Enviar para o Financeiro")
        
        if enviado:
            if cliente and valor > 0 and arquivo:
                try:
                    # 1. Salvar arquivo no Storage
                    nome_arquivo = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cliente}.jpg"
                    blob = bucket.blob(f"comprovantes/{nome_arquivo}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    url_foto = blob.public_url
                    
                    # 2. Salvar dados no Firestore
                    db.collection("pagamentos").add({
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "cliente": cliente,
                        "valor": valor,
                        "url_foto": url_foto,
                        "status": "Pendente",
                        "obs": obs
                    })
                    st.success(f"✅ Sucesso! O pagamento de {cliente} foi registrado.")
                except Exception as e:
                    st.error(f"Erro ao enviar: {e}")
            else:
                st.warning("⚠️ Preencha o nome, valor e anexe o arquivo.")

with aba_financeiro:
    st.subheader("Painel de Consulta")
    if st.button("🔄 Atualizar Lista"):
        docs = db.collection("pagamentos").stream()
        lista = [doc.to_dict() for doc in docs]
        if lista:
            df = pd.DataFrame(lista)
            st.dataframe(df, column_config={
                "url_foto": st.column_config.LinkColumn("Ver Foto")
            })
        else:
            st.info("Nenhum registro encontrado.")
