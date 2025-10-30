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
            print(" Could not parse JSON:", e)
            return None
    else:
        print(f"Error fetching FAQs: {response.status_code}, {response.text}")
        return None


def search_faqs(query, faq_data):
    results = []
    if not faq_data or "data" not in faq_data:
        return results

    query = query.lower().strip()
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

            if query in question or query in clause or query in document_type:
                results.append({
                    "question": question,
                    "answer": response,
                    "clause": clause,
                    "documentType": document_type,
                    "submittedBy": submitted_by
                })

    return results


def is_greeting(text):
    greetings = [
        "hi", "hello", "hey", "good morning", "good afternoon",
        "good evening", "what's up", "whatsup", "good day", "greetings"
    ]
    text = text.lower()
    return any(word in text for word in greetings)


def contains_fuzzy_command(text):
    fuzzy_keywords = [
        "show", "show me", "show me all", "display", "find", "fetch", "list", "list all",
        "search", "search for", "view", "tell me", "tell me about", "give me", "can you show",
        "fni", "issue", "issues", "negotiated issue", "negotiated issues", "negotiated",
        "about", "on", "in", "for", "the", "on the",
        "clause", "clauses", "clause title", "document", "document type", "client"
    ]
    text = text.lower()
    return any(keyword in text for keyword in fuzzy_keywords)


def clean_fuzzy_query(text):
    text = text.lower()
    fuzzy_patterns = [
        r"\b(show|show me|show me all|list|list all|display|find|fetch|tell me|tell me about|give me|search|search for|can you show)\b",
        r"\b(fni|issue|issues|negotiated issue|negotiated issues|negotiated)\b",
        r"\b(about|on|in|for|the|on the)\b",
        r"\b(clause|clauses|clause title|document|document type|client)\b"
    ]
    for pattern in fuzzy_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if cleaned else text.strip()


def intro_message(faq_data):
    clause_names = [item.get("name", "") for item in faq_data["data"]["result"] if item.get("name")]
    doc_names = [item.get("documentTypeName", "") for item in faq_data["data"]["result"] if item.get("documentTypeName")]
    client_types = [item.get("clientTypeName", "") for item in faq_data["data"]["result"] if item.get("clientTypeName")]

    clause_example = clause_names[0] if clause_names else "Clause 1"
    doc_example = doc_names[0] if doc_names else "Document 1"
    client_example = client_types[0] if client_types else "Client 1"

    return {
        "welcome": {
            "title": "Hi, I’m LUAN — Infracredit’s AI Lesson Learnt Bot.",
            "intro": "Ask me things like:",
            "examples": [
                f"→ Show me all negotiated issues about document type \"{doc_example}\"",
                f"→ Tell me about FNI for clause \"{clause_example}\"",
                f"→ List issues in client type \"{client_example}\"",
                f"→ What are the negotiated issues on \"{doc_example}\"?",
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

    if is_greeting(user_input):
        return intro_message(faq_data)

    if contains_fuzzy_command(user_input):
        cleaned_query = clean_fuzzy_query(user_input)
        matches = search_faqs(cleaned_query, faq_data)
    else:
        matches = search_faqs(user_input, faq_data)

    if matches:
        return {"response": matches}
    else:
        return {
            "response": "Hmm, I couldn’t find any match for that. Try asking differently, e.g. 'Show me FNI in document type Guarantee Agreement'."
        }

