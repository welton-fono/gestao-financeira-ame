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
            # Este é o nome que aparece na sua imagem
            'storageBucket': 'chamdor-amesaude.appspot.com' 
        })
    except Exception as e:
        st.error(f"Erro na chave: {e}")

db = firestore.client()
bucket = storage.bucket()

st.set_page_config(page_title="AME - Financeiro", layout="wide")
st.title("🏥 AME - Gestão de Comprovantes Online")

aba_envio, aba_busca = st.tabs(["📥 Recepção (Envio)", "🔍 Financeiro (Consulta)"])

with aba_envio:
    st.subheader("Registrar Novo Pagamento")
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente")
        valor = st.number_input("Valor Recebido (R$)", min_value=0.0, format="%.2f")
        arquivo = st.file_uploader("Anexe a foto do comprovante", type=["png", "jpg", "jpeg"])
        obs = st.text_area("Observações")
        
        if st.form_submit_button("Enviar para o Financeiro"):
            if cliente and arquivo:
                try:
                    nome_arq = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cliente}.jpg"
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    db.collection("pagamentos").add({
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "cliente": cliente.upper(),
                        "valor": valor,
                        "url": blob.public_url,
                        "obs": obs
                    })
                    st.success("✅ Enviado com sucesso!")
                except Exception as e:
                    st.error(f"Erro ao enviar: {e}")

with aba_busca:
    st.subheader("Painel de Visualização Rápida")
    
    # Busca dados
    docs = db.collection("pagamentos").order_by("data", direction="DESCENDING").stream()
    dados = [doc.to_dict() for doc in docs]
    
    if dados:
        df = pd.DataFrame(dados)
        
        # Filtro de busca
        busca = st.text_input("🔍 Digite o nome da empresa para filtrar:")
        if busca:
            df = df[df['cliente'].str.contains(busca.upper(), case=False)]
        
        # Exibição em CARDS para ver a foto direto na tela
        for i, row in df.iterrows():
            with st.expander(f"📄 {row['cliente']} - R$ {row['valor']} ({row['data']})"):
                col1, col2 = st.columns([1, 2])
                with col1:
                    st.write(f"**Data:** {row['data']}")
                    st.write(f"**Valor:** R$ {row['valor']}")
                    st.write(f"**Obs:** {row['obs']}")
                with col2:
                    # MOSTRA A FOTO DIRETO NA TELA
                    st.image(row['url'], caption=f"Comprovante {row['cliente']}", use_container_width=True)
    else:
        st.info("Nenhum registro encontrado.")
