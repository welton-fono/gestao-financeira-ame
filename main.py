import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd
import pytz

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="AME - Financeiro PRO", layout="wide", page_icon="🏥")

# --- CSS PARA DESIGN PROFISSIONAL ---
st.markdown("""
    <style>
    .stMetric {background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0;}
    .stExpander {border: 1px solid #d1d1d1; border-radius: 8px; margin-bottom: 10px;}
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
                        "url": blob.public_url,
                        "nome_storage": nome_arq,
                        "tipo": ext,
                        "obs": obs
                    })
                    st.success(f"✅ Registro de {cliente} salvo com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")
            else:
                st.warning("⚠️ Todos os campos e o arquivo são obrigatórios.")

with aba_busca:
    st.subheader("Painel de Controle Financeiro")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        busca = st.text_input("🔍 Buscar por Empresa ou Funcionário:").upper()
    with c2:
        mes_atual = datetime.now(fuso_br).strftime("%m/%Y")
        mes_filtro = st.text_input("📅 Mês/Ano (Ex: 04/2026)", value=mes_atual)
    with c3:
        st.write("") 
        if st.button("🔄 Atualizar Lista", use_container_width=True):
            st.rerun()

    try:
        query = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING")
        docs = query.stream()
        
        lista_dados = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            lista_dados.append(d)
        
        if lista_dados:
            # Substitui valores nulos ou NaN por strings vazias para evitar erros
            df = pd.DataFrame(lista_dados).fillna("")
            
            if busca:
                df = df[(df['cliente'].astype(str).str.contains(busca)) | (df['funcionario'].astype(str).str.contains(busca))]
            if mes_filtro:
                df = df[df['mes_ano'] == mes_filtro]
            
            if not df.empty:
                t1, t2 = st.columns(2)
                t1.metric("💰 Total Valor", f"R$ {df['valor'].sum():,.2f}")
                t2.metric("📄 Total Registros", f"{len(df)} docs")
                st.divider()

                for i, row in df.iterrows():
                    icon = "📕" if row['tipo'] == 'pdf' else "🖼️"
                    # Limpeza visual para dados antigos
                    func_v = row['funcionario'] if row['funcionario'] and str(row['funcionario']).lower() != "nan" else "Não informado"
                    cnpj_v = row['cnpj'] if row['cnpj'] and str(row['cnpj']).lower() != "nan" else "Não informado"
                    
                    with st.expander(f"{icon} {row['cliente']} | {func_v} | R$ {row['valor']:.2f}"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**🏢 Empresa:** {row['cliente']} (CNPJ: {cnpj_v})")
                            st.write(f"**👤 Funcionário:** {func_v}")
                            st.write(f"**⏰ Horário:** {row.get('hora', '--:--')}")
                            st.write(f"**📝 Obs:** {row.get('obs', '')}")
                            st.link_button("📂 Abrir Arquivo", row['url'])
                            
                            # LOGICA DE EXCLUSÃO MELHORADA
                            if st.button(f"🗑️ Deletar Registro", key=f"del_{row['id']}"):
                                try:
                                    # Pega o nome do arquivo e verifica se é válido (não é vazio nem "nan")
                                    nome_arq_storage = str(row.get('nome_storage', '')).strip()
                                    
                                    if nome_arq_storage and nome_arq_storage.lower() != "nan":
                                        try:
                                            # Tenta apagar, mas se não achar o arquivo, não trava o programa
                                            bucket.blob(f"comprovantes/{nome_arq_storage}").delete()
                                        except Exception:
                                            pass 
                                            
                                    # Apaga o registro do banco de dados (isso sempre funciona se o ID existir)
                                    db.collection("pagamentos").document(row['id']).delete()
                                    st.success("Registro removido!")
                                    st.rerun()
                                except Exception as err:
                                    st.error(f"Erro ao apagar: {err}")

                        with col_b:
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url'], use_container_width=True)
                            else:
                                st.info("Sem preview.")
            else:
                st.info("Nenhum registro encontrado.")
        else:
            st.info("O sistema está vazio.")
            
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
