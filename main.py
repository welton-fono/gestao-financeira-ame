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
    html, body, [class*="View"] { font-size: 18px !important; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 2px 2px 8px rgba(0,0,0,0.08); }
    [data-testid="stMetricValue"] { font-size: 32px !important; font-weight: bold; }
    [data-testid="stMetricLabel"] { font-size: 20px !important; }
    h1 { font-size: 42px !important; color: #008f39 !important; }
    h2, h3 { font-size: 28px !important; }
    .stExpander { border: 1px solid #d1d1d1; border-radius: 10px; margin-bottom: 12px; background-color: #ffffff; }
    .logo-ame { font-size: 60px; font-weight: 900; color: #008f39; letter-spacing: 2px; margin-bottom: -15px; }
    .sub-logo { font-size: 18px; color: #555555; font-weight: 600; margin-bottom: 25px; text-transform: uppercase; }
    label { font-size: 20px !important; font-weight: bold !important; }
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
        with col2:
            funcionario = st.text_input("👤 Nome do Funcionário (Exame)")
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
                        "url_nf": None, # Começa sem NF
                        "nome_storage": nome_arq,
                        "tipo": ext,
                        "obs": obs
                    })
                    st.success(f"✅ Registro de {cliente} salvo!")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("⚠️ Preencha todos os campos obrigatórios.")

with aba_busca:
    st.subheader("Painel Financeiro")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        busca = st.text_input("🔍 Buscar Cliente/Funcionário:").upper()
    with c2:
        mes_atual = datetime.now(fuso_br).strftime("%m/%Y")
        mes_filtro = st.text_input("📅 Mês/Ano", value=mes_atual)
    with c3:
        st.write("") 
        if st.button("🔄 Atualizar", use_container_width=True):
            st.rerun()

    try:
        docs = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING").stream()
        lista_dados = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            lista_dados.append(d)
        
        if lista_dados:
            df = pd.DataFrame(lista_dados).fillna("")
            if busca:
                df = df[(df['cliente'].astype(str).str.contains(busca)) | (df['funcionario'].astype(str).str.contains(busca))]
            if mes_filtro:
                df = df[df['mes_ano'] == mes_filtro]
            
            if not df.empty:
                t1, t2 = st.columns(2)
                t1.metric("💰 Total do Mês", f"R$ {df['valor'].sum():,.2f}")
                t2.metric("📄 Registros", f"{len(df)} itens")
                st.divider()

                for i, row in df.iterrows():
                    # Status visual se tem NF ou não
                    tem_nf = "✅ NF PRONTA" if row.get('url_nf') else "⏳ SEM NOTA"
                    
                    with st.expander(f"🏢 {row['cliente']} | {row['funcionario']} | R$ {row['valor']:.2f} | {tem_nf}"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**CNPJ:** {row['cnpj']}")
                            st.write(f"**Data:** {row.get('dia')} às {row.get('hora')}")
                            st.write(f"**Observação:** {row.get('obs')}")
                            
                            st.write("---")
                            # BOTÕES DE ARQUIVOS
                            st.link_button("📂 Ver Comprovante do Exame", row.get('url_comprovante', row.get('url')))
                            
                            if row.get('url_nf'):
                                st.link_button("📄 BAIXAR NOTA FISCAL PRONTA", row['url_nf'], type="primary")
                            else:
                                st.warning("A nota fiscal ainda não foi anexada.")

                            st.write("---")
                            # UPLOAD DA NF PRONTA
                            nova_nf = st.file_uploader("📤 Anexar PDF da Nota Fiscal Pronta", key=f"up_{row['id']}")
                            if nova_nf:
                                if st.button(f"Confirmar Upload NF", key=f"btn_{row['id']}"):
                                    nome_nf = f"NF_{row['id']}.pdf"
                                    blob_nf = bucket.blob(f"notas_fiscais/{nome_nf}")
                                    blob_nf.upload_from_string(nova_nf.read(), content_type=nova_nf.type)
                                    blob_nf.make_public()
                                    db.collection("pagamentos").document(row['id']).update({"url_nf": blob_nf.public_url})
                                    st.success("Nota Fiscal anexada!")
                                    st.rerun()

                        with col_b:
                            if st.button(f"🗑️ Deletar Tudo", key=f"del_{row['id']}", use_container_width=True):
                                db.collection("pagamentos").document(row['id']).delete()
                                st.rerun()
            else:
                st.info("Nenhum registro para este filtro.")
    except Exception as e:
        st.error(f"Erro: {e}")
