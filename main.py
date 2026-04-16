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
@st.cache_data(ttl=10)
def obter_dados():
    try:
        docs = db.collection("pagamentos").order_by("data_ordenacao", direction="DESCENDING").stream()
        lista = [{**doc.to_dict(), 'id': doc.id} for doc in docs]
        return pd.DataFrame(lista) if lista else pd.DataFrame()
    except:
        return pd.DataFrame()

df = obter_dados()

# --- CSS ---
st.markdown("""
    <style>
    .logo-ame { font-size: 55px; font-weight: 900; color: #008f39; margin-bottom: -15px; }
    .sub-logo { font-size: 16px; color: #444; font-weight: 600; margin-bottom: 20px; }
    .card { background-color: #f9f9f9; padding: 20px; border-radius: 10px; border-left: 5px solid #008f39; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">ASSISTÊNCIA MÉDICA ESPECIALIZADA</div>', unsafe_allow_html=True)

aba_envio, aba_financeiro, aba_dashboard = st.tabs(["📥 LANÇAR", "🔍 FINANCEIRO", "📊 DASHBOARD"])

# --- ABA ENVIO (Mesma função de antes) ---
with aba_envio:
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
                    "mes_ano": agora.strftime("%m/%Y"),
                    "empresa": empresa, "cnpj": cnpj, "funcionario": func,
                    "valor": valor, "url_arquivo": blob.public_url,
                    "status_nota": "PENDENTE", "url_nf": None
                })
                st.success("Salvo!")
                st.cache_data.clear()
                st.rerun()

# --- ABA FINANCEIRO (Com Excel e Anexo de NF) ---
with aba_financeiro:
    if not df.empty:
        df_view = df.copy().fillna("")
        pesquisa = st.text_input("🔍 Pesquisar:").upper()
        if pesquisa:
            df_view = df_view[(df_view['empresa'].str.contains(pesquisa)) | (df_view['funcionario'].str.contains(pesquisa))]
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_view.to_excel(writer, index=False)
        st.download_button("📥 BAIXAR EXCEL", buffer, "financeiro_ame.xlsx", use_container_width=True)

        for i, row in df_view.iterrows():
            pronto = row.get('url_nf')
            st_cor = "🟢" if pronto else "🔴"
            with st.expander(f"{st_cor} {row['empresa']} | {row['funcionario']} | R$ {row['valor']:.2f}"):
                c1, c2 = st.columns([2,1])
                with c1:
                    st.write(f"Data: {row.get('data_formatada')}")
                    st.link_button("👁️ Ver Comprovante", row['url_arquivo'])
                    if pronto:
                        st.link_button("📄 BAIXAR NOTA", row['url_nf'], type="primary")
                    else:
                        up_nf = st.file_uploader("Anexar NF PDF", key=f"f_{row['id']}")
                        if up_nf and st.button("Confirmar", key=f"b_{row['id']}"):
                            blob_nf = bucket.blob(f"notas/{row['id']}.pdf")
                            blob_nf.upload_from_string(up_nf.read(), content_type="application/pdf")
                            blob_nf.make_public()
                            db.collection("pagamentos").document(row['id']).update({"url_nf": blob_nf.public_url, "status_nota": "REALIZADA", "data_nota_feita": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")})
                            st.cache_data.clear()
                            st.rerun()
                with c2:
                    if st.button("🗑️ Deletar", key=f"d_{row['id']}"):
                        db.collection("pagamentos").document(row['id']).delete()
                        st.cache_data.clear()
                        st.rerun()

# --- ABA DASHBOARD (NOVIDADE!) ---
with aba_dashboard:
    st.subheader("📊 Análise de Desempenho AME")
    if not df.empty:
        df_dash = df.copy()
        df_dash['valor'] = pd.to_numeric(df_dash['valor'])
        
        # 1. Métricas Rápidas
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 Faturamento Total", f"R$ {df_dash['valor'].sum():,.2f}")
        col2.metric("🏢 Total de Empresas", df_dash['empresa'].nunique())
        col3.metric("📑 Exames Realizados", len(df_dash))

        st.divider()

        # 2. Gráficos
        g1, g2 = st.columns(2)
        
        with g1:
            st.markdown("**🏢 Faturamento por Empresa**")
            fat_empresa = df_dash.groupby('empresa')['valor'].sum().reset_index().sort_values('valor', ascending=False).head(10)
            fig1 = px.bar(fat_empresa, x='empresa', y='valor', color='valor', color_continuous_scale='Greens')
            st.plotly_chart(fig1, use_container_width=True)

        with g2:
            st.markdown("**📈 Volume de Exames por Mês**")
            vol_mes = df_dash.groupby('mes_ano').size().reset_index(name='quantidade')
            fig2 = px.line(vol_mes, x='mes_ano', y='quantidade', markers=True, line_shape='spline')
            fig2.update_traces(line_color='#008f39')
            st.plotly_chart(fig2, use_container_width=True)

        # 3. Status das Notas
        st.markdown("**🧾 Status das Notas Fiscais (Geral)**")
        df_dash['Status'] = df_dash['url_nf'].apply(lambda x: "Realizada" if x else "Pendente")
        status_pie = df_dash['Status'].value_counts().reset_index()
        fig3 = px.pie(status_pie, values='count', names='Status', color='Status', 
                     color_discrete_map={'Realizada':'#008f39', 'Pendente':'#ff4b4b'}, hole=.4)
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("Aguardando dados para gerar os gráficos.")
