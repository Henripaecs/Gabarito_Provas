import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import json
import time

# Configuração da página do site
st.set_page_config(page_title="Corretor de Provas", page_icon="📝")
st.title("📝 Corretor Automático (Modo Diagnóstico)")

st.markdown("""
Esta versão está rodando de forma mais lenta (uma foto por vez, com pausas) 
para evitarmos o bloqueio de velocidade do Google e descobrirmos o motivo do erro.
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
        
        prompt = f"""
        Você é um assistente de correção. Analise a imagem.
        Gabarito oficial:
        {gabarito_oficial}
        
        Retorne APENAS um JSON válido com esta estrutura exata:
        {{
            "nome_do_aluno": "Nome",
            "respostas_do_aluno": "1-A, 2-B...",
            "total_acertos": 3,
            "multiplas_marcacoes": false
        }}
        
        Regra: "multiplas_marcacoes" é true se houver mais de uma marcação na mesma questão, senão false.
        """

        resultados = []
        progress_bar = st.progress(0)
        
        with st.spinner('Analisando uma por uma (modo lento)...'):
            for i, file in enumerate(uploaded_files):
                try:
                    img = Image.open(file)
                    img.thumbnail((1024, 1024))
                    
                    # Envia a imagem para o Google forçando o formato JSON
                    response = model.generate_content(
                        [prompt, img],
                        generation_config={"response_mime_type": "application/json"}
                    )
                    
                    # Isso vai imprimir a resposta bruta da IA no seu terminal do computador
                    print(f"\n--- Resposta da IA para {file.name} ---")
                    print(response.text)
                    print("---------------------------------------\n")
                    
                    # Tenta ler a resposta e transformar em tabela
                    dados = json.loads(response.text)
                    
                    # Adiciona o emoji se necessário
                    if dados.get("multiplas_marcacoes") == True:
                        dados["nome_do_aluno"] = str(dados["nome_do_aluno"]) + " ❗"
                    
                    # Remove a coluna de marcação para não sujar a tabela final
                    if "multiplas_marcacoes" in dados:
                        del dados["multiplas_marcacoes"]
                        
                    resultados.append(dados)
                    
                except Exception as e:
                    # Se algo der errado, a tabela vai mostrar EXATAMENTE o que falhou
                    resultados.append({
                        "nome_do_aluno": f"Erro: {str(e)}", 
                        "respostas_do_aluno": "N/A", 
                        "total_acertos": 0
                    })
                
                # Atualiza a barra de progresso
                progress_bar.progress((i + 1) / len(uploaded_files))
                
                # Pausa de 3 segundos para o Google não achar que é ataque de spam/velocidade
                time.sleep(3)

        # Mostrar os resultados em uma tabela
        if resultados:
            st.success("Teste finalizado!")
            df = pd.DataFrame(resultados)
            df.columns = ["Nome do Aluno", "Respostas do Aluno", "Total de Acertos"]
            st.dataframe(df, use_container_width=True)
