import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import time
import concurrent.futures
import io
import string
import os
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Corretor de Gabaritos", page_icon="📝", layout="wide")

# --- SISTEMA DE ARQUIVOS PARA O HISTÓRICO ---
PASTA_HISTORICO = "Historico_Corretor"
if not os.path.exists(PASTA_HISTORICO):
    os.makedirs(PASTA_HISTORICO)

# Título Principal
st.title("📝 Corretor Automático de Gabaritos")

# --- BARRA LATERAL: Configurações Gerais ---
with st.sidebar:
    st.header("Configurações do Sistema")
    
    # Busca exclusiva nos Secrets (Pronto para Nuvem)
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ Chave conectada via Secrets!")
    else:
        st.error("⚠️ Chave de API não encontrada nos Secrets do Streamlit Cloud.")
        api_key = None
    
    st.divider()
    
    st.subheader("Dados da Avaliação")
    nome_turma = st.text_input("Nome da Turma:", value="1º Ano A")
    num_questoes = st.number_input("Quantidade de Questões:", min_value=1, max_value=100, value=5, step=1)
    num_alternativas = st.number_input("Alternativas por Questão (Ex: 5 = A até E):", min_value=2, max_value=10, value=5, step=1)
    
    tipo_pontuacao = st.radio(
        "Distribuição de Pontos:",
        ["Mesma pontuação para todas", "Pontuação individual por questão"]
    )
    
    valor_padrao = 1.0
    if tipo_pontuacao == "Mesma pontuação para todas":
        valor_padrao = st.number_input("Valor de cada questão (pts):", min_value=0.1, value=1.0, step=0.5)

# --- CRIAÇÃO DAS ABAS (TABS) ---
aba_nova_correcao, aba_historico = st.tabs(["🚀 Nova Correção", "📂 Histórico de Turmas"])

