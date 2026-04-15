import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd

# --- CONFIGURAÇÃO DA PÁGINA (Precisa ser a primeira linha) ---
st.set_page_config(page_title="AME - Financeiro", layout="wide", page_icon="🏥", initial_sidebar_state="expanded")

# --- CSS CUSTOMIZADO PARA DEIXAR BONITO ---
st.markdown("""
    <style>
    .stMetric {background-color: #f8f9fa; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center;}
    h1 {color: #0056b3;}
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
        st.error(f"Erro na conexão com o Firebase: {e}")

db = firestore.client()
bucket = storage.bucket()

# --- CABEÇALHO ---
st.title("🏥 AME Saúde - Gestão Financeira")
st.markdown("Sistema inteligente para organização de arquivos, comprovantes e faturamento.")
st.divider()

aba_envio, aba_busca = st.tabs(["📤 Lançar Novo Documento", "📊 Painel e Histórico"])

with aba_envio:
    st.subheader("Registrar Novo Lançamento")
    
    with st.form("form_caixa", clear_on_submit=True):
        # Campos divididos em duas colunas para ficar elegante
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("🏢 Nome da Empresa ou Cliente").upper()
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
        with col2:
            arquivo = st.file_uploader("📎 Selecione o arquivo (PDF, Imagem, Word)")
            obs = st.text_area("📝 Observações Adicionais (Opcional)", height=68)
        
        enviado = st.form_submit_button("🚀 SALVAR NO SISTEMA", use_container_width=True)
        
        if enviado:
            if cliente and arquivo:
                try:
                    extensao = arquivo.name.split('.')[-1].lower()
                    agora = datetime.now()
                    nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{cliente}.{extensao}"
                    
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    # Salva os dados de tempo bem detalhados para organização
                    db.collection("pagamentos").add({
                        "data_completa": agora.strftime("%Y/%m/%d %H:%M:%S"), # Formato para o sistema ordenar fácil
                        "dia": agora.strftime("%d/%m/%Y"),
                        "hora": agora.strftime("%H:%M"),
                        "mes_ano": agora.strftime("%m/%Y"),
                        "cliente": cliente,
                        "valor": valor,
                        "url": blob.public_url,
                        "tipo": extensao,
                        "obs": obs
                    })
                    st.success(f"✅ Sucesso! O comprovante de {cliente} foi salvo e organizado no dia {agora.strftime('%d/%m/%Y')} às {agora.strftime('%H:%M')}.")
                except Exception as e:
                    st.error(f"Erro no envio: {e}")
            else:
                st.warning("⚠️ Preencha o nome da empresa e anexe o arquivo antes de enviar.")

with aba_busca:
    st.subheader("Painel de Controle")
    
    # Linha de Filtros
    f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
    with f_col1:
        busca = st.text_input("🔍 Buscar por Empresa/Cliente:").upper()
    with f_col2:
        meses_lista = [f"{str(i).zfill(2)}/{datetime.now().year}" for i in range(1, 13)]
        mes_atual = datetime.now().strftime("%m/%Y")
        mes_filtro = st.selectbox("📅 Filtrar por Mês", ["Todos"] + meses_lista, index=meses_lista.index(mes_atual) + 1)
    with f_col3:
        st.markdown("<br>", unsafe_allow_html=True) # Espaço para alinhar
        if st.button("🔄 Atualizar Dados", use_container_width=True):
            st.rerun()

    try:
        # Puxa os dados organizados do mais novo para o mais velho
        docs = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING").stream()
        dados = [doc.to_dict() for doc in docs]
        
        if dados:
            df = pd.DataFrame(dados)
            
            # Garante que arquivos velhos não quebrem o sistema novo
            if 'data_completa' not in df.columns:
                if 'dia' not in df.columns: df['dia'] = df['data'].apply(lambda x: str(x)[0:10] if pd.notnull(x) else "")
                if 'hora' not in df.columns: df['hora'] = df['data'].apply(lambda x: str(x)[11:16] if pd.notnull(x) else "")
                if 'mes_ano' not in df.columns: df['mes_ano'] = df['data'].apply(lambda x: str(x)[3:10] if pd.notnull(x) else "")
            
            # Aplica a barra de pesquisa
            if busca:
                df = df[df['cliente'].str.contains(busca, case=False)]
            # Aplica o filtro de mês
            if mes_filtro != "Todos":
                df = df[df['mes_ano'] == mes_filtro]
            
            # --- MOSTRA O RESUMO FINANCEIRO ---
            if not df.empty:
                m1, m2, m3 = st.columns(3)
                total_rs = df['valor'].sum()
                qtd_docs = len(df)
                
                # Formata moeda padrão Brasil
                moeda = f"R$ {total_rs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                m1.metric("💰 Total do Período", moeda)
                m2.metric("📄 Notas Lançadas", f"{qtd_docs} documentos")
                m3.metric("🗓️ Filtro Ativo", "Geral" if mes_filtro == "Todos" else mes_filtro)
                st.divider()
                
                # --- LISTA OS ARQUIVOS COM HORÁRIO ---
                for i, row in df.iterrows():
                    icon = "🖼️" if row['tipo'] in ['png', 'jpg', 'jpeg'] else "📄"
                    if row['tipo'] == 'pdf': icon = "📕"
                    if row['tipo'] in ['doc', 'docx']: icon = "📘"
                    
                    titulo = f"{icon} {row['cliente']} | R$ {row['valor']:,.2f} | 🗓️ {row['dia']} às ⏰ {row['hora']}"
                    
                    with st.expander(titulo):
                        c1, c2 = st.columns([1, 1])
                        with c1:
                            st.markdown(f"**Empresa:** {row['cliente']}")
                            st.markdown(f"**Registrado em:** {row['dia']} - {row['hora']}")
                            st.markdown(f"**Observação:** {row.get('obs', 'Nenhuma')}")
                            st.link_button("🚀 Abrir Documento Original", row['url'])
                        with c2:
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url'], use_container_width=True)
                            else:
                                st.info(f"O arquivo é um .{row['tipo'].upper()}. Clique no botão azul para ler.")
            else:
                st.warning("Nenhum comprovante encontrado para este filtro. 🕵️‍♂️")
        else:
            st.info("O banco de dados está limpinho! Faça o primeiro lançamento na outra aba. 📂")
    except Exception as e:
        st.error(f"Erro ao organizar dados: {e}")
