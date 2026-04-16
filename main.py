import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro", layout="wide", page_icon="🏥")

# --- CSS PARA DESIGN E ALERTAS ---
st.markdown("""
    <style>
    html, body, [class*="View"] { font-size: 19px !important; }
    .logo-ame { font-size: 60px; font-weight: 900; color: #008f39; margin-bottom: -15px; }
    .sub-logo { font-size: 18px; color: #444; font-weight: 600; margin-bottom: 20px; text-transform: uppercase; }
    
    /* Estilo do Alerta de Nota Pendente */
    .alerta-nota {
        background-color: #ff4b4b;
        color: white;
        padding: 15px;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        font-size: 24px;
        margin-bottom: 20px;
        animation: blinker 2s linear infinite;
    }
    @keyframes blinker { 50% { opacity: 0.7; } }
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

# --- BUSCA DE DADOS ---
def obter_dados():
    docs = db.collection("pagamentos").order_by("data_ordenacao", direction="DESCENDING").stream()
    lista = []
    for doc in docs:
        item = doc.to_dict()
        item['id'] = doc.id
        lista.append(item)
    return pd.DataFrame(lista) if lista else pd.DataFrame()

df = obter_dados()

# --- VERIFICAÇÃO DE NOTAS PENDENTES (PARA A NOTIFICAÇÃO) ---
notas_pendentes = 0
if not df.empty:
    # Conta registros que não possuem url_nf
    notas_pendentes = len(df[df['url_nf'].isna() | (df['url_nf'] == "")])

# --- CABEÇALHO ---
st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">Assistência Médica Especializada</div>', unsafe_allow_html=True)

# NOTIFICAÇÃO QUE APARECE EM TODAS AS ABAS
if notas_pendentes > 0:
    st.markdown(f'<div class="alerta-nota">🚨 TEM NOTA FISCAL PARA FAZER ({notas_pendentes} pendentes)</div>', unsafe_allow_html=True)

aba_envio, aba_financeiro = st.tabs(["📥 ENVIAR COMPROVANTE", "🔍 PAINEL FINANCEIRO"])

with aba_envio:
    st.subheader("Registrar Novo Documento")
    with st.form("form_registro", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            empresa = st.text_input("🏢 Empresa").upper()
            cnpj = st.text_input("📑 CNPJ")
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
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
                    "hora": agora.strftime("%H:%M"),
                    "empresa": empresa, "cnpj": cnpj, "funcionario": func,
                    "valor": valor, "url_arquivo": blob.public_url,
                    "url_nf": None, "obs": obs, "tipo": ext
                })
                st.toast("✅ Registro salvo!", icon="🔔")
                st.success("Enviado com sucesso!")
                time.sleep(1)
                st.rerun()

with aba_financeiro:
    st.subheader("Gestão de Pagamentos e Notas")
    pesquisa = st.text_input("🔍 Buscar:").upper()
    
    if not df.empty:
        df_view = df.copy()
        if pesquisa:
            df_view = df_view[(df_view['empresa'].str.contains(pesquisa)) | (df_view['funcionario'].str.contains(pesquisa))]
        
        for i, row in df_view.iterrows():
            tem_nf = "✅ NF OK" if row.get('url_nf') else "⏳ PENDENTE"
            with st.expander(f"{row['empresa']} | {row['funcionario']} | R$ {row['valor']:.2f} | {tem_nf}"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.write(f"**Data:** {row['data_formatada']} às {row['hora']}")
                    st.link_button("📂 Ver Comprovante", row['url_arquivo'])
                    
                    if row.get('url_nf'):
                        st.link_button("📄 BAIXAR NOTA FISCAL PRONTA", row['url_nf'], type="primary")
                    else:
                        st.error("Esta nota ainda não foi feita.")
                    
                    st.divider()
                    # ÁREA DE COLOCAR A NOTA FISCAL PRONTA
                    up_nf = st.file_uploader("📤 Anexar PDF da Nota Fiscal Pronta", key=f"nf_{row['id']}")
                    if up_nf:
                        if st.button("Confirmar Anexo da NF", key=f"btn_{row['id']}"):
                            blob_nf = bucket.blob(f"notas/{row['id']}.pdf")
                            blob_nf.upload_from_string(up_nf.read(), content_type="application/pdf")
                            blob_nf.make_public()
                            db.collection("pagamentos").document(row['id']).update({"url_nf": blob_nf.public_url})
                            st.success("Nota anexada!")
                            st.rerun()
                
                with col_b:
                    if st.button("🗑️ Deletar", key=f"del_{row['id']}", use_container_width=True):
                        db.collection("pagamentos").document(row['id']).delete()
                        st.rerun()
    else:
        st.info("Nenhum registro.")