# ==========================================
# ABA 1: NOVA CORREÇÃO
# ==========================================
with aba_nova_correcao:
    st.subheader("🎯 Gabarito Oficial e Pontuações")
    st.markdown("Marque a alternativa correta e defina a pontuação correspondente para cada questão:")

    gabarito_oficial_dict = {}
    pesos_questoes_dict = {}
    alternativas = list(string.ascii_uppercase)[:num_alternativas]
    alternativas_texto = ", ".join(alternativas[:-1]) + " ou " + alternativas[-1] if len(alternativas) > 1 else alternativas[0]

    with st.container():
        for q in range(1, num_questoes + 1):
            if tipo_pontuacao == "Pontuação individual por questão":
                col_label, col_radio, col_pts = st.columns([1, 4, 2])
            else:
                col_label, col_radio = st.columns([1, 6])
            
            with col_label:
                st.markdown(f"**Q{q}:**")
                
            with col_radio:
                escolha = st.radio(
                    f"Opção Q{q}",
                    alternativas,
                    horizontal=True,
                    key=f"q_{q}",
                    label_visibility="collapsed"
                )
                gabarito_oficial_dict[f"{q}"] = escolha
                
            if tipo_pontuacao == "Pontuação individual por questão":
                with col_pts:
                    pts = st.number_input(f"Pts Q{q}", min_value=0.1, value=1.0, step=0.5, key=f"pts_{q}", label_visibility="collapsed")
                    pesos_questoes_dict[f"{q}"] = pts
            else:
                pesos_questoes_dict[f"{q}"] = valor_padrao

    st.divider()

    st.subheader("📁 Upload das Folhas de Resposta")
    uploaded_files = st.file_uploader("Selecione as fotos dos gabaritos", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if st.button("Corrigir Provas", type="primary"):
        if not api_key:
            st.error("Por favor, configure a chave nos Secrets para iniciar.")
        elif not uploaded_files:
            st.warning("Envie ao menos uma foto para iniciar a correção.")
        else:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-3.6-flash')
            
            gabarito_texto = "\n".join([f"{k}-{v}" for k, v in gabarito_oficial_dict.items()])
            
            prompt = f"""
            Você é um assistente de correção de provas. Analise a imagem em anexo.
            O gabarito oficial com o total de questões é:
            {gabarito_texto}
            
            Sua tarefa:
            1. Identifique o nome do aluno escrito na folha.
            2. Identifique quais alternativas ({alternativas_texto}) o aluno marcou para cada questão numerada.
            3. Se o aluno marcou mais de uma opção, considere a questão como 'DUPLA'.
            4. Retorne a lista com a resposta exata.
            
            Retorne APENAS um JSON com esta estrutura exata:
            {{
                "nome_do_aluno": "Nome Encontrado",
                "respostas": {{"1": "A", "2": "B"}},
                "multiplas_marcacoes": false
            }}
            
            Regra: "multiplas_marcacoes" deve ser true se houver qualquer marcação dupla/rasura, caso contrário false.
            """

            def processar_gabarito(file):
                max_tentativas = 3
                for tentativa in range(max_tentativas):
                    try:
                        img = Image.open(file)
                        img.thumbnail((1024, 1024))
                        response = model.generate_content([prompt, img], generation_config={"response_mime_type": "application/json"})
                        
                        dados = json.loads(response.text)
                        nome = dados.get("nome_do_aluno", "Nome não identificado")
                        respostas_aluno = dados.get("respostas", {})
                        teve_multiplas = dados.get("multiplas_marcacoes", False)
                        
                        total_acertos = 0
                        nota_calculada = 0.0
                        resumo_respostas = []
                        
                        for q_num, alt_correta in gabarito_oficial_dict.items():
                            resp = str(respostas_aluno.get(q_num, "-")).upper().strip()
                            resumo_respostas.append(f"{q_num}-{resp}")
                            
                            if resp == alt_correta:
                                total_acertos += 1
                                nota_calculada += pesos_questoes_dict.get(q_num, 0.0)
                        
                        if teve_multiplas:
                            nome = f"{nome} ❗"
                            
                        return {
                            "Nome do Aluno": nome,
                            "Respostas do Aluno": ", ".join(resumo_respostas),
                            "Total de Acertos": total_acertos,
                            "Nota Final": round(nota_calculada, 2)
                        }
                        
                    except Exception as e:
                        if "429" in str(e):
                            if tentativa < max_tentativas - 1:
                                time.sleep(32)
                                continue
                            return {"Nome do Aluno": f"Erro: Limite da API", "Respostas do Aluno": "N/A", "Total de Acertos": 0, "Nota Final": 0.0}
                        return {"Nome do Aluno": f"Erro: {str(e)}", "Respostas do Aluno": "N/A", "Total de Acertos": 0, "Nota Final": 0.0}

            resultados = []
            progress_bar = st.progress(0)
            
            with st.spinner(f'Processando correções para: {nome_turma}...'):
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(processar_gabarito, file) for file in uploaded_files]
                    for i, future in enumerate(concurrent.futures.as_completed(futures)):
                        resultados.append(future.result())
                        progress_bar.progress((i + 1) / len(uploaded_files))

            if resultados:
                st.success("🎉 Todas as provas foram corrigidas!")
                df = pd.DataFrame(resultados)
                st.dataframe(df, use_container_width=True)
                
                df_excel = df.copy()
                df_excel["Nota Final"] = df_excel["Nota Final"].astype(object)
                
                for i in range(len(df_excel)):
                    linha_excel = i + 2 
                    if tipo_pontuacao == "Mesma pontuação para todas":
                        df_excel.at[i, "Nota Final"] = f"=C{linha_excel}*{valor_padrao}"
                    else:
                        media_pts = sum(pesos_questoes_dict.values()) / len(pesos_questoes_dict)
                        nota_original = df.at[i, "Nota Final"]
                        acertos_originais = df.at[i, "Total de Acertos"]
                        df_excel.at[i, "Nota Final"] = f"={nota_original}+((C{linha_excel}-{acertos_originais})*{media_pts})"
                
                nome_arquivo_seguro = "".join([c for c in nome_turma if c.isalnum() or c == ' ']).strip().replace(' ', '_')
                data_hora = datetime.now().strftime("%d-%m-%Y_%H-%M")
                nome_final = f"Notas_{nome_arquivo_seguro}_{data_hora}"
                
                caminho_csv = os.path.join(PASTA_HISTORICO, f"{nome_final}.csv")
                caminho_xlsx = os.path.join(PASTA_HISTORICO, f"{nome_final}.xlsx")
                
                df.to_csv(caminho_csv, index=False)
                df_excel.to_excel(caminho_xlsx, index=False, sheet_name=nome_turma[:31])
                
                with open(caminho_xlsx, "rb") as file:
                    st.download_button(
                        label="📥 Baixar Planilha Excel Oficial",
                        data=file,
                        file_name=f"{nome_final}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )


# ==========================================
# ABA 2: HISTÓRICO DE TURMAS
# ==========================================
with aba_historico:
    st.subheader("📂 Correções Salvas Anteriormente")
    st.markdown("Aqui você encontra todas as turmas corrigidas na sessão atual.")
    
    arquivos_salvos = [f for f in os.listdir(PASTA_HISTORICO) if f.endswith('.csv')]
    
    if arquivos_salvos:
        arquivos_salvos.sort(reverse=True)
        
        turma_selecionada = st.selectbox("Selecione uma turma corrigida:", arquivos_salvos, format_func=lambda x: x.replace(".csv", "").replace("_", " "))
        
        if turma_selecionada:
            caminho_csv = os.path.join(PASTA_HISTORICO, turma_selecionada)
            caminho_xlsx = caminho_csv.replace(".csv", ".xlsx")
            
            df_historico = pd.read_csv(caminho_csv)
            st.dataframe(df_historico, use_container_width=True)
            
            if os.path.exists(caminho_xlsx):
                with open(caminho_xlsx, "rb") as f:
                    st.download_button(
                        label="📥 Re-baixar Planilha Excel",
                        data=f,
                        file_name=turma_selecionada.replace(".csv", ".xlsx"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_historico"
                    )
    else:
        st.info("Nenhuma correção foi salva ainda nesta sessão.")