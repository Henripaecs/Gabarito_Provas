import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import concurrent.futures

# Configuração da página do site
st.set_page_config(page_title="Corretor de Provas", page_icon="📝")
st.title("📝 Corretor Automático de Gabaritos")

st.markdown("""
Faça o upload das fotos das provas. O sistema usará Inteligência Artificial para identificar o nome do aluno, 
ler as respostas e comparar com o gabarito oficial.
""")

# Barra lateral para configurações
with st.sidebar:
    st.header("Configurações")
    
    # Verifica se a chave está salva no cofre invisível do Streamlit
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("✅ Chave de API conectada automaticamente!")
    else:
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
        
        # PROMPT ATUALIZADO: Explicação super clara sobre o true e false
        prompt = f"""
        Você é um assistente de correção de provas. Analise a imagem em anexo.
        O gabarito oficial da prova é:
        {gabarito_oficial}
        
        Sua tarefa:
        1. Identifique o nome do aluno escrito na prova.
        2. Verifique as alternativas. Se houver mais de uma marcação na mesma questão, ela está ERRADA.
        3. Compare com o gabarito oficial e conte os acertos.
        4. Verifique se o aluno fez múltiplas marcações.
        
        Retorne APENAS um JSON válido com a seguinte estrutura:
        {{
            "nome_do_aluno": "Nome Encontrado",
            "respostas_do_aluno": "1-A, 2-B...",
            "total_acertos": 3,
            "multiplas_marcacoes": false
        }}
        
        IMPORTANTE: O campo "multiplas_marcacoes" deve ser true SE o aluno marcou mais de uma opção na mesma questão, e false se estiver tudo normal (apenas uma marcação por questão).
        """

        def corrigir_uma_prova(file):
            try:
                img = Image.open(file)
                img.thumbnail((1024, 1024))
                
                # Forçando o formato JSON para evitar erros de leitura
                response = model.generate_content(
                    [prompt, img],
                    generation_config={"response_mime_type": "application/json"}
                )
                
                dados = json.loads(response.text)
                
                # REGRA DO EMOJI
                if dados.get("multiplas_marcacoes") == True:
                    dados["nome_do_aluno"] = str(dados["nome_do_aluno"]) + " ❗"
                
                # Limpa a coluna extra antes de ir para a tabela
                if "multiplas_marcacoes" in dados:
                    del dados["multiplas_marcacoes"]
                    
                return dados
                
            except Exception as e:
                return {
                    "nome_do_aluno": f"Erro ({file.name}): {str(e)}", 
                    "respostas_do_aluno": "N/A", 
                    "total_acertos": 0
                }

        resultados = []
        progress_bar = st.progress(0)
        
        with st.spinner('Analisando as imagens...'):
            # Reduzimos de 5 para 2 para o Google não bloquear a sua chave gratuita por excesso de velocidade
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(corrigir_uma_prova, file) for file in uploaded_files]
                
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    resultados.append(future.result())
                    progress_bar.progress((i + 1) / len(uploaded_files))

        if resultados:
            st.success("Correção finalizada com sucesso! ⚡")
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