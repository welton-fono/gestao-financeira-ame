import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        # Puxa a chave dos Secrets do Streamlit
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        
        # Inicializa o app com o link EXATO do Firebase atual
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'chamdor-amesaude.firebasestorage.app'
        })
    except Exception as e:
        st.error(f"Erro na conexão com o Firebase: {e}")

db = firestore.client()
bucket = storage.bucket()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Gestão de Arquivos", layout="wide", page_icon="🏥")
st.title("🏥 AME - Sistema de Comprovantes e Documentos")

aba_envio, aba_busca = st.tabs(["📥 Enviar Arquivo", "🔍 Painel do Financeiro"])

with aba_envio:
    st.subheader("Upload de Documentos")
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente").upper()
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        arquivo = st.file_uploader("Selecione o arquivo (PDF, Word, Imagem, etc.)")
        obs = st.text_area("Observações Adicionais")
        enviado = st.form_submit_button("Enviar para o Sistema")
        
        if enviado:
            if cliente and arquivo:
                try:
                    extensao = arquivo.name.split('.')[-1].lower()
                    nome_arq = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{cliente}.{extensao}"
                    
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    db.collection("pagamentos").add({
                        "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                        "cliente": cliente,
                        "valor": valor,
                        "url": blob.public_url,
                        "tipo": extensao,
                        "nome_original": arquivo.name,
                        "obs": obs
                    })
                    st.success(f"✅ Arquivo .{extensao.upper()} enviado com sucesso!")
                except Exception as e:
                    st.error(f"Erro no envio: {e}")
            else:
                st.warning("⚠️ Preencha o nome do cliente e anexe um arquivo.")

with aba_busca:
    st.subheader("Visualização e Acesso Rápido")
    
    col_busca, col_refresh = st.columns([4, 1])
    with col_busca:
        busca = st.text_input("🔍 Pesquisar por Cliente:").upper()
    with col_refresh:
        if st.button("🔄 Atualizar Lista"):
            st.rerun()

    try:
        docs = db.collection("pagamentos").order_by("data", direction="DESCENDING").stream()
        dados = [doc.to_dict() for doc in docs]
        
        if dados:
            df = pd.DataFrame(dados)
            if busca:
                df = df[df['cliente'].str.contains(busca, case=False)]
            
            for i, row in df.iterrows():
                icon = "🖼️" if row['tipo'] in ['png', 'jpg', 'jpeg'] else "📄"
                if row['tipo'] == 'pdf': icon = "📕"
                
                with st.expander(f"{icon} {row['cliente']} | R$ {row['valor']} | {row['data']}"):
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.write(f"**Obs:** {row['obs']}")
                        st.link_button("🚀 Abrir Documento", row['url'])
                    with c2:
                        if row['tipo'] in ['png', 'jpg', 'jpeg']:
                            st.image(row['url'], use_container_width=True)
                        else:
                            st.info(f"Arquivo .{row['tipo'].upper()} pronto para abrir.")
        else:
            st.info("Nenhum documento encontrado.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
