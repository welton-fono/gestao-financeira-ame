import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro PRO", layout="wide", page_icon="🏥", initial_sidebar_state="expanded")

# --- CSS PARA DESIGN PROFISSIONAL E ALERTAS ---
st.markdown("""
    <style>
    html, body, [class*="View"] { font-size: 18px !important; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 2px 2px 8px rgba(0,0,0,0.08); }
    [data-testid="stMetricValue"] { font-size: 32px !important; font-weight: bold; }
    h1 { font-size: 42px !important; color: #008f39 !important; }
    .logo-ame { font-size: 60px; font-weight: 900; color: #008f39; letter-spacing: 2px; margin-bottom: -15px; }
    .sub-logo { font-size: 18px; color: #555555; font-weight: 600; margin-bottom: 25px; text-transform: uppercase; }
    
    /* Estilo para a aba de Alerta Vermelho */
    .stTabs [data-baseweb="tab"]:nth-child(2) { color: #d32f2f !important; font-weight: bold !important; }
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

# --- NAVEGAÇÃO POR ABAS ---
aba_envio, aba_pendentes, aba_geral = st.tabs(["📥 Lançar Documento", "🚨 NOTAS PENDENTES", "📊 Histórico Geral"])

# --- FUNÇÃO PARA BUSCAR DADOS ---
def carregar_dados():
    docs = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING").stream()
    lista = []
    for doc in docs:
        d = doc.to_dict()
        d['id'] = doc.id
        lista.append(d)
    return pd.DataFrame(lista) if lista else pd.DataFrame()

df_total = carregar_dados()

# --- ABA 1: ENVIO ---
with aba_envio:
    st.subheader("Registrar Novo Exame")
    with st.form("form_caixa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("🏢 Empresa/Cliente").upper()
            cnpj = st.text_input("📑 CNPJ da Empresa")
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
        with col2:
            funcionario = st.text_input("👤 Nome do Funcionário")
            arquivo = st.file_uploader("📎 Anexar Comprovante do Exame")
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
                        "url_comprovante": blob.public_url,
                        "url_nf": None,
                        "nome_storage": nome_arq,
                        "tipo": ext,
                        "obs": obs
                    })
                    # NOTIFICAÇÃO VISUAL
                    st.toast(f"🔔 NOVO REGISTRO: {cliente} salvo com sucesso!", icon='🚀')
                    st.success(f"✅ Documento registrado!")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("⚠️ Preencha todos os campos obrigatórios.")

# --- ABA 2: PENDENTES (VERMELHA) ---
with aba_pendentes:
    st.markdown("### ⚠️ Notas Fiscais Não Realizadas")
    if not df_total.empty:
        # Filtra apenas quem não tem url_nf
        df_pend = df_total[df_total['url_nf'].isna() | (df_total['url_nf'] == "")]
        
        if not df_pend.empty:
            st.error(f"Atenção: Existem {len(df_pend)} notas aguardando anexo do PDF.")
            for i, row in df_pend.iterrows():
                with st.expander(f"❌ PENDENTE: {row['cliente']} - {row['funcionario']} (R$ {row['valor']:.2f})"):
                    st.write(f"**Data do Exame:** {row['dia']} às {row['hora']}")
                    st.link_button("👁️ Ver Comprovante do Exame", row['url_comprovante'])
                    
                    # Upload direto da NF aqui
                    nova_nf = st.file_uploader("📤 Anexar PDF da Nota Fiscal", key=f"pend_{row['id']}")
                    if nova_nf:
                        if st.button("Confirmar NF", key=f"btn_p_{row['id']}"):
                            blob_nf = bucket.blob(f"notas_fiscais/NF_{row['id']}.pdf")
                            blob_nf.upload_from_string(nova_nf.read(), content_type=nova_nf.type)
                            blob_nf.make_public()
                            db.collection("pagamentos").document(row['id']).update({"url_nf": blob_nf.public_url})
                            st.success("Nota anexada! Ela sairá desta lista agora.")
                            st.rerun()
        else:
            st.success("🎉 Ótimo trabalho! Todas as notas fiscais foram emitidas.")
    else:
        st.info("Nenhum dado encontrado.")

# --- ABA 3: HISTÓRICO GERAL ---
with aba_geral:
    st.subheader("Controle Geral Financeiro")
    busca = st.text_input("🔍 Pesquisar por Cliente ou Funcionário:").upper()
    
    if not df_total.empty:
        df_view = df_total.copy()
        if busca:
            df_view = df_view[(df_view['cliente'].str.contains(busca)) | (df_view['funcionario'].str.contains(busca))]
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric("💰 Faturamento Total", f"R$ {df_view['valor'].sum():,.2f}")
        col_m2.metric("📄 Total de Exames", f"{len(df_view)}")

        for i, row in df_view.iterrows():
            status = "✅ NF PRONTA" if row.get('url_nf') else "⏳ SEM NOTA"
            with st.expander(f"{row['cliente']} | {row['funcionario']} | {status}"):
                st.write(f"**CNPJ:** {row['cnpj']} | **Valor:** R$ {row['valor']:.2f}")
                st.write(f"**Data:** {row['dia']} às {row['hora']}")
                
                c1, c2 = st.columns(2)
                with c1:
                    st.link_button("📂 Comprovante Exame", row['url_comprovante'], use_container_width=True)
                with c2:
                    if row.get('url_nf'):
                        st.link_button("📄 NOTA FISCAL", row['url_nf'], type="primary", use_container_width=True)
                
                if st.button(f"🗑️ Deletar Registro", key=f"del_g_{row['id']}"):
                    db.collection("pagamentos").document(row['id']).delete()
                    st.rerun()
