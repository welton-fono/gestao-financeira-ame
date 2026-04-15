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
            # Note: é chamdor (sem o 'a' no meio)
            'storageBucket': 'chamdor-amesaude.firebasestorage.app' 
        })
    except Exception as e:
        st.error(f"Erro na chave: {e}")

db = firestore.client()
bucket = storage.bucket()

st.set_page_config(page_title="AME - Gestão de Arquivos", layout="wide", page_icon="🏥")
st.title("🏥 AME - Sistema de Comprovantes e Documentos")

aba_envio, aba_busca = st.tabs(["📥 Enviar Arquivo", "🔍 Painel do Financeiro"])

with aba_envio:
    st.subheader("Upload de Documentos")
    with st.form("form_caixa", clear_on_submit=True):
        cliente = st.text_input("Nome da Empresa ou Cliente").upper()
        valor = st.number_input("Valor (R$)", min_value=0.0, format="%.2f")
        
        # ACEITA QUALQUER TIPO DE ARQUIVO
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
        busca = st.text_input("🔍 Pesquisar por Cliente/Empresa:").upper()
    with col_refresh:
        atualizar = st.button("🔄 Atualizar Lista")

    if atualizar or busca or "primeira_carga" not in st.session_state:
        st.session_state["primeira_carga"] = True
        docs = db.collection("pagamentos").order_by("data", direction="DESCENDING").stream()
        dados = [doc.to_dict() for doc in docs]
        
        if dados:
            df = pd.DataFrame(dados)
            if busca:
                df = df[df['cliente'].str.contains(busca, case=False)]
            
            for i, row in df.iterrows():
                # Define o ícone baseado no tipo
                icon = "🖼️" if row['tipo'] in ['png', 'jpg', 'jpeg'] else "📄"
                if row['tipo'] == 'pdf': icon = "📕"
                if row['tipo'] in ['doc', 'docx']: icon = "📘"
                
                with st.expander(f"{icon} {row['cliente']} | R$ {row['valor']} | Data: {row['data']}"):
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.info(f"**Tipo de Arquivo:** .{row['tipo'].upper()}")
                        st.write(f"**Observações:** {row['obs']}")
                        st.write(f"**Arquivo original:** {row.get('nome_original', 'N/A')}")
                        st.link_button("🚀 Abrir Documento / Ver em Tela Cheia", row['url'])
                    
                    with c2:
                        # Se for imagem, mostra o preview na hora
                        if row['tipo'] in ['png', 'jpg', 'jpeg']:
                            st.image(row['url'], caption="Visualização da Imagem", use_container_width=True)
                        else:
                            st.warning(f"Este é um arquivo {row['tipo'].upper()}. Clique no botão azul ao lado para visualizar ou baixar.")
        else:
            st.info("Nenhum documento encontrado.")
