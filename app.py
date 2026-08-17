import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import concurrent.futures  # Biblioteca nativa do Python para processamento paralelo

# Configuração da página do site
st.set_page_config(page_title="Corretor de Provas", page_icon="📝")
st.title("📝 Corretor Automático de Gabaritos (Versão Turbo)")

st.markdown("""
Faça o upload das fotos das provas. O sistema usará Inteligência Artificial para identificar o nome do aluno, 
ler as respostas e comparar com o gabarito oficial **simultaneamente**.
""")

# Barra lateral para configurações
with st.sidebar:
    st.header("Configurações")
    # Verifica se a chave está salva no cofre invisível do Streamlit
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ Chave de API conectada automaticamente!")
    else:
        # Se não achar a chave no cofre, pede para digitar (útil se você compartilhar o site)
        api_key = st.text_input("Sua Chave de API (Gemini):", type="password")
    
    gabarito_oficial = st.text_area(
        "Gabarito Oficial", 
        value="1-A\n2-B\n3-C\n4-D\n5-A",
        help="Digite uma questão por linha"
    )

# Área principal de upload
uploaded_files = st.file_uploader("Arraste as fotos das provas aqui", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if st.button("Corrigir Provas", type="primary"):
    if not api_key:
        st.error("Por favor, insira sua Chave de API na barra lateral.")
    elif not uploaded_files:
        st.warning("Por favor, envie pelo menos uma foto de prova.")
    else:
        # Configurar a IA
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.6-flash') 
        
        prompt = f"""
        Você é um assistente de correção de provas. Analise a imagem em anexo.
        O gabarito oficial da prova é:
        {gabarito_oficial}
        
        Sua tarefa:
        1. Identifique o nome do aluno escrito na prova.
        2. Verifique quais alternativas o aluno marcou.
        3. Compare com o gabarito oficial e conte os acertos.
        
        Retorne APENAS um JSON válido com a seguinte estrutura:
        {{
            "nome_do_aluno": "Nome Encontrado",
            "respostas_do_aluno": "1-A, 2-B...",
            "total_acertos": 3
        }}
        """

        # Função que corrige uma única prova (preparada para rodar várias vezes ao mesmo tempo)
        def corrigir_uma_prova(file):
            try:
                img = Image.open(file)
                # OTIMIZAÇÃO 1: Reduzir a imagem para max 1024x1024 (upload super rápido, sem perder a leitura)
                img.thumbnail((1024, 1024))
                
                response = model.generate_content([prompt, img])
                texto_limpo = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(texto_limpo)
            except Exception as e:
                # Se der erro em uma prova, não trava as outras
                return {
                    "nome_do_aluno": f"Erro na foto: {file.name}", 
                    "respostas_do_aluno": "N/A", 
                    "total_acertos": 0
                }

        resultados = []
        progress_bar = st.progress(0)
        
        with st.spinner('Analisando todas as imagens simultaneamente...'):
            # OTIMIZAÇÃO 2: Executa até 5 correções ao mesmo tempo em paralelo
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                # Dispara todas as tarefas de uma vez
                futures = [executor.submit(corrigir_uma_prova, file) for file in uploaded_files]
                
                # Conforme as respostas vão chegando, atualiza a barra e salva
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    resultados.append(future.result())
                    progress_bar.progress((i + 1) / len(uploaded_files))

        # Mostrar os resultados em uma tabela
        if resultados:
            st.success("Correção finalizada na velocidade da luz! ⚡")
            df = pd.DataFrame(resultados)
            
            # Renomear colunas
            df.columns = ["Nome do Aluno", "Respostas do Aluno", "Total de Acertos"]
            
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Planilha de Notas",
                data=csv,
                file_name='notas_alunos.csv',
                mime='text/csv',
            )