from langchain_mistralai.embeddings import MistralAIEmbeddings
from langchain.vectorstores import Chroma
import os

os.environ["MISTRAL_API_KEY"] = "your_key"  # Set your Mistral API Key here

# Load vector DB only once
embedding_model = MistralAIEmbeddings(model="mistral-embed")
vectorstore = Chroma(
    collection_name="mistral_store",
    embedding_function=embedding_model,
    persist_directory="./chroma_c3v0_d78"
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

def get_rag_context(query: str, min_score: float = 0.55, top_k: int = 3) -> str:
    try:
        # Chroma returns: List[Tuple[Document, score]]
        results = retriever.vectorstore.similarity_search_with_relevance_scores(query, k=10)
    except AttributeError:
        print("⚠️ Could not access similarity scores. Check your retriever or vectorstore.")
        return ""

    # Filter by score threshold
    filtered = [
        (doc, score) for doc, score in results
        if score >= min_score and doc.page_content.strip()
    ][:top_k]

    if not filtered:
        print(f"⚠️ No results found with score >= {min_score}.")
        return ""

    # Format result with source and markdown
    context = ""
    for i, (doc, score) in enumerate(filtered, 1):
        source = doc.metadata.get("source") or doc.metadata.get("file_name") or "Unknown source"
        content = doc.page_content.strip()
        context += f"### 📄 Source: `{source}` (Match {i}, Relevance Score: {score:.2f})\n\n"
        context += content[:1500] + "\n\n---\n\n"

    return context.strip()
