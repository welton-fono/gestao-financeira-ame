import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz # Biblioteca para Fuso Horário

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro PRO", layout="wide", page_icon="🏥")

# --- CSS PARA DESIGN PROFISSIONAL ---
st.markdown("""
    <style>
    .stMetric {background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0;}
    .stExpander {border: 1px solid #d1d1d1; border-radius: 8px; margin-bottom: 10px;}
    .main {background-color: #f9f9f9;}
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'chamdor-amesaude.firebasestorage.app'
        })
    except Exception as e:
        st.error(f"Erro na conexão: {e}")

db = firestore.client()
bucket = storage.bucket()
fuso_br = pytz.timezone('America/Sao_Paulo') # Configura Brasília

# --- CABEÇALHO ---
st.title("🏥 AME Saúde - Gestão de Documentos Profissional")
st.markdown(f"**Horário Atual (Brasília):** {datetime.now(fuso_br).strftime('%d/%m/%Y %H:%M')}")
st.divider()

aba_envio, aba_busca = st.tabs(["📥 Enviar Novo Comprovante", "📊 Painel do Financeiro"])

with aba_envio:
    st.subheader("Registrar Documento")
    with st.form("form_caixa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("🏢 Empresa/Cliente").upper()
            cnpj = st.text_input("📑 CNPJ da Empresa")
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
        with col2:
            funcionario = st.text_input("👤 Nome do Funcionário (Exame)")
            arquivo = st.file_uploader("📎 Anexar Comprovante (PDF, Imagem)")
            obs = st.text_area("📝 Observações", height=68)
        
        enviado = st.form_submit_button("🚀 SALVAR REGISTRO", use_container_width=True)
        
        if enviado:
            if cliente and arquivo and cnpj and funcionario:
                try:
                    ext = arquivo.name.split('.')[-1].lower()
                    agora = datetime.now(fuso_br)
                    # Nome do arquivo no storage
                    nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{cliente}.{ext}"
                    
                    # Upload Storage
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    # Salva no Firestore
                    db.collection("pagamentos").add({
                        "data_completa": agora.strftime("%Y/%m/%d %H:%M:%S"),
                        "dia": agora.strftime("%d/%m/%Y"),
                        "hora": agora.strftime("%H:%M"),
                        "mes_ano": agora.strftime("%m/%Y"),
                        "cliente": cliente,
                        "cnpj": cnpj,
                        "funcionario": funcionario,
                        "valor": valor,
                        "url": blob.public_url,
                        "nome_storage": nome_arq, # Guardamos para poder deletar depois
                        "tipo": ext,
                        "obs": obs
                    })
                    st.success(f"✅ Registro de {cliente} salvo com sucesso em {agora.strftime('%H:%M')}!")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("⚠️ Todos os campos e o arquivo são obrigatórios.")

with aba_busca:
    st.subheader("Painel de Controle Financeiro")
    
    # Filtros e Atualização
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        busca = st.text_input("🔍 Buscar por Empresa ou Funcionário:").upper()
    with c2:
        mes_atual = datetime.now(fuso_br).strftime("%m/%Y")
        mes_filtro = st.text_input("📅 Mês/Ano (Ex: 04/2026)", value=mes_atual)
    with c3:
        st.write("") # Alinhamento
        if st.button("🔄 Atualizar Lista", use_container_width=True):
            st.rerun()

    try:
        # Busca com ID para permitir deleção
        query = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING")
        docs = query.stream()
        
        lista_dados = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id # Pega o ID único do documento
            lista_dados.append(d)
        
        if lista_dados:
            df = pd.DataFrame(lista_dados)
            
            # Filtros
            if busca:
                df = df[(df['cliente'].str.contains(busca)) | (df['funcionario'].str.contains(busca))]
            if mes_filtro:
                df = df[df['mes_ano'] == mes_filtro]
            
            # Dashboard simples
            if not df.empty:
                t1, t2 = st.columns(2)
                t1.metric("💰 Total Valor", f"R$ {df['valor'].sum():,.2f}")
                t2.metric("📄 Total Registros", f"{len(df)} docs")
                st.divider()

                for i, row in df.iterrows():
                    icon = "📕" if row['tipo'] == 'pdf' else "🖼️"
                    label = f"{icon} {row['cliente']} | {row['funcionario']} | R$ {row['valor']:.2f} ({row['dia']})"
                    
                    with st.expander(label):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**🏢 Empresa:** {row['cliente']} (CNPJ: {row['cnpj']})")
                            st.write(f"**👤 Funcionário:** {row['funcionario']}")
                            st.write(f"**⏰ Horário do Registro:** {row['hora']}")
                            st.write(f"**📝 Obs:** {row['obs']}")
                            st.link_button("📂 Abrir Arquivo", row['url'])
                            
                            # BOTÃO DE EXCLUSÃO
                            if st.button(f"🗑️ Deletar Registro", key=f"del_{row['id']}"):
                                try:
                                    # 1. Deleta do Storage (Se o nome existir)
                                    if 'nome_storage' in row:
                                        bucket.blob(f"comprovantes/{row['nome_storage']}").delete()
                                    # 2. Deleta do Firestore
                                    db.collection("pagamentos").document(row['id']).delete()
                                    st.success("Registro apagado!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"Erro ao deletar: {err}")

                        with col_b:
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url'], use_container_width=True)
                            else:
                                st.info("Preview indisponível para PDF/Word.")
            else:
                st.info("Nenhum registro encontrado para este filtro.")
        else:
            st.info("O sistema ainda não possui registros.")
            
    except Exception as e:
        st.error(f"Erro ao carregar painel: {e}")
