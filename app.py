from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import re
from config import BASE_URL, FAQ_ENDPOINT, get_auth_headers  

app = FastAPI(title="LUAN – Infracredit AI Bot")

# Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- EXISTING BOT LOGIC ---------------- #

def fetch_faqs(token: str):
    """Fetch FAQs using frontend user token"""
    url = f"{BASE_URL}{FAQ_ENDPOINT}"
    headers = get_auth_headers(token)
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        try:
            data = response.json()
            total_fnis = sum(len(item.get("fnIs", [])) for item in data.get("data", {}).get("result", []))
            print(f"Loaded {total_fnis} total FNI records across all results.")
            return data
        except Exception as e:
            print("Could not parse JSON:", e)
            return None
    else:
        print(f"Error fetching FAQs: {response.status_code}, {response.text}")
        return None


# 🔧 Helper to remove filler tokens that cause overmatching
def clean_tokens(tokens):
    """Remove generic filler words that cause false positives"""
    stop_words = {
        "about", "on", "for", "of", "the", "a", "an", "me", "show",
        "list", "display", "find", "fetch", "tell", "give", "can", "you",
        "issues", "negotiated", "type", "document", "clause", "client"
    }
    return [t for t in tokens if t not in stop_words and len(t) > 1]


# ✅ Improved precise matching logic
def search_faqs(query, faq_data):
    results = []
    if not faq_data or "data" not in faq_data:
        return results

    query = query.strip().lower()
    if not query:
        return results

    # Tokenize the query and clean filler words
    query_tokens = clean_tokens(query.split())
    if not query_tokens:
        return results

    faq_items = faq_data["data"].get("result", [])

    for item in faq_items:
        clause_name = item.get("name", "").lower()
        doc_type = item.get("documentTypeName", "").lower()
        fnis = item.get("fnIs", [])

        for fn in fnis:
            question = fn.get("question", "").lower()
            response = fn.get("response", "")
            clause = fn.get("clauseName", clause_name).lower()
            document_type = fn.get("documentTypeName", doc_type).lower()
            submitted_by = fn.get("submittedByUserName", "Unknown User")

            combined_text = f"{question} {clause} {document_type}"

            # ✅ Require *all tokens* to appear, not just one
            if all(token in combined_text for token in query_tokens):
                results.append({
                    "question": fn.get("question"),
                    "answer": response,
                    "clause": clause,
                    "documentType": document_type,
                    "submittedBy": submitted_by
                })

    return results


# Greeting check
def is_greeting(text):
    greetings = [
        "hi", "hello", "hey", "good morning", "good afternoon",
        "good evening", "what's up", "whatsup", "good day", "greetings"
    ]
    text = text.lower()
    return any(word in text for word in greetings)


# Detect fuzzy-style queries
def contains_fuzzy_command(text):
    fuzzy_keywords = [
        "show", "show me", "display", "find", "fetch", "list",
        "search", "search for", "view", "tell me", "tell me about",
        "give me", "can you show", "show me fni for", "give me fni for"
    ]
    text = text.lower().strip()
    return any(text.startswith(keyword) for keyword in fuzzy_keywords)


# ✅ Clean fuzzy prefixes & filler words
def clean_fuzzy_query(text):
    """Clean natural language query prefixes and filler words"""
    text = text.lower().strip()

    # Remove leading fuzzy prefixes
    patterns = [
        r"^(show|show me|give me|tell me|list|display|find|fetch|search|search for|view|can you show|what are|what is|tell me about)\s+"
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove filler words that dilute search precision
    fillers = r"\b(about|type|document|clause|client|issues|negotiated|on|for|of|the|a|an|me|show|list|display|find|fetch|tell|give|can|you|fni)\b"
    text = re.sub(fillers, "", text, flags=re.IGNORECASE)

    # Clean extra spaces
    return re.sub(r"\s+", " ", text).strip()


# Welcome message builder
def intro_message(faq_data):
    clause_names = [item.get("name", "") for item in faq_data["data"]["result"] if item.get("name")]
    doc_names = [item.get("documentTypeName", "") for item in faq_data["data"]["result"] if item.get("documentTypeName")]
    client_types = [item.get("clientTypeName", "") for item in faq_data["data"]["result"] if item.get("clientTypeName")]

    clause_example = clause_names[0] if clause_names else "Clause 1"
    doc_example = doc_names[0] if doc_names else "Document 1"
    client_example = client_types[0] if client_types else "Client 1"

    return {
        "welcome": {
            "title": "Hi, I’m LUAN, Infracredit’s AI Bot.",
            "intro": "Ask me things like:",
            "examples": [
                f"→ Show me negotiated issues about document type \"{doc_example}\"",
                f"→ Tell me about FNI for clause \"{clause_example}\"",
                f"→ List issues in client type \"{client_example}\"",
                f"→ Give me FNI for \"{clause_example}\""
            ]
        }
    }


# ---------------- FASTAPI WRAPPER ---------------- #

class QueryRequest(BaseModel):
    query: str


@app.get("/")
def root():
    """Welcome endpoint for bot"""
    return {"message": "LUAN – Infracredit AI Bot API is running"}


@app.get("/welcome")
def get_welcome(token: str = Header(...)):
    """Show welcome message when user opens bot"""
    faq_data = fetch_faqs(token)
    if not faq_data:
        raise HTTPException(status_code=500, detail="Failed to fetch FAQs from server.")
    return intro_message(faq_data)


@app.post("/chat")
def chat_with_bot(request: QueryRequest, token: str = Header(...)):
    """Main chat endpoint"""
    faq_data = fetch_faqs(token)
    if not faq_data:
        raise HTTPException(status_code=500, detail="Failed to fetch FAQs from server.")

    user_input = request.query.strip()

    # Check for greetings
    if is_greeting(user_input):
        return intro_message(faq_data)

    # Handle fuzzy queries like "show me", "give me"
    if contains_fuzzy_command(user_input):
        cleaned_query = clean_fuzzy_query(user_input)
        print(f"Detected fuzzy input. Cleaned query → '{cleaned_query}'")

        if not cleaned_query:
            return {"response": "Please specify what you'd like me to show, e.g. 'Show me FNI for Guarantee Agreement'."}

        matches = search_faqs(cleaned_query, faq_data)
    else:
        print(f"Normal keyword search for: '{user_input}'")
        matches = search_faqs(user_input, faq_data)

    if matches:
        return {"response": matches}
    else:
        return {
            "response": "Hmm, I couldn’t find any match for that. Try asking differently, e.g. 'Show me FNI in document type Guarantee Agreement'."
        }
