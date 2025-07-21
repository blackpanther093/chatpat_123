import gradio as gr
import tempfile
import os
import mimetypes
import requests
import shutil
import asyncio
import zipfile
from tqdm import tqdm
from urllib.parse import urlparse
import time
# LangChain modules
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    UnstructuredWordDocumentLoader,
    TextLoader,
    UnstructuredURLLoader,
)
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_mistralai import MistralAIEmbeddings
from langchain.vectorstores import Chroma

# Set Mistral API Key
os.environ["MISTRAL_API_KEY"] = "your_key"

SUPPORTED_TYPES = ['.pdf', '.docx', '.txt']
extracted_documents = []  # Global document store

def extract_from_file(uploaded_files):
    docs = []
    for file in uploaded_files:
        ext = os.path.splitext(file.name)[1].lower()
        if ext == '.pdf':
            loader = PyMuPDFLoader(file.name)
        elif ext == '.docx':
            loader = UnstructuredWordDocumentLoader(file.name)
        elif ext == '.txt':
            loader = TextLoader(file.name)
        else:
            continue
        extracted = loader.load()
        docs.extend(extracted)
    return docs

def extract_from_urls(url_list):
    docs = []
    for url in url_list.splitlines():
        url = url.strip()
        if "drive.google.com" in url:
            file_id = extract_gdrive_id(url)
            if not file_id:
                continue
            download_url = f"https://drive.google.com/uc?id={file_id}"
            try:
                response = requests.get(download_url)
                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    ext = mimetypes.guess_extension(content_type)
                    if ext not in SUPPORTED_TYPES:
                        continue
                    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                        tmp.write(response.content)
                        tmp_path = tmp.name
                    docs.extend(extract_from_file([open(tmp_path, 'rb')]))
                    os.remove(tmp_path)
            except Exception:
                continue
        else:
            try:
                loader = UnstructuredURLLoader(urls=[url])
                docs.extend(loader.load())
            except:
                continue
    return docs

def extract_gdrive_id(url):
    try:
        parsed = urlparse(url)
        if "/d/" in parsed.path:
            return parsed.path.split("/d/")[1].split("/")[0]
        elif "id=" in parsed.query:
            return parsed.query.split("id=")[1].split("&")[0]
    except:
        return None
    return None

def process_inputs(files, urls):
    global extracted_documents
    all_docs = []
    if files:
        all_docs += extract_from_file(files)
    if urls:
        all_docs += extract_from_urls(urls)

    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    all_docs = splitter.split_documents(all_docs)
    extracted_documents = all_docs

    result = ""
    for doc in all_docs[:20]:
        metadata = doc.metadata
        content = doc.page_content
        result += f"\n---\n📄 Metadata: {metadata}\n📝 Content:\n{content[:500]}...\n"
    return result if result else "❌ No valid content extracted."

async def embed_in_batches(docs, embedding_model: Embeddings):
    all_embeddings = []
    BATCH_SIZE = 50
    RPS = 5
    INTERVAL = 1 / RPS

    batched_docs = [docs[i:i+BATCH_SIZE] for i in range(0, len(docs), BATCH_SIZE)]
    for batch in tqdm(batched_docs, desc="🔗 Embedding"):
        start = time.time()
        texts = [doc.page_content for doc in batch]
        embeddings = await embedding_model.aembed_documents(texts)
        all_embeddings.extend(zip(batch, embeddings))
        elapsed = time.time() - start
        if elapsed < INTERVAL:
            await asyncio.sleep(INTERVAL - elapsed)
    return all_embeddings

def generate_and_save_vectorstore():
    if not extracted_documents:
        return "⚠️ No documents to embed.", None

    try:
        # 1) Create temporary directory for Chroma persistence
        persist_dir = tempfile.mkdtemp(prefix="chroma_")

        # 2) Init embedding model and vectorstore
        embedding_model = MistralAIEmbeddings(model="mistral-embed")

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        embeddings_data = loop.run_until_complete(embed_in_batches(extracted_documents, embedding_model))

        # Unzip docs and embeddings for vectorstore
        documents, embeddings = zip(*embeddings_data)
        texts = [doc.page_content for doc in documents]
        metas = [doc.metadata for doc in documents]

        vectorstore = Chroma(
            collection_name="mistral_store",
            embedding_function=embedding_model,
            persist_directory=persist_dir
        )

        chunk_size = 1000
        total_docs = len(texts)

        for i in range(0, total_docs, chunk_size):
            chunk_texts = texts[i:i+chunk_size]
            chunk_metas = metas[i:i+chunk_size]
            chunk_embeddings = embeddings[i:i+chunk_size]

            vectorstore.add_texts(
                texts=chunk_texts,
                embeddings=chunk_embeddings,
                metadatas=chunk_metas
            )

        vectorstore.persist()

        # 3) Zip the persist_dir folder
        zip_path = "chroma_vectorstore.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(persist_dir):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, persist_dir)
                    zipf.write(abs_path, arcname=rel_path)

        # 4) Cleanup temp folder
        shutil.rmtree(persist_dir)

        return "✅ Vectorstore created and zipped successfully!", zip_path

    except Exception as e:
        return f"❌ Failed to create vectorstore: {str(e)}", None


with gr.Blocks() as app:
    gr.Markdown("## 📚 Document Extractor + Mistral Vectorstore Generator")

    with gr.Row():
        file_input = gr.File(file_types=[".pdf", ".docx", ".txt"], file_count="multiple", label="Upload Files")
        url_input = gr.Textbox(label="Paste URLs (Google Drive / Notion / Slack)", lines=3)

    with gr.Row():
        output_box = gr.Textbox(label="Output (Preview / Status)", lines=20, interactive=False)

    extract_btn = gr.Button("🔍 Extract Text + Metadata")
    embed_btn = gr.Button("✨ Generate Vectorstore with Mistral")

    embed_output_file = gr.File(label="📦 Download Vectorstore (.zip)", visible=False)

    extract_btn.click(fn=process_inputs, inputs=[file_input, url_input], outputs=output_box)

    def handle_embedding():
        status, zip_path = generate_and_save_vectorstore()
        if zip_path:
            return status, gr.update(value=zip_path, visible=True)
        else:
            return status, gr.update(value=None, visible=False)

    embed_btn.click(fn=handle_embedding, outputs=[output_box, embed_output_file])

app.launch()
