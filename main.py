import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'chamdor-amesaude.appspot.com' 
        })
    except Exception as e:
        st.error(f"Erro na chave de segurança: {e}")

db = firestore.client()
bucket = storage.bucket()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro", layout="wide", page_icon="🏥")
st.title("🏥 AME - Gestão de Comprovantes Online")

aba_envio, aba_busca = st.tabs(["📥 Recepção (Envio)", "🔍 Financeiro (Consulta)"])

with aba_envio:
    st.subheader("Registrar Novo Pagamento")
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente")
        valor = st.number_input("Valor Recebido (R$)", min_value=0.0, format="%.2f")
        arquivo = st.file_uploader("Anexe a foto do comprovante", type=["png", "jpg", "jpeg"])
        obs = st.text_area("Observações")
        
        enviado = st.form_submit_button("Enviar para o Financeiro")
        
        if enviado:
            if cliente and arquivo and valor > 0:
                try:
                    # 1. Upload da Foto
                    nome_arq = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cliente}.jpg"
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    # 2. Salvar no Banco de Dados
                    db.collection("pagamentos").add({
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "cliente": cliente.upper(),
                        "valor": valor,
                        "url": blob.public_url,
                        "status": "Pendente",
                        "obs": obs
                    })
                    st.success(f"✅ Sucesso! Pagamento de {cliente} registrado.")
                except Exception as e:
                    st.error(f"Erro ao enviar arquivo: {e}")
            else:
                st.warning("⚠️ Preencha o nome, valor e anexe a foto.")

with aba_busca:
    st.subheader("Painel do Financeiro (Visualização Rápida)")
    
    if st.button("🔄 Atualizar e Buscar Dados"):
        docs = db.collection("pagamentos").order_by("data", direction="DESCENDING").stream()
        dados = [doc.to_dict() for doc in docs]
        
        if dados:
            df = pd.DataFrame(dados)
            
            # Barra de busca para o financeiro achar rápido
            busca = st.text_input("🔍 Buscar por nome do cliente:")
            if busca:
                df = df[df['cliente'].str.contains(busca.upper(), case=False)]
            
            # Exibe os comprovantes em cards expansíveis
            for i, row in df.iterrows():
                with st.expander(f"📄 {row['cliente']} - R$ {row['valor']} ({row['data']})"):
                    col1, col2 = st.columns([1, 1])
                    with col1:
                        st.write(f"**Status:** {row['status']}")
                        st.write(f"**Observação:** {row['obs']}")
                        st.link_button("Abrir imagem em tela cheia", row['url'])
                    with col2:
                        st.image(row['url'], width=300)
        else:
            st.info("Nenhum registro encontrado no banco de dados.")
