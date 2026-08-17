import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import time
import concurrent.futures

st.set_page_config(page_title="Corretor de Provas", page_icon="📝")
st.title("📝 Corretor Automático de Gabaritos")

with st.sidebar:
    st.header("Configurações")
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ Chave conectada automaticamente!")
    else:
        api_key = st.text_input("Sua Chave de API:", type="password")
    
    gabarito_oficial = st.text_area("Gabarito Oficial", value="1-A\n2-B\n3-C\n4-D\n5-A")

uploaded_files = st.file_uploader("Arraste as fotos das provas aqui", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

if st.button("Corrigir Provas", type="primary"):
    if not api_key or not uploaded_files:
        st.warning("Preencha a chave e envie as fotos.")
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.6-flash') 
        
        prompt = f"""
        Você é um assistente de correção de provas. Analise a imagem.
        Gabarito oficial:
        {gabarito_oficial}
        
        Sua tarefa:
        1. Identifique o nome do aluno.
        2. Verifique as alternativas. Se houver mais de uma marcação na mesma questão, ela está ERRADA.
        3. Compare com o gabarito oficial e conte os acertos.
        
        Retorne APENAS um JSON válido com esta estrutura:
        {{
            "nome_do_aluno": "Nome",
            "respostas_do_aluno": "1-A, 2-B...",
            "total_acertos": 3,
            "multiplas_marcacoes": false
        }}
        
        Regra de ouro: O campo "multiplas_marcacoes" DEVE ser true se o aluno marcou mais de uma opção na mesma questão. Caso contrário, retorne false.
        """

        def corrigir_uma_prova(file):
            max_tentativas = 3
            
            for tentativa in range(max_tentativas):
                try:
                    img = Image.open(file)
                    img.thumbnail((1024, 1024))
                    
                    response = model.generate_content(
                        [prompt, img],
                        generation_config={"response_mime_type": "application/json"}
                    )
                    
                    dados = json.loads(response.text)
                    
                    # Coloca o emoji vermelho se teve múltipla marcação
                    if dados.get("multiplas_marcacoes") == True:
                        dados["nome_do_aluno"] = str(dados["nome_do_aluno"]) + " ❗"
                    
                    # Limpa a coluna extra
                    if "multiplas_marcacoes" in dados:
                        del dados["multiplas_marcacoes"]
                        
                    return dados
                    
                except Exception as e:
                    erro = str(e)
                    # SE O ERRO FOR O LIMITE DO GOOGLE (429)
                    if "429" in erro:
                        if tentativa < max_tentativas - 1:
                            # O código dorme por 32 segundos e tenta a mesma foto de novo!
                            time.sleep(32)
                            continue
                        else:
                            return {"nome_do_aluno": f"Erro: Limite do Google atingido", "respostas_do_aluno": "N/A", "total_acertos": 0}
                    else:
                        return {"nome_do_aluno": f"Erro: {erro}", "respostas_do_aluno": "N/A", "total_acertos": 0}

        resultados = []
        progress_bar = st.progress(0)
        
        with st.spinner('Analisando imagens (O sistema fará pausas automáticas se necessário)...'):
            # Enviamos no máximo 2 por vez para não assustar o servidor do Google
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(corrigir_uma_prova, file) for file in uploaded_files]
                
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    resultados.append(future.result())
                    progress_bar.progress((i + 1) / len(uploaded_files))

        if resultados:
            st.success("Correção finalizada!")
            df = pd.DataFrame(resultados)
            df.columns = ["Nome do Aluno", "Respostas do Aluno", "Total de Acertos"]
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar Planilha de Notas",
                data=csv,
                file_name='notas_alunos.csv',
                mime='text/csv',
            )