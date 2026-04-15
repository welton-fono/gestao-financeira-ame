import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime
import json
import pandas as pd

# --- CONFIGURAÇÃO DA PÁGINA (Precisa ser a primeira linha) ---
st.set_page_config(page_title="AME - Financeiro PRO", layout="wide", page_icon="🏥", initial_sidebar_state="expanded")

# --- CONEXÃO FIREBASE ---
# Usar o bucket atual: chamdor-amesaude.firebasestorage.app
if not firebase_admin._apps:
    try:
        # Carrega a chave dos Secrets do Streamlit
        creds_dict = json.loads(st.secrets["firebase_key"])
        cred = credentials.Certificate(creds_dict)
        
        # Inicializa o app com o link EXATO do Firebase atual
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'chamdor-amesaude.firebasestorage.app'
        })
    except Exception as e:
        st.error(f"Erro na conexão com o Firebase: {e}")

db = firestore.client()
bucket = storage.bucket()

# --- CABEÇALHO COM LOGOTIPO ---
# Exibir o logotipo e o título
st.image("image_11.png", width=150)
st.title("🏥 AME - Sistema de Comprovantes e Documentos")
st.markdown("Sistema inteligente para organização e faturamento da clínica.")
st.divider()

# --- ABAS DE NAVEGAÇÃO ---
aba_envio, aba_busca = st.tabs(["📥 Lançar Novo Documento", "📊 Painel e Histórico"])

with aba_envio:
    st.subheader("Registrar Novo Lançamento")
    
    with st.form("form_caixa", clear_on_submit=True):
        # Campos divididos em duas colunas para ficar elegante
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("🏢 Nome da Empresa ou Cliente").upper()
            valor = st.number_input("💰 Valor (R$)", min_value=0.0, format="%.2f")
        with col2:
            # ACEITA QUALQUER TIPO DE ARQUIVO
            arquivo = st.file_uploader("📎 Selecione o arquivo (PDF, Imagem, Word, etc.)")
            obs = st.text_area("📝 Observações Adicionais (Opcional)", height=68)
        
        # Botão mais destacado
        enviado = st.form_submit_button("🚀 SALVAR NO SISTEMA", use_container_width=True)
        
        if enviado:
            if cliente and arquivo:
                try:
                    # 1. Definir nome e extensão
                    extensao = arquivo.name.split('.')[-1].lower()
                    agora = datetime.now()
                    nome_arq = f"{agora.strftime('%Y%m%d_%H%M%S')}_{cliente}.{extensao}"
                    
                    # 2. Upload para o Storage
                    blob = bucket.blob(f"comprovantes/{nome_arq}")
                    blob.upload_from_string(arquivo.read(), content_type=arquivo.type)
                    blob.make_public()
                    
                    # 3. Salvar metadados no Firestore com informações de tempo detalhadas
                    db.collection("pagamentos").add({
                        "data_completa": agora.strftime("%Y/%m/%d %H:%M:%S"), # Formato para ordenar fácil
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
                    st.error(f"Erro no envio técnico: {e}")
            else:
                st.warning("⚠️ Preencha o nome da empresa e anexe o arquivo antes de enviar.")

with aba_busca:
    st.subheader("Painel de Controle Financeiro")
    
    # Linha de Filtros organizada em colunas
    col_busca, col_refresh, col_mes = st.columns([2, 1, 1])
    with col_busca:
        busca = st.text_input("🔍 Buscar por Empresa/Cliente:").upper()
    with col_mes:
        # Criar uma lista de meses/anos para o seletor
        meses_lista = [f"{str(i).zfill(2)}/{datetime.now().year}" for i in range(1, 13)]
        mes_atual = datetime.now().strftime("%m/%Y")
        mes_filtro = st.selectbox("📅 Filtrar por Mês", ["Todos"] + meses_lista, index=meses_lista.index(mes_atual) + 1)
    with col_refresh:
        st.write("<br>", unsafe_allow_html=True) # Espaço para alinhar o botão
        if st.button("🔄 Atualizar Dados", use_container_width=True):
            # st.experimental_rerun() foi depreciado, use st.rerun() no Streamlit 1.20+
            st.rerun()

    try:
        # Busca os dados no Firestore, ordenando pela data completa (mais novo primeiro)
        # É importante ter salvado a "data_completa" no formato Y/m/d H:M:S para ordenar certo
        docs = db.collection("pagamentos").order_by("data_completa", direction="DESCENDING").stream()
        dados = [doc.to_dict() for doc in docs]
        
        if dados:
            df = pd.DataFrame(dados)
            
            # Adiciona informações de tempo para documentos antigos que não têm esses campos
            if 'data_completa' not in df.columns:
                # Se não tem data_completa, assume que o campo data é a data antiga e processa
                df['dia'] = df['data'].apply(lambda x: str(x)[0:10] if pd.notnull(x) else "")
                df['hora'] = df['data'].apply(lambda x: str(x)[11:16] if pd.notnull(x) else "")
                df['mes_ano'] = df['data'].apply(lambda x: str(x)[3:10] if pd.notnull(x) else "")

            # Aplica o filtro de busca
            if busca:
                df = df[df['cliente'].str.contains(busca, case=False)]
            
            # Aplica o filtro de mês
            if mes_filtro != "Todos":
                df = df[df['mes_ano'] == mes_filtro]
            
            # --- MOSTRA O RESUMO FINANCEIRO EM MÉTRICAS ---
            if not df.empty:
                st.divider()
                t1, t2, t3 = st.columns(3)
                total_rs = df['valor'].sum()
                qtd_docs = len(df)
                
                # Formata moeda padrão Brasil
                moeda_formatada = f"R$ {total_rs:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                
                t1.metric("💰 Total Movimentado", moeda_formatada)
                t2.metric("📄 Notas Carregadas", f"{qtd_docs} documentos")
                t3.metric("🗓️ Filtro Ativo", "Geral" if mes_filtro == "Todos" else mes_filtro)
                st.divider()
                
                # --- LISTA OS ARQUIVOS COM HORÁRIO ---
                for i, row in df.iterrows():
                    # Define o ícone baseado no tipo de arquivo
                    icon = "🖼️" if row['tipo'] in ['png', 'jpg', 'jpeg'] else "📄"
                    if row['tipo'] == 'pdf': icon = "📕"
                    if row['tipo'] in ['doc', 'docx']: icon = "📘"
                    
                    # Título do expansor com mais detalhes
                    titulo_expander = f"{icon} {row['cliente']} | R$ {row['valor']:,.2f} | 🗓️ {row['dia']} às ⏰ {row['hora']}"
                    
                    with st.expander(titulo_expander):
                        c1, c2 = st.columns([1, 1])
                        with c1:
                            st.info(f"**Empresa:** {row['cliente']}")
                            st.write(f"**Registrado em:** {row['dia']} - {row['hora']}")
                            st.write(f"**Observações:** {row['obs']}")
                            st.link_button("🚀 Abrir Documento Original", row['url'])
                        
                        with c2:
                            # Se for imagem, mostra o preview centralizado
                            if row['tipo'] in ['png', 'jpg', 'jpeg']:
                                st.image(row['url'], use_container_width=True)
                            else:
                                st.warning(f"O documento é um arquivo do tipo .{row['tipo'].upper()}. Clique no botão azul ao lado para visualizá-lo.")
            else:
                st.info("Nenhum comprovante encontrado para este filtro.")
        else:
            st.info("O banco de dados está vazio. Faça o primeiro lançamento na aba '📥 Lançar Novo Documento'.")
    except Exception as e:
        st.error(f"Erro ao organizar dados do Financeiro: {e}")
