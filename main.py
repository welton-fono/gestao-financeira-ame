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
    .stMetric {background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e0e0e0; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);}
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
            nf_emitida = st.checkbox("🧾 Nota Fiscal já foi emitida?") # NOVO CAMPO DE NF
            
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
                        "nf_emitida": nf_emitida, # SALVA O STATUS DA NF
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
    
    # Adicionado um novo filtro para a NF
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        busca = st.text_input("🔍 Buscar por Empresa ou Funcionário:").upper()
    with c2:
        mes_atual = datetime.now(fuso_br).strftime("%m/%Y")
        mes_filtro = st.text_input("📅 Mês/Ano", value=mes_atual)
    with c3:
        filtro_nf = st.selectbox("🧾 Status da NF", ["Todos", "⏳ Pendentes", "✅ Emitidas"])
    with c4:
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
            d['nf_emitida'] = d.get('nf_emitida', False) # Proteção para os arquivos velhos
            lista_dados.append(d)
        
        if lista_dados:
            df = pd.DataFrame(lista_dados).fillna("")
            
            # Aplicação dos Filtros
            if busca:
                df = df[(df['cliente'].astype(str).str.contains(busca)) | (df['funcionario'].astype(str).str.contains(busca))]
            if mes_filtro:
                df = df[df['mes_ano'] == mes_filtro]
            
            if filtro_nf == "⏳ Pendentes":
                df = df[df['nf_emitida'] == False]
            elif filtro_nf == "✅ Emitidas":
                df = df[df['nf_emitida'] == True]
            
            if not df.empty:
                # Novas Métricas de Dashboard
                t1, t2, t3 = st.columns(3)
                t1.metric("💰 Total (Filtro)", f"R$ {df['valor'].sum():,.2f}")
                t2.metric("📄 Total de Registros", f"{len(df)} docs")
                qtd_pendentes = len(df[df['nf_emitida'] == False])
                t3.metric("⚠️ NFs Pendentes", f"{qtd_pendentes} notas")
                st.divider()

                for i, row in df.iterrows():
                    icon = "📕" if row['tipo'] == 'pdf' else "🖼️"
                    func_v = row['funcionario'] if row['funcionario'] and str(row['funcionario']).lower() != "nan" else "N/A"
                    cnpj_v = row['cnpj'] if row['cnpj'] and str(row['cnpj']).lower() != "nan" else "N/A"
                    
                    # Selo visual de status
                    status_nf = "✅ NF Emitida" if row['nf_emitida'] else "⏳ NF Pendente"
                    
                    with st.expander(f"{icon} {row['cliente']} | {func_v} | R$ {row['valor']:.2f} | {status_nf}"):
                        col_a, col_b = st.columns([2, 1])
                        with col_a:
                            st.write(f"**🏢 Empresa:** {row['cliente']} (CNPJ: {cnpj_v})")
                            st.write(f"**👤 Funcionário:** {func_v}")
                            st.write(f"**⏰ Data/Hora:** {row.get('dia', '--')} às {row.get('hora', '--:--')}")
                            st.write(f"**📝 Obs:** {row.get('obs', '')}")
                            st.write(f"**🧾 Status Fiscal:** {status_nf}")
                            st.link_button("📂 Abrir Arquivo Original", row['url'])
                            
                            st.write("---")
                            # BOTÕES DE AÇÃO LADO A LADO
                            act1, act2 = st.columns(2)
                            with act1:
                                # Se estiver pendente, mostra o botão para dar baixa na NF
                                if not row['nf_emitida']:
                                    if st.button(f"✅ Marcar NF Emitida", key=f"ok_{row['id']}", type="primary"):
                                        try:
                                            db.collection("pagamentos").document(row['id']).update({"nf_emitida": True})
                                            st.success("Nota Fiscal baixada com sucesso!")
                                            st.rerun()
                                        except Exception as err:
                                            st.error(f"Erro ao atualizar: {err}")
                            with act2:
                                if st.button(f"🗑️ Deletar Registro", key=f"del_{row['id']}"):
                                    try:
                                        nome_arq_storage = str(row.get('nome_storage', '')).strip()
                                        if nome_arq_storage and nome_arq_storage.lower() != "nan":
                                            try:
                                                bucket.blob(f"comprovantes/{nome_arq_storage}").delete()
                                            except Exception:
                                                pass 
                                                
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
                st.info("Nenhum registro encontrado para estes filtros.")
        else:
            st.info("O sistema está vazio.")
            
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
