import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz
import time
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Sistema Profissional", layout="wide", page_icon="🏥")

# --- LOGIN SIMPLES ---
def check_password():
    def password_entered():
        if st.session_state["password"] == "ame2026": # VOCÊ PODE MUDAR A SENHA AQUI
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown('<div style="text-align:center"><h1>🏥 AME - Acesso Restrito</h1></div>', unsafe_allow_html=True)
        st.text_input("Digite a senha da clínica", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Senha incorreta. Tente novamente", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha inválida")
        return False
    else:
        return True

if not check_password():
    st.stop()

# --- CSS PROFISSIONAL ---
st.markdown("""
    <style>
    html, body, [class*="View"] { font-size: 19px !important; }
    .logo-ame { font-size: 60px; font-weight: 900; color: #008f39; margin-bottom: -15px; }
    .sub-logo { font-size: 18px; color: #444; font-weight: 600; margin-bottom: 20px; text-transform: uppercase; }
    .alerta-nota { background-color: #ff4b4b; color: white; padding: 15px; border-radius: 10px; text-align: center; font-weight: bold; font-size: 24px; margin-bottom: 20px; }
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
@st.cache_data(ttl=60) # Faz o site carregar mais rápido
def obter_dados():
    docs = db.collection("pagamentos").order_by("data_ordenacao", direction="DESCENDING").stream()
    lista = []
    for doc in docs:
        item = doc.to_dict()
        item['id'] = doc.id
        lista.append(item)
    return pd.DataFrame(lista) if lista else pd.DataFrame()

df = obter_dados()

# --- CABEÇALHO ---
st.markdown('<div class="logo-ame">AME</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-logo">Assistência Médica Especializada</div>', unsafe_allow_html=True)

aba_envio, aba_financeiro = st.tabs(["📥 ENVIAR COMPROVANTE", "🔍 GESTÃO E EXCEL"])

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
                    "mes_ano": agora.strftime("%m/%Y"),
                    "empresa": empresa, "cnpj": cnpj, "funcionario": func,
                    "valor": valor, "url_arquivo": blob.public_url,
                    "status_nota": "PENDENTE", "obs": obs, "tipo": ext
                })
                st.balloons()
                st.success("✅ Registro enviado!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

with aba_financeiro:
    st.subheader("Painel de Controle e Exportação")
    
    # Filtros Avançados
    f1, f2, f3 = st.columns([2, 1, 1])
    with f1:
        pesquisa = st.text_input("🔍 Buscar por Empresa/Funcionário:").upper()
    with f2:
        meses = df['mes_ano'].unique().tolist() if not df.empty else [datetime.now(fuso_br).strftime("%m/%Y")]
        filtro_mes = st.selectbox("📅 Filtrar Mês", ["Todos"] + meses)
    with f3:
        filtro_status = st.selectbox("🧾 Status NF", ["Todos", "PENDENTE", "REALIZADA"])

    if not df.empty:
        df_view = df.copy().fillna("")
        
        # Aplicar filtros
        if pesquisa:
            df_view = df_view[(df_view['empresa'].str.contains(pesquisa)) | (df_view['funcionario'].str.contains(pesquisa))]
        if filtro_mes != "Todos":
            df_view = df_view[df_view['mes_ano'] == filtro_mes]
        if filtro_status != "Todos":
            df_view = df_view[df_view['status_nota'] == filtro_status]

        # BOTÃO EXCEL
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_view.to_excel(writer, index=False, sheet_name='Financeiro_AME')
        
        st.download_button(
            label="📥 BAIXAR RELATÓRIO EXCEL",
            data=buffer,
            file_name=f"Relatorio_AME_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.divider()
        
        # Alerta de Pendências
        pendentes_count = len(df_view[df_view['status_nota'] == "PENDENTE"])
        if pendentes_count > 0:
            st.warning(f"🚨 Existem {pendentes_count} notas pendentes neste filtro.")

        for i, row in df_view.iterrows():
            status_cor = "🟢" if row['status_nota'] == "REALIZADA" else "🔴"
            with st.expander(f"{status_cor} {row['empresa']} | {row['funcionario']} | R$ {row['valor']:.2f}"):
                col_a, col_b = st.columns([2, 1])
                with col_a:
                    st.write(f"**Data Envio:** {row['data_formatada']} às {row['hora']}")
                    st.link_button("📂 Ver Comprovante", row['url_arquivo'])
                    
                    if row['status_nota'] == "PENDENTE":
                        if st.button("✅ MARCAR NOTA COMO FEITA", key=f"btn_{row['id']}", type="primary"):
                            db.collection("pagamentos").document(row['id']).update({"status_nota": "REALIZADA", "data_nota_feita": datetime.now(fuso_br).strftime("%d/%m/%Y %H:%M")})
                            st.cache_data.clear()
                            st.rerun()
                    else:
                        st.success(f"Nota Finalizada em: {row.get('data_nota_feita', 'Data não registrada')}")
                
                with col_b:
                    if st.button("🗑️ Deletar", key=f"del_{row['id']}", use_container_width=True):
                        db.collection("pagamentos").document(row['id']).delete()
                        st.cache_data.clear()
                        st.rerun()
    else:
        st.info("Nenhum registro para exibir.")
