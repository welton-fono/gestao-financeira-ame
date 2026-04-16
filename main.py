import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro PRO", layout="wide", page_icon="🏥", initial_sidebar_state="expanded")

# --- CSS PARA DESIGN PROFISSIONAL E LETRAS MAIORES ---
st.markdown("""
    <style>
    /* Aumentar o tamanho da fonte global */
    html, body, [class*="View"] {
        font-size: 18px !important;
    }
    
    /* Estilizar métricas (Quadrados do topo) */
    .stMetric {
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 12px; 
        border: 1px solid #e0e0e0; 
        box-shadow: 2px 2px 8px rgba(0,0,0,0.08);
    }
    [data-testid="stMetricValue"] {
        font-size: 32px !important;
        font-weight: bold;
    }
    [data-testid="stMetricLabel"] {
        font-size: 20px !important;
    }

    /* Estilizar Títulos e Subtítulos */
    h1 { font-size: 42px !important; color: #008f39 !important; }
    h2, h3 { font-size: 28px !important; }

    /* Estilizar o Expander (Lista de notas) */
    .stExpander {
        border: 1px solid #d1d1d1; 
        border-radius: 10px; 
        margin-bottom: 12px;
        background-color: #ffffff;
    }
    
    .logo-ame { font-size: 60px; font-weight: 900; color: #008f39; letter-spacing: 2px; margin-bottom: -15px; }
    .sub-logo { font-size: 18px; color: #555555; font-weight: 600; margin-bottom: 25px; text-transform: uppercase; }
    
    /* Deixar os inputs e labels maiores */
    label { font-size: 20px !important; font-weight: bold !important; }
    input { font-size: 18px !important; }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {'storageBucket': 'chamdor-amesaude.firebasestorage.app'})
    except Exception as e:
        st.error(f"Erro na conexão: {e}")

db = firestore.client()
bucket = storage.bucket()
fuso_br = pytz.timezone('America/Sao_Paulo')

# --- CABEÇALHO ---
st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">Assistência Médica Especializada</div>', unsafe_allow_html=True)
st.divider()

aba_envio, aba_busca = st.tabs(["📥 Lançar Novo Documento", "📊 Painel do Financeiro"])

with aba_envio:
    st.subheader("Registrar Documento")
    with st.form("form_caixa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("🏢 Empresa/Cliente").upper()
            cnpj = st.text_input("📑 CNPJ da Empresa")
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
            nf_pronta = st.checkbox("🧾 NF já emitida e arquivada?") 
            
        with col2:
            funcionario = st.text_input("👤 Nome do Funcionário (Exame)")
            arquivo = st.file_uploader("📎 Anexar Comprovante (PDF, Imagem)")
            obs = st.text_area("📝 Observações", height=100)
        
        enviado = st.form_submit_button("SALVAR REGISTRO", use_container_width=True)
        
        if enviado:
            if cliente and arquivo and cnpj and funcionario:
                try:
                    ext = arquivo.name.split('.')[-1].lower()
                    agora = datetime.now(fuso_br)
                    nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{cliente}.{ext}"
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    db.collection("pagamentos").add({
                        "data_completa": agora.strftime("%Y/%m/%d %H:%M:%S"),
                        "dia": agora.strftime("%d/%m/%Y"),
                        "hora": agora.strftime("%H:%M"),
                        "mes_ano": agora.strftime("%m/%Y"),
                        "cliente": cliente,
                        "cnpj": cnpj,
                        "funcionario": funcionario,
                        "valor": valor,
                        "arquivado": nf_pronta, 
                        "url": blob.public_url,
                        "nome_storage": nome_arq,
                        "tipo": ext,
                        "obs": obs
                    })
                    st.success(f"✅ Registro de {cliente} salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("⚠️ Preencha todos os campos obrigatórios.")

with aba_busca:
    st.subheader("Painel de Controle Financeiro")
    
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        busca = st.text_input("🔍 Buscar Cliente/Funcionário:").upper()
    with c2:
        mes_atual = datetime.now(fuso_br).strftime("%m/%Y")
        mes_filtro = st.text_input("📅 Mês/Ano", value=mes_atual)
    with c3:
        exibir_arquivados = st.selectbox("📂 Ver Registros", ["📌 Ativos (Pendentes)", "📁 Arquivados (Baixados)", "🔍 Todos"])
    with c4:
        st.write("") 
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    try:
        # Puxa os dados
        docs = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING").stream()
        lista_dados = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            # GARANTE QUE O ARQUIVAMENTO FUNCIONE MESMO PARA REGISTROS SEM ESSE CAMPO
            d['arquivado'] = d.get('arquivado', False)
            lista_dados.append(d)
        
        if lista_dados:
            df = pd.DataFrame(lista_dados).fillna("")
            
            if busca:
                df = df[(df['cliente'].astype(str).str.contains(busca)) | (df['funcionario'].astype(str).str.contains(busca))]
            if mes_filtro:
                df = df[df['mes_ano'] == mes_filtro]
            
            # Lógica de filtro corrigida
            if exibir_arquivados == "📌 Ativos (Pendentes)":
                df = df[df['arquivado'] == False]
            elif exibir_arquivados == "📁 Arquivados (Baixados)":
                df = df[df['arquivado'] == True]
            
            if not df.empty:
                t1, t2, t3 = st.columns(3)
                t1.metric("💰 Total Valor", f"R$ {df['valor'].sum():,.2f}")
                t2.metric("📄 Documentos", f"{len(df)} itens")
                status_txt = "Pendentes" if "Ativos" in exibir_arquivados else "Arquivados"
                t3.metric("📊 Status Atual", status_txt)
                st.divider()

                for i, row in df.iterrows():
                    icon = "📕" if row['tipo'] == 'pdf' else "🖼️"
                    status_cor = "🔴 Pendente" if not row['arquivado'] else "🟢 Arquivado"
                    
                    with st.expander(f"{icon} {row['cliente']} | {row['funcionario']} | R$ {row['valor']:.2f} | {status_cor}"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**Empresa:** {row['cliente']} (CNPJ: {row['cnpj']})")
                            st.write(f"**Funcionário:** {row['funcionario']}")
                            st.write(f"**Data:** {row.get('dia', '--')} às {row.get('hora', '--:--')}")
                            st.write(f"**Obs:** {row.get('obs', '')}")
                            st.link_button("📂 Ver Arquivo", row['url'])
                            
                            st.write("---")
                            act1, act2 = st.columns(2)
                            with act1:
                                if not row['arquivado']:
                                    if st.button(f"📥 Arquivar Nota", key=f"ark_{row['id']}", type="primary", use_container_width=True):
                                        db.collection("pagamentos").document(row['id']).update({"arquivado": True})
                                        st.rerun()
                                else:
                                    if st.button(f"🔙 Desarquivar", key=f"unark_{row['id']}", use_container_width=True):
                                        db.collection("pagamentos").document(row['id']).update({"arquivado": False})
                                        st.rerun()
                            with act2:
                                if st.button(f"🗑️ Deletar", key=f"del_{row['id']}", use_container_width=True):
                                    try:
                                        nome_arq = str(row.get('nome_storage', ''))
                                        if nome_arq and nome_arq.lower() != "nan":
                                            try: bucket.blob(f"comprovantes/{nome_arq}").delete()
                                            except: pass
                                        db.collection("pagamentos").document(row['id']).delete()
                                        st.rerun()
                                    except: st.error("Erro ao apagar.")

                        with col_b:
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url'], use_container_width=True)
                            else:
                                st.info("Preview indisponível.")
            else:
                st.info("Nenhum registro encontrado nesta categoria.")
        else:
            st.info("O sistema está vazio.")
    except Exception as e:
        st.error(f"Erro: {e}")
