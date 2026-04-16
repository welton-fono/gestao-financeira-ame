import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Gestão de Comprovantes", layout="wide", page_icon="🏥")

# --- CSS PARA LAYOUT PROFISSIONAL ---
st.markdown("""
    <style>
    /* Letras maiores para melhor visibilidade */
    html, body, [class*="View"] { font-size: 19px !important; }
    
    /* Letreiro Digital AME */
    .logo-ame {
        font-size: 65px;
        font-weight: 900;
        color: #008f39;
        letter-spacing: 2px;
        margin-bottom: -15px;
        text-align: left;
    }
    .sub-logo {
        font-size: 20px;
        color: #444;
        font-weight: 600;
        margin-bottom: 30px;
        text-align: left;
    }
    
    /* Estilo dos cards (métricas) */
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border: 1px solid #eee;
    }
    
    /* Botão de salvar maior e destacado */
    .stButton>button {
        height: 3em;
        font-size: 20px !important;
        font-weight: bold !important;
        background-color: #008f39 !important;
        color: white !important;
        border-radius: 10px;
    }
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
fuso_br = pytz.timezone('America/Sao_Paulo')

# --- CABEÇALHO ---
st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">Assistência Médica Especializada</div>', unsafe_allow_html=True)
st.divider()

# --- NAVEGAÇÃO ---
aba_envio, aba_financeiro = st.tabs(["📥 ENVIAR COMPROVANTE", "🔍 PAINEL DO FINANCEIRO"])

with aba_envio:
    st.subheader("Registrar Novo Documento")
    
    # Formulário de Envio
    with st.form("form_ame", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            empresa = st.text_input("🏢 Nome da Empresa/Cliente").upper()
            cnpj = st.text_input("📑 CNPJ da Empresa")
            valor = st.number_input("💰 Valor do Exame (R$)", min_value=0.0, format="%.2f")
        with col2:
            funcionario = st.text_input("👤 Nome do Funcionário")
            arquivo = st.file_uploader("📎 Selecione o Comprovante (PDF ou Imagem)")
            obs = st.text_area("📝 Observações extras")
            
        botao_enviar = st.form_submit_button("🚀 SALVAR REGISTRO NO SISTEMA", use_container_width=True)

        if botao_enviar:
            if empresa and arquivo and cnpj and funcionario:
                try:
                    # Preparar arquivo
                    ext = arquivo.name.split('.')[-1].lower()
                    agora = datetime.now(fuso_br)
                    nome_arquivo = f"{agora.strftime('%Y%m%d_%H%M%S')}_{empresa}.{ext}"
                    
                    # Subir para o Storage
                    blob = bucket.blob(f"comprovantes/{nome_arquivo}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    # Salvar dados no Banco
                    db.collection("pagamentos").add({
                        "data_ordenacao": agora.strftime("%Y/%m/%d %H:%M:%S"),
                        "data_formatada": agora.strftime("%d/%m/%Y"),
                        "hora": agora.strftime("%H:%M"),
                        "mes_referencia": agora.strftime("%m/%Y"),
                        "empresa": empresa,
                        "cnpj": cnpj,
                        "funcionario": funcionario,
                        "valor": valor,
                        "url_arquivo": blob.public_url,
                        "nome_original": nome_arquivo,
                        "tipo": ext,
                        "obs": obs
                    })
                    
                    # --- NOTIFICAÇÃO DE CHEGADA ---
                    st.balloons() # Efeito visual de comemoração
                    st.toast(f"✅ RECEBIDO: {empresa} - {funcionario}", icon='🔔')
                    st.success(f"### ✨ REGISTRO SALVO COM SUCESSO!\n**Empresa:** {empresa} | **Funcionário:** {funcionario}")
                    time.sleep(2)
                    st.rerun() # Atualiza a tela para limpar o formulário
                except Exception as e:
                    st.error(f"Erro ao enviar: {e}")
            else:
                st.warning("⚠️ Atenção: Todos os campos são obrigatórios!")

with aba_financeiro:
    st.subheader("Histórico de Documentos Recebidos")
    
    # Barra de pesquisa e filtro
    c1, c2 = st.columns([3, 1])
    with c1:
        pesquisa = st.text_input("🔍 Pesquisar por Empresa ou Funcionário:").upper()
    with c2:
        if st.button("🔄 Atualizar Lista", use_container_width=True):
            st.rerun()

    try:
        # Puxar dados do Firebase
        docs = db.collection("pagamentos").order_by("data_ordenacao", direction="DESCENDING").stream()
        lista_dados = []
        for doc in docs:
            item = doc.to_dict()
            item['id'] = doc.id
            lista_dados.append(item)
            
        if lista_dados:
            df = pd.DataFrame(lista_dados)
            
            # Filtro de pesquisa
            if pesquisa:
                df = df[(df['empresa'].str.contains(pesquisa)) | (df['funcionario'].str.contains(pesquisa))]
            
            if not df.empty:
                # Métricas do topo
                m1, m2 = st.columns(2)
                m1.metric("💰 Total em Comprovantes", f"R$ {df['valor'].sum():,.2f}")
                m2.metric("📄 Total de Arquivos", f"{len(df)} registros")
                st.divider()

                # Lista de Expanders (Comprovantes)
                for i, row in df.iterrows():
                    cor_icone = "📕" if row['tipo'] == 'pdf' else "🖼️"
                    titulo = f"{cor_icone} {row['empresa']} | {row['funcionario']} | R$ {row['valor']:.2f}"
                    
                    with st.expander(titulo):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**📑 CNPJ:** {row['cnpj']}")
                            st.write(f"**📅 Data do Envio:** {row['data_formatada']} às {row['hora']}")
                            st.write(f"**📝 Observações:** {row.get('obs', 'Nenhuma')}")
                            st.link_button("📂 ABRIR COMPROVANTE ORIGINAL", row['url_arquivo'])
                            
                            st.write("---")
                            # Botão de Deletar
                            if st.button(f"🗑️ Deletar Registro", key=f"del_{row['id']}"):
                                db.collection("pagamentos").document(row['id']).delete()
                                st.success("Apagado!")
                                st.rerun()
                        with col_b:
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url_arquivo'], use_container_width=True)
                            else:
                                st.info("Arquivo PDF/Documento. Clique no botão ao lado para visualizar.")
            else:
                st.info("Nenhum registro encontrado para essa pesquisa.")
        else:
            st.info("Ainda não há comprovantes salvos no sistema.")
            
    except Exception as e:
        st.error(f"Erro ao carregar o financeiro: {e}")
