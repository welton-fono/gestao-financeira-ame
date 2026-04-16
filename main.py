import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz
import time
import io
import plotly.express as px

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Gestão Inteligente", layout="wide", page_icon="🏥")

# --- LOGIN ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "ame2026":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if "password_correct" not in st.session_state:
        st.markdown('<div style="text-align:center"><h1>🏥 AME - Acesso Restrito</h1></div>', unsafe_allow_html=True)
        st.text_input("Senha da clínica", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.error("Senha inválida")
        return False
    return True

if not check_password():
    st.stop()

# --- CONEXÃO FIREBASE ---
if not firebase_admin._apps:
    try:
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {'storageBucket': 'chamdor-amesaude.firebasestorage.app'})
    except Exception as e:
        st.error(f"Erro Firebase: {e}")

db = firestore.client()
bucket = storage.bucket()
fuso_br = pytz.timezone('America/Sao_Paulo')

# --- BUSCA DE DADOS ---
@st.cache_data(ttl=5)
def obter_dados():
    try:
        docs = db.collection("pagamentos").order_by("data_ordenacao", direction="DESCENDING").stream()
        lista = [{**doc.to_dict(), 'id': doc.id} for doc in docs]
        return pd.DataFrame(lista) if lista else pd.DataFrame()
    except:
        return pd.DataFrame()

df = obter_dados()

# --- CÁLCULO DE PENDÊNCIAS ---
pendentes_total = 0
if not df.empty:
    for col in ['url_nf', 'status_nota']:
        if col not in df.columns: df[col] = None
    pendentes_total = len(df[(df['url_nf'].isna() | (df['url_nf'] == "")) & (df['status_nota'] != "REALIZADA")])

