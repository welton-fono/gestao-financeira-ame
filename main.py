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

# --- CÁLCULO DE PENDÊNCIAS PARA O BALÃO ---
pendentes_total = 0
if not df.empty:
    if 'url_nf' not in df.columns: df['url_nf'] = None
    if 'status_nota' not in df.columns: df['status_nota'] = "PENDENTE"
    pendentes_total = len(df[(df['url_nf'].isna() | (df['url_nf'] == "")) & (df['status_nota'] != "REALIZADA")])

# --- CSS ---
st.markdown(f"""
    <style>
    .logo-ame {{ font-size: 55px; font-weight: 900; color: #008f39; margin-bottom: -15px; }}
    .sub-logo {{ font-size: 16px; color: #444; font-weight: 600; margin-bottom: 20px; }}
    /* Estilo do Balão de Notificação na Aba */
    .badge {{
        background-color: #ff4b4b;
        color: white;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 14px;
        margin-left: 5px;
        font-weight: bold;
    }}
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">ASSISTÊNCIA MÉDICA ESPECIALIZADA</div>', unsafe_allow_html=True)

# Título da aba com balão dinâmico
texto_aba_financeiro = f"🔍 FINANCEIRO"
if pendentes_total > 0:
    texto_aba_financeiro = f"🔍 FINANCEIRO ({pendentes_total})"

aba_envio, aba_financeiro, aba_dashboard = st.tabs(["📥 LANÇAR", texto_aba_financeiro, "📊 DASHBOARD"])

with aba_envio:
    st.subheader("Registrar Novo Documento")
    with st.form("form_registro", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            empresa = st.text_input("🏢 Empresa").upper()
            cnpj = st.text_input("📑 CNPJ")
            valor = st.number_input("💰 Valor", min_value=0.0)
        with c2:
            func = st.text_input("👤 Funcionário")
            arquivo = st.file_uploader("📎 Comprovante")
            obs = st.text_area("📝 Obs")
        if st.form_submit_button("🚀 SALVAR REGISTRO", use_container_width=True):
            if empresa and arquivo and func:
                agora = datetime.now(fuso_br)
                ext = arquivo.name.split('.')[-1].lower()
                nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{empresa}.{ext}"
                blob = bucket.blob(f"comprovantes/{nome_arq}")
                blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                blob.make_public()
                db.collection("pagamentos").add({
                    "data_ordenacao": agora.strftime("%Y/%m/%d %H:%M:%S"),
                    "data_formatada": agora.strftime("%d/%m/%Y"),
                    "dia": agora.strftime("%d"),
                    "mes_ano": agora.strftime("%m/%Y"),
                    "empresa": empresa, "cnpj": cnpj, "funcionario": func,
                    "valor": valor, "url_arquivo": blob.public_url,
                    "status_nota": "PENDENTE", "url_nf": None
                })
                st.success("Salvo!")
                st.cache_data.clear()
                st.rerun()

with aba_financeiro:
    st.subheader("Painel de Controle")
    
    if not df.empty:
        # Garantir colunas
        for col in ['mes_ano', 'data_formatada', 'status_nota', 'url_nf']:
            if col not in df.columns: df[col] = None
        
        df_view = df.copy().fillna("")
        
        # --- FILTROS DE PESQUISA ---
        col_p, col_m, col_d = st.columns([2, 1, 1])
        with col_p:
            pesquisa = st.text_input("🔍 Buscar Empresa/Funcionário:").upper()
        with col_m:
            meses = sorted(df_view['mes_ano'].unique().tolist())
            filtro_mes = st.selectbox("📅 Mês/Ano", ["Todos"] + meses)
        with col_d:
            filtro_dia = st.text_input("📆 Dia (Ex: 16)")

        # Aplicar os filtros
        if pesquisa:
            df_view = df_view[(df_view['empresa'].str.contains(pesquisa)) | (df_view['funcionario'].str.contains(pesquisa))]
        if filtro_mes != "Todos":
            df_view = df_view[df_view['mes_ano'] == filtro_mes]
        if filtro_dia:
            df_view = df_view[df_view['data_formatada'].str.startswith(filtro_dia)]

        # Botão Excel
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_view.to_excel(writer, index=False)
        st.download_button("📥 BAIXAR EXCEL", buffer, "financeiro_ame.xlsx", use_container_width=True)

        st.divider()

        for i, row in df_view.iterrows():
            tem_nf = row.get('url_nf') != "" and row.get('url_nf') is not None
            foi_marcada = row.get('status_nota') == "REALIZADA"
            status_cor = "🟢" if (tem_nf or foi_marcada) else "🔴"
            
            with st.expander(f"{status_cor} {row['empresa']} | {row['funcionario']} | R$ {row['valor']:.2f}"):
                c1, c2 = st.columns([2,1])
                with c1:
                    st.write(f"**Data:** {row.get('data_formatada')}")
                    st.link_button("👁️ Ver Comprovante", row['url_arquivo'])
                    
                    if tem_nf or foi_marcada:
                        st.success(f"✅ Nota realizada em: {row.get('data_nota_feita', 'Data não registrada')}")
                        if tem_nf:
                            st.link_button("📄 BAIXAR NOTA PDF", row['url_nf'], type="primary")
                    else:
                        st.error("⏳ NF PENDENTE")
                        # BOTÃO DE CONFIRMAÇÃO MANUAL
                        if st.button("✔️ Marcar como Nota Feita (Manual)", key=f"man_{row['id']}"):
                            agora_nf = datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                            db.collection("pagamentos").document(row['id']).update({
                                "status_nota": "REALIZADA",
                                "data_nota_feita": agora_nf
                            })
                            st.cache_data.clear()
                            st.rerun()

                        st.write("---")
                        up_nf = st.file_uploader("Anexar PDF da Nota", key=f"up_{row['id']}")
                        if up_nf and st.button("Confirmar PDF", key=f"b_{row['id']}"):
                            blob_nf = bucket.blob(f"notas/{row['id']}.pdf")
                            blob_nf.upload_from_string(up_nf.read(), content_type="application/pdf")
                            blob_nf.make_public()
                            db.collection("pagamentos").document(row['id']).update({
                                "url_nf": blob_nf.public_url, 
                                "status_nota": "REALIZADA", 
                                "data_nota_feita": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")
                            })
                            st.cache_data.clear()
                            st.rerun()
                with c2:
                    if st.button("🗑️ Deletar", key=f"d_{row['id']}", use_container_width=True):
                        db.collection("pagamentos").document(row['id']).delete()
                        st.cache_data.clear()
                        st.rerun()

# --- ABA DASHBOARD (Mantida igual) ---
with aba_dashboard:
    st.subheader("📊 Análise de Desempenho AME")
    if not df.empty:
        df_dash = df.copy()
        df_dash['valor'] = pd.to_numeric(df_dash['valor'])
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Faturamento Total", f"R$ {df_dash['valor'].sum():,.2f}")
        col2.metric("🏢 Total de Empresas", df_dash['empresa'].nunique())
        col3.metric("📑 Exames Realizados", len(df_dash))
        
        g1, g2 = st.columns(2)
        with g1:
            fat_empresa = df_dash.groupby('empresa')['valor'].sum().reset_index().sort_values('valor', ascending=False).head(10)
            st.plotly_chart(px.bar(fat_empresa, x='empresa', y='valor', color='valor', color_continuous_scale='Greens'), use_container_width=True)
        with g2:
            vol_mes = df_dash.groupby('mes_ano').size().reset_index(name='quantidade')
            st.plotly_chart(px.line(vol_mes, x='mes_ano', y='quantidade', markers=True), use_container_width=True)