# --- CSS ---
st.markdown(f"""
    <style>
    .logo-ame {{ font-size: 55px; font-weight: 900; color: #008f39; margin-bottom: -15px; }}
    .sub-logo {{ font-size: 16px; color: #444; font-weight: 600; margin-bottom: 20px; }}
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">ASSISTÊNCIA MÉDICA ESPECIALIZADA</div>', unsafe_allow_html=True)

aba_envio, aba_financeiro, aba_dashboard = st.tabs([
    "📥 LANÇAR", 
    f"🔍 FINANCEIRO ({pendentes_total})" if pendentes_total > 0 else "🔍 FINANCEIRO", 
    "📊 DASHBOARD"
])

with aba_envio:
    st.subheader("Registrar Novo Documento")
    
    # LÓGICA DE MEMÓRIA (Auto-completar)
    sugestao_empresa = ""
    sugestao_func = ""
    
    doc_input = st.text_input("📑 Digite CNPJ ou CPF (Grava automaticamente)").strip()
    
    if doc_input and not df.empty:
        # Busca no banco se esse documento já existe
        registro_antigo = df[df['cnpj'] == doc_input]
        if not registro_antigo.empty:
            sugestao_empresa = registro_antigo.iloc[0]['empresa']
            sugestao_func = registro_antigo.iloc[0]['funcionario']
            st.info(f"✨ Documento reconhecido! Preenchendo dados de: {sugestao_empresa}")

    with st.form("form_registro", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            empresa = st.text_input("🏢 Empresa/Cliente", value=sugestao_empresa).upper()
            valor = st.number_input("💰 Valor (R$)", min_value=0.0)
        with c2:
            funcionario = st.text_input("👤 Funcionário", value=sugestao_func).upper()
            arquivo = st.file_uploader("📎 Comprovante")
        
        obs = st.text_area("📝 Observações")
        
        if st.form_submit_button("🚀 SALVAR REGISTRO", use_container_width=True):
            if empresa and arquivo and doc_input:
                agora = datetime.now(fuso_br)
                ext = arquivo.name.split('.')[-1].lower()
                nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{empresa}.{ext}"
                blob = bucket.blob(f"comprovantes/{nome_arq}")
                blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                blob.make_public()
                
                db.collection("pagamentos").add({
                    "data_ordenacao": agora.strftime("%Y/%m/%d %H:%M:%S"),
                    "data_formatada": agora.strftime("%d/%m/%Y"),
                    "mes_ano": agora.strftime("%m/%Y"),
                    "empresa": empresa, 
                    "cnpj": doc_input, # Salva o CNPJ/CPF informado
                    "funcionario": funcionario,
                    "valor": valor, 
                    "url_arquivo": blob.public_url,
                    "status_nota": "PENDENTE", 
                    "url_nf": None,
                    "obs": obs
                })
                st.success("✅ Registro e Documento salvos na memória!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()
            else:
                st.warning("⚠️ O campo de Documento (CNPJ/CPF), Empresa e Arquivo são obrigatórios.")

with aba_financeiro:
    st.subheader("Painel de Controle")
    if not df.empty:
        df_view = df.copy().fillna("")
        
        # --- FILTROS DE PESQUISA AMPLIADOS ---
        col1, col2, col3 = st.columns([1.5, 1.5, 1])
        with col1:
            pesquisa = st.text_input("🔍 Buscar Nome (Empresa/Funcionario):").upper()
        with col2:
            pesquisa_doc = st.text_input("🔍 Buscar por CNPJ ou CPF:")
        with col3:
            meses = sorted(df_view['mes_ano'].unique().tolist())
            filtro_mes = st.selectbox("📅 Mês/Ano", ["Todos"] + meses)

        # Aplicar Filtros
        if pesquisa:
            df_view = df_view[(df_view['empresa'].str.contains(pesquisa)) | (df_view['funcionario'].str.contains(pesquisa))]
        if pesquisa_doc:
            df_view = df_view[df_view['cnpj'].str.contains(pesquisa_doc)]
        if filtro_mes != "Todos":
            df_view = df_view[df_view['mes_ano'] == filtro_mes]

        st.divider()

        for i, row in df_view.iterrows():
            tem_nf = row.get('url_nf') != "" and row.get('url_nf') is not None
            foi_marcada = row.get('status_nota') == "REALIZADA"
            status_cor = "🟢" if (tem_nf or foi_marcada) else "🔴"
            
            with st.expander(f"{status_cor} {row['empresa']} | Doc: {row['cnpj']} | R$ {row['valor']:.2f}"):
                c1, c2 = st.columns([2,1])
                with c1:
                    st.write(f"**Funcionário:** {row['funcionario']}")
                    st.write(f"**Data:** {row['data_formatada']}")
                    st.link_button("👁️ Ver Comprovante", row['url_arquivo'])
                    
                    if tem_nf or foi_marcada:
                        st.success(f"✅ Nota realizada em: {row.get('data_nota_feita', 'Data manual')}")
                        if tem_nf: st.link_button("📄 BAIXAR NOTA PDF", row['url_nf'], type="primary")
                    else:
                        if st.button("✔️ Marcar como Nota Feita", key=f"m_{row['id']}"):
                            db.collection("pagamentos").document(row['id']).update({
                                "status_nota": "REALIZADA",
                                "data_nota_feita": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                            })
                            st.cache_data.clear()
                            st.rerun()
                        
                        up_nf = st.file_uploader("Anexar PDF da Nota", key=f"u_{row['id']}")
                        if up_nf and st.button("Confirmar PDF", key=f"b_{row['id']}"):
                            blob_nf = bucket.blob(f"notas/{row['id']}.pdf")
                            blob_nf.upload_from_string(up_nf.read(), content_type="application/pdf")
                            blob_nf.make_public()
                            db.collection("pagamentos").document(row['id']).update({
                                "url_nf": blob_nf.public_url, "status_nota": "REALIZADA", 
                                "data_nota_feita": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                            })
                            st.cache_data.clear()
                            st.rerun()
                with c2:
                    if st.button("🗑️ Deletar", key=f"d_{row['id']}"):
                        db.collection("pagamentos").document(row['id']).delete()
                        st.cache_data.clear()
                        st.rerun()

with aba_dashboard:
    # (Mantido os gráficos conforme a última versão)
    if not df.empty:
        df_dash = df.copy()
        df_dash['valor'] = pd.to_numeric(df_dash['valor'])
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Faturamento Total", f"R$ {df_dash['valor'].sum():,.2f}")
        col2.metric("🏢 Total de Empresas", df_dash['empresa'].nunique())
        col3.metric("📑 Exames Realizados", len(df_dash))
        st.plotly_chart(px.bar(df_dash.groupby('empresa')['valor'].sum().reset_index(), x='empresa', y='valor', color='valor', color_continuous_scale='Greens'), use_container_width=True)
