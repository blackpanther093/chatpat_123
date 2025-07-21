from rag import get_rag_context
from flask import Flask, request, jsonify, redirect, url_for, render_template, flash, session
import requests
import uuid
import base64
import json
import os
from collections import defaultdict
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import timedelta
import urllib.parse
# import feedparser
# import wikipediaapi
# from duckduckgo_search import DDGS
# import trafilatura
from bs4 import BeautifulSoup
import urllib.parse
import hashlib
import time
import trafilatura
import concurrent.futures
from flask_dance.contrib.google import make_google_blueprint, google
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer

app = Flask(__name__)
app.secret_key = 'super-secret-key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

app.config['SQLALCHEMY_DATABASE_URI'] = (
    'your-db-uri'  # e.g., 'mysql+mysqlconnector://user:password@host/dbname'
)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'connect_args': {
        'ssl_disabled': False  # ✅ This tells mysqlconnector to use SSL
    }
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = False  # True for HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_PROTECTION'] = "strong"
# app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your mail'
app.config['MAIL_PASSWORD'] = 'your password'  # Not your Gmail password
app.config['MAIL_DEFAULT_SENDER'] = 'sender mail'


db = SQLAlchemy(app)
mail = Mail(app)

class ChatSession(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = db.Column(db.String(100), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # <== changed from False to True
    # One-to-many: One chat session → Many messages
    messages = db.relationship('ChatMessage', backref='chat_session', lazy=True, cascade='all, delete-orphan')
    user = db.relationship("User", back_populates="chats")  # ✅ Needed if you're using back_populates
    org_code = db.Column(db.String(20), db.ForeignKey('organizations.org_code'), nullable=True)

class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(36), db.ForeignKey('chat_session.id'))
    role = db.Column(db.String(10))
    # content = db.Column(db.Text)
    content = db.Column(LONGTEXT)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    # One-to-many: One user → Many chat sessions
    confirmed = db.Column(db.Boolean, default=False)
    chats = db.relationship('ChatSession', back_populates='user', lazy=True, cascade='all, delete-orphan')
    org_code = db.Column(db.String(20), db.ForeignKey('organizations.org_code'), nullable=True)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Organization(db.Model):
    __tablename__ = "organizations"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    org_code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Load from env or hardcode if testing
GOOGLE_CLIENT_ID = 'google_id'
GOOGLE_CLIENT_SECRET = 'secret_id'

google_bp = make_google_blueprint(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    scope=[
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid"
    ],
    # redirect_url="/login/google/authorized"
)
app.register_blueprint(google_bp, url_prefix="/login")

# DATA_FILE = "chat_data.json"

platform = "https://openrouter.ai/api/v1/chat/completions"
api_key = "api_key_here"
groq_platform = "https://api.groq.com/openai/v1/chat/completions"
groq_api_key = "api_key_here"
GITHUB_API_KEY = "api_key_here"
# Endpoint and headers
GITHUB_MODEL_ENDPOINT = "https://models.github.ai/inference/chat/completions"

# MODEL_ALIASES = {
#     "llama3-70b-8192": "llama-3-70b",
#     "llama3-8b-8192": "llama-3-8b"
# }

def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(app.secret_key)
    return serializer.dumps(email, salt='email-confirm-salt')

def confirm_token(token, expiration=3600):  # 1 hour
    serializer = URLSafeTimedSerializer(app.secret_key)
    try:
        email = serializer.loads(token, salt='email-confirm-salt', max_age=expiration)
    except Exception:
        return False
    return email

def safe_fetch(url, timeout=6):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(trafilatura.fetch_url, url)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            return None

def estimate_tokens(content):
    if isinstance(content, (dict, list)):
        content = json.dumps(content)
    return int(len(content) / 3.5)  # ~3.5 characters per token is more accurate

def serialize_content(content):
    if isinstance(content, (dict, list)):
        return json.dumps(content)
    return content  # leave string as-is

def safe_json_load(content):
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content

def build_rag_query(messages, current_question, max_recent_qs=2):
    # Extract last N user questions
    user_questions = []
    for msg in reversed(messages):
        if msg["role"] == "user":
            if isinstance(msg["content"], str):
                user_questions.append(msg["content"])
            elif isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "text":
                        user_questions.append(block["text"])
            if len(user_questions) >= max_recent_qs:
                break

    user_questions.reverse()  # keep order chronological
    full_rag_query = "\n".join(user_questions + [current_question])
    return full_rag_query.strip()

@app.route('/confirm/<token>')
def confirm_email(token):
    email = confirm_token(token)
    if not email:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Account not found.', 'danger')
        return redirect(url_for('register'))

    if user.confirmed:
        flash('Account already confirmed. Please login.', 'success')
    else:
        user.confirmed = True
        db.session.commit()
        flash('You have confirmed your account. Thanks!', 'success')

    return redirect(url_for('login'))

@app.route('/')
# @login_required
def home():
    if current_user.is_authenticated:
        recent_chat = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.updated_at.desc()).first()
    else:
        recent_chat = ChatSession.query.filter_by(user_id=None).order_by(ChatSession.updated_at.desc()).first()
    chat_id = recent_chat.id if recent_chat else None
    print(f"[DEBUG] Current User: {current_user}")
    return render_template('chat.html', chat_id=chat_id)

@app.route("/login/google/authorized")
def google_authorized():
    if not google.authorized:
        return redirect(url_for("home"))

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Failed to fetch user info from Google.", "danger")
        return redirect(url_for("home"))

    info = resp.json()
    email = info.get("email")
    name = info.get("name", email.split("@")[0])

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(username=name, email=email, password_hash="google_oauth")
        db.session.add(user)
        db.session.commit()

    login_user(user)
    print("[DEBUG] Logged in user:", current_user)
    flash("✅ Google Login successful", "success")
    return redirect(url_for("home"))  # ✅ THIS IS THE FIX

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash("User already exists.")
            return redirect(url_for('register'))

        # ✅ Create but don't commit yet
        new_user = User(username=username, email=email)
        new_user.set_password(password)

        # ✅ Generate confirmation token
        token = generate_confirmation_token(email)
        confirm_url = url_for('confirm_email', token=token, _external=True)

        # ✅ Prepare confirmation email
        html = render_template('activate_email.html', confirm_url=confirm_url)
        subject = "Please confirm your email"

        try:
            msg = Message(subject=subject, recipients=[email], html=html)
            mail.send(msg)
            # ✅ Save user only if mail is successfully sent
            db.session.add(new_user)
            db.session.commit()
            flash("A confirmation email has been sent to your email address.", "info")
        except Exception as e:
            print("[MAIL ERROR]", e)
            flash("Could not send confirmation email. Contact support.", "danger")
            return redirect(url_for('register'))

        return redirect(url_for('login'))

    return render_template("login.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            # ✅ Block unconfirmed users
            if not user.confirmed:
                flash("Please confirm your email before logging in.", "warning")
                return redirect(url_for('login'))

            login_user(user, remember=True)
            flash("✅ Login successful.", "success")
            return redirect(url_for('home'))

        else:
            flash("Invalid username or password.", "danger")
            return redirect(url_for('login'))

    return render_template("login.html")


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for('home'))

@app.route('/ask', methods=['POST'])
# @login_required
def ask():
    q = request.form.get('question', '').strip()
    model = request.form.get('ai_model', 'mistralai/mistral-7b-instruct')
    temp = float(request.form.get("temperature", 0.5))
    session_id = request.form.get("chat_id", str(uuid.uuid4()))
    try:
        uuid.UUID(session_id)
    except ValueError:
        session_id = str(uuid.uuid4())

    image_files = request.files.getlist("images")
    web_search_enabled = request.form.get("web_search_enabled", "false").lower() == "true"


    if not q:
        return jsonify({"error": "Question cannot be empty."}), 400

    print(f"[ASK] Question: '{q}' | Model: {model} | Temp: {temp} | Web Search: {web_search_enabled}")

    # model = MODEL_ALIASES.get(model, model)
    classification_models = {"meta-llama/llama-prompt-guard-2-86m"}

    image_blocks = []
    for image_file in image_files:
        if image_file and image_file.filename != '':
            img_b64 = base64.b64encode(image_file.read()).decode("utf-8")
            image_blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
            })

    prompt = q.strip()
    search_results_text = ""
    # 📚 Add RAG results to the prompt
    chat = db.session.get(ChatSession, session_id)
    if chat:
        if current_user.is_authenticated:
            if chat.user_id != current_user.id:
                return jsonify({"error": "You cannot access another user's chat."}), 403
        elif chat.user_id is not None:
            return jsonify({"error": "This chat belongs to a registered user. Please log in."}), 403
    else:
        db.session.add(ChatSession(id=session_id, user_id=current_user.id if current_user.is_authenticated else None))
        db.session.commit()

    # ✅ Now safe to fetch messages
    raw_messages = ChatMessage.query.filter_by(chat_id=session_id).order_by(ChatMessage.created_at).all()

    # raw_messages = ChatMessage.query.filter_by(chat_id=session_id).order_by(ChatMessage.created_at).all()
    messages = [{
        "role": m.role,
        "content": safe_json_load(m.content)
    } for m in raw_messages if m.role == "user"]
    print(f"[DEBUG] Raw messages: {json.dumps(messages, indent=2)}")
    # rag_query = build_rag_query(messages, q)
    rag_query = prompt  # Use the current question directly for RAG
    greeting_keywords = {
    "hi", "hello", "hey", "bye", "goodbye", "thanks", "thank you", "yo", "hola", "namaste",
    "sup", "what's up", "how are you", "ok", "okay", "k", "fine", "nice", "cool",
    "hii", "heyy", "heyyy", "yoo", "thankyou", "no thanks", "no thank you", "alright",
    "good", "great", "good morning", "good night", "morning", "night", "gn", "gm",
    "test", "testing", "hello there", "just checking", "trial", "okay bye", "hm", "hmm", "hmmm",
    "yo bro", "yo dude", "yo man", "yo girl", "wassup", "yo what's up", "yo what's going on"
    }
    prompt_clean = prompt.lower().strip()

    if prompt_clean in greeting_keywords or len(prompt_clean.split()) <= 2:
        rag_context = ""
    else:
        fallback_keywords = {
        "he", "she", "it", "this", "that", "they", "his", "her", "their", "them",
        "where", "when", "which", "who", "whom", "whose", "there", "those",
        "did", "does", "do", "was", "were", "had", "has", "have",
        "one", "ones", "someone", "something", "anyone", "anything"
        }
        tokens = set(prompt.lower().split())
        uses_pronouns = any(word in tokens for word in fallback_keywords)
        if uses_pronouns:
        # If question has vague pronouns, directly use full history
            rag_history_query = build_rag_query(messages, prompt)
            rag_context = get_rag_context(rag_history_query)
        else:
            rag_query = prompt
            rag_context = get_rag_context(rag_query)
            if not rag_context or rag_context.strip() == "":
                # Combine recent history (e.g., last 2 user questions) with the current question
                rag_history_query = build_rag_query(messages, q)
                rag_context = get_rag_context(rag_history_query)

    if rag_context and rag_context.strip() != "":
        search_results_text += f"\n🔗 Retrieved from private knowledge base:\n\n{rag_context}\n\n"

    
    if web_search_enabled:
        print(f"Performing web search for: {q}")
        wiki_summary = get_wikipedia_summary(q)
        ddg_snippets = get_duckduckgo_snippets(q)
        print(f"[DEBUG] Wikipedia Summary: {wiki_summary if wiki_summary else 'None'}")
        print(f"[DEBUG] DuckDuckGo Snippets: {ddg_snippets[:1000]} results found")
        # gdelt_news = get_gdelt_rss(q)
        if not wiki_summary and not ddg_snippets:
            search_results_text = "\n🔎 Web search enabled, but no useful results were found.\n\n"
        search_results_text += f"""
            📌 The user asked: "{q}"

            🔎 Web Search has been enabled. Here are summarized results from Wikipedia and DuckDuckGo.

            ------------------------------------------
        """

        if wiki_summary:
            search_results_text += f"Wikipedia Summary:\n{wiki_summary}\n\n"
        # if gdelt_news:
        #     search_results_text += "GDELT News Headlines:\n"
        #     for item in gdelt_news:
        #         search_results_text += f"- {item['title']}\n{item['url']}\n"
        #         if item['content']:
        #             search_results_text += f"Snippet: {item['content']}\n"
        #         search_results_text += "\n"
        if ddg_snippets:
            search_results_text += "DuckDuckGo Snippets:\n"
            for item in ddg_snippets:
                if isinstance(item, dict) and 'url' in item and 'content' in item:
                    search_results_text += f"[{item['url']}]\n{item['content']}\n\n"
                else:
                    search_results_text += f"{str(item)}\n\n"
        
        # print("[DEBUG] DDG Snippets:", ddg_snippets)
        search_results_text += "\n✅ End of Web Results.\n\n"
        print(f"[DEBUG] Search results text: {search_results_text[:300]}...")

    if image_blocks and model in [
            "gpt-4o", "openai/gpt-4.1", "llava", "gemini-pro-vision",
            "qwen/qwen2.5-vl-32b-instruct:free", "meta-llama/llama-4-maverick-17b-128e-instruct",
            "nvidia/llama-3.3-nemotron-super-49b-v1:free", "meta-llama/llama-4-scout-17b-16e-instruct"
    ]:
            combined_text = f"{search_results_text}\n\n{prompt}".strip()
            user_msg = {
                "role": "user",
                "content": [
                    {"type": "text", "text": combined_text},
                    *image_blocks
                ]
            }
            # ✅ Store user's real message separately (for chat DB)
            raw_user_msg = {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    *image_blocks
                ]
            }

    else:
        user_msg = {
            "role": "user",
            "content": search_results_text + prompt
        }
        raw_user_msg = {
            "role": "user",
            "content": prompt
        }

    if model == "openai/gpt-4.1":
        selected_platform = GITHUB_MODEL_ENDPOINT
        selected_key = GITHUB_API_KEY


    elif model.startswith("meta-llama") or model in [
        "llama-3.3-70b-versatile", "compound-beta", "gemma2-9b-it",
        "mistral-saba-24b", "llama-3-8b",
        "llama3-70b-8192", "deepseek-r1-distill-llama-70b",
        "qwen/qwen3-32b"
    ]:
        selected_platform = groq_platform
        selected_key = groq_api_key
    else:
        selected_platform = platform
        selected_key = api_key

    if model in classification_models:

        # Token-safe history trimming (max 5000 tokens to be safe)
        max_tokens = 4500
        total_tokens = 0
        messages = []

        for msg in reversed(raw_messages):
            role = msg.role
            content = safe_json_load(msg.content)
            tokens = estimate_tokens(content)

            if total_tokens + tokens > max_tokens:
                break

            messages.insert(0, {
                "role": role,
                "content": content
            })
            total_tokens += tokens
        # ✅ FIX START
        # if not messages:
        #     messages = [user_msg]
        messages.append(user_msg)

    else:

        # content = user_msg['content']
        # if isinstance(content, (dict, list)):
        #     content = serialize_content(user_msg['content'])
        # db.session.add(ChatMessage(chat_id=session_id, role='user', content=content))
        db.session.add(ChatMessage(chat_id=session_id, role='user', content=serialize_content(raw_user_msg["content"])))

        db.session.commit()

        # raw_messages = ChatMessage.query.filter_by(chat_id=session_id).order_by(ChatMessage.created_at).all()

        # Token-safe history trimming (max 5000 tokens to be safe)
        max_tokens = 4500
        total_tokens = 0
        messages = []

        for msg in reversed(raw_messages):
            role = msg.role
            content = safe_json_load(msg.content)
            tokens = estimate_tokens(content)

            if total_tokens + tokens > max_tokens:
                break

            messages.insert(0, {
                "role": role,
                "content": content
            })
            total_tokens += tokens
        # if not messages:
        #     messages = [user_msg]
        messages.append(user_msg)
        print(f"[DEBUG] Final messages: {json.dumps(messages, indent=2)}")


    try:
        response = requests.post(
            selected_platform,
            headers={
                "Authorization": f"Bearer {selected_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "temperature": temp,
                "messages": messages
            }
        )

        print(f"[DEBUG] API status: {response.status_code}")
        print(f"[DEBUG] Response: {response.text[:300]}...")

        try:
            data = response.json()
        except Exception as e:
            print(f"[ERROR] Could not parse response JSON: {response.text[:500]}")
            return jsonify({
                "error": "Invalid response from model",
                "raw_response": response.text[:500]
            }), 500

        if "choices" not in data:
            raise ValueError(data.get("error", {}).get("message", "Unknown error"))

        reply_msg = data["choices"][0]["message"]
        usage_info = data.get("usage", {})
        print(f"[USAGE] Prompt: {usage_info.get('prompt_tokens')}, Completion: {usage_info.get('completion_tokens')}, Total: {usage_info.get('total_tokens')}")

        if model not in classification_models:
            db.session.add(ChatMessage(chat_id=session_id, role=reply_msg["role"], content=serialize_content(reply_msg["content"])))
            # ✅ Update session's updated_at when message added
            chat = db.session.get(ChatSession, session_id)
            if chat:
                chat.updated_at = datetime.utcnow()
            db.session.commit()
            history_msgs = ChatMessage.query.filter_by(chat_id=session_id).order_by(ChatMessage.created_at).limit(4).all()
            if len(history_msgs) >= 4:
                # chat = ChatSession.query.get(session_id)
                chat = db.session.get(ChatSession, session_id)
                if chat and (chat.title in ["New Chat", f"Chat {session_id[:8]}", "Auto-Retry"]):
                    try:
                        title_payload = [{
                            "role": m.role,
                            "content": safe_json_load(m.content)
                        } for m in history_msgs]

                        title_resp = requests.post(
                            url_for('generate_title', _external=True),
                            json={"history": title_payload}
                        )
                        if title_resp.ok:
                            title = title_resp.json().get("title", "").strip()
                            if title:
                                chat.title = title
                                db.session.commit()
                    except Exception as e:
                        print(f"[AUTO-TITLE ERROR] ❌ {e}")

        final_answer = reply_msg["content"]
        if isinstance(final_answer, (dict, list)):
            final_answer = json.dumps(final_answer, ensure_ascii=False, indent=2)

        return jsonify({
            "chat_id": session_id,
            "answer": final_answer
        })

    except Exception as e:
        print(f"[ASK ERROR] ❌ {e}")
        return jsonify({"error": f"Backend error: {str(e)}"}), 500

@app.route('/generate_title', methods=['POST'])
def generate_title():
    data = request.get_json()
    history = data.get("history", [])[:4]

    if not history:
        return jsonify({"title": "Untitled"})

    prompt = "Summarize this chat in a short, clear title (max 3 words):\n\n"
    for msg in history:
        role = msg["role"].capitalize()
        content = msg["content"] if isinstance(msg["content"], str) else json.dumps(msg["content"])
        prompt += f"{role}: {content}\n"

    try:
        response = requests.post(
            groq_platform,
            headers={
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-70b-8192",
                "temperature": 0.3,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        data = response.json()
        title = None
        if "choices" in data:
            choice = data["choices"][0]
            if "message" in choice:
                title = choice["message"]["content"].strip().strip('"')
            elif "text" in choice:
                title = choice["text"].strip().strip('"')

        if not title:
            raise ValueError("No valid title found in response.")

        return jsonify({"title": title})

    except Exception as e:
        print(f"[TITLE ERROR] {e}")
        return jsonify({"title": "Auto-Retry"})

@app.route("/new_chat", methods=["POST"])
# @login_required
def new_chat():
    new_chat_id = str(uuid.uuid4())
    # user_id = current_user.id if current_user.is_authenticated else None
    # Get current user_id if logged in, else None
    user_id = current_user.id if current_user.is_authenticated else None
    chat = ChatSession(
        id=new_chat_id,
        title="New Chat",
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    # new_session = ChatSession(user_id=user_id)
    db.session.add(chat)
    db.session.commit()

    # 🧠 Save for guest tracking
    if not current_user.is_authenticated:
        session['chat_id'] = new_chat_id

    return jsonify({"chat_id": new_chat_id})

# @app.route('/chat/<chat_id>')
# @login_required
# def view_chat(chat_id):
#     # chat = ChatSession.query.filter_by(id=chat_id, user_id=current_user.id).first()
#     chat = ChatSession.query.filter_by(id=chat_id).first()
#     if not chat:
#         return jsonify({"error": "Chat not found or unauthorized"}), 404

#     messages = ChatMessage.query.filter_by(chat_id=chat_id).order_by(ChatMessage.created_at).all()
#     history = [{
#         "role": m.role,
#         "content": safe_json_load(m.content)
#     } for m in messages]
#     return jsonify({"chat_id": chat_id, "history": history})

@app.route("/chat/<session_id>")
# @login_required
def get_chat(session_id):
    chat = ChatSession.query.get(session_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    if current_user.is_authenticated:
        if chat.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
    else:
        # Guest: only allow access if chat_id matches AND chat is not owned
        if chat.user_id is not None or session.get("chat_id") != session_id:
            return jsonify({"error": "Unauthorized"}), 403

    messages = ChatMessage.query.filter_by(chat_id=session_id).order_by(ChatMessage.created_at).all()
    formatted_messages = [
        {"role": m.role, "content": safe_json_load(m.content)}
        for m in messages
    ]

    # ✅ Return key as 'messages' (not 'history') to match JS
    return jsonify({
        "chat_id": session_id,
        "messages": formatted_messages
    })

@app.route("/all_chats")
# @login_required
def all_chats():
    if current_user.is_authenticated:
        # Only fetch chats belonging to this logged-in user
        sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    else:
        # For guest, return only session tied to their browser
        chat_id = session.get("chat_id")
        if chat_id:
            session_obj = ChatSession.query.get(chat_id)
            if session_obj and session_obj.user_id is None:
                sessions = [session_obj]
            else:
                sessions = []
        else:
            sessions = []

    return jsonify([
        {"id": s.id, "title": s.title or f"Chat {s.id[:8]}"}
        for s in sessions
    ])

@app.route('/delete_chat/<chat_id>', methods=['DELETE'])
@login_required
def delete_chat(chat_id):
    ChatMessage.query.filter_by(chat_id=chat_id).delete()
    ChatSession.query.filter_by(id=chat_id).delete()
    db.session.commit()
    return jsonify({"success": True})

@app.route('/rename_chat/<chat_id>', methods=['POST'])
@login_required
def rename_chat(chat_id):
    data = request.get_json()
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "No title provided"}), 400

    chat = db.session.get(ChatSession, chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404

    chat.title = title
    db.session.commit()
    return jsonify({"success": True})

def save_chat_data():
    pass

def delete_old_chats():
    cutoff = datetime.utcnow() - timedelta(days=15)

    # Delete messages of old chats
    old_sessions = ChatSession.query.filter(ChatSession.updated_at < cutoff).all()
    for session in old_sessions:
        ChatMessage.query.filter_by(chat_id=session.id).delete()
        db.session.delete(session)

    db.session.commit()
    print(f"[CLEANUP] Deleted {len(old_sessions)} chat(s) older than 15 days.")

# Web search functions (from the provided code)
# wiki_wiki = wikipediaapi.Wikipedia(
#     language='en',    
#     user_agent='MyLegalBot/1.0 (https://example.com)' # Placeholder, replace with a real identifying string
# )

def get_wikipedia_summary(query):
    try:
        # STEP 1: Use search API to get best-matching title
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json"
        }

        search_res = requests.get(search_url, params=params, timeout=5)
        search_data = search_res.json()
        search_results = search_data.get("query", {}).get("search", [])

        if not search_results:
            return None  # No results found

        # STEP 2: Use top search result title
        top_title = search_results[0]["title"]
        encoded_title = urllib.parse.quote(top_title)

        # STEP 3: Get summary for the title
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_title}"
        summary_res = requests.get(summary_url, timeout=5)

        if summary_res.status_code == 200:
            return summary_res.json().get("extract")

        return None
    except Exception as e:
        print("Wikipedia fetch error:", e)
        return None

def get_duckduckgo_snippets(query, max_results=5):
    start_time = time.time()
    MAX_DURATION = 15  # seconds max for entire search
    search_url = "https://html.duckduckgo.com/html/"
    headers = {'User-Agent': 'Mozilla/5.0'}
    data = {'q': query}

    try:
        res = requests.post(search_url, data=data, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []

        for a in soup.find_all('a', class_='result__a', limit=max_results * 2):  # extra links in case some fail
            href = a.get('href')
            if href and href.startswith("http"):
                links.append(href)

        results = []
        seen_hashes = set()

        for url in links:
            if time.time() - start_time > MAX_DURATION:
                print("[DEBUG] Exiting early due to time budget")
                break
            try:
                downloaded = safe_fetch(url, timeout=6)
                if downloaded:
                    content = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
                    if content:
                        content = content.strip()
                        max_len = 1500
                        for i in range(0, len(content), max_len):
                            chunk = content[i:i + max_len]
                            content_hash = hashlib.md5(chunk.encode()).hexdigest()
                            if content_hash not in seen_hashes:
                                seen_hashes.add(content_hash)
                                results.append({
                                    "url": url,
                                    "content": chunk
                                })
                            if len(results) >= max_results:
                                return results
                time.sleep(0.5)
            except:
                continue

        return results
    except Exception as e:
        return []

# @app.route('/force_logout')
# def force_logout():
#     logout_user()
#     if 'google_oauth_token' in session:
#         del session['google_oauth_token']
#     flash("Force logged out.")
#     return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        delete_old_chats()
    port = int(os.environ.get('PORT', 5000))  # Default to 5000 if not on Render
    app.run(host='0.0.0.0', port=port)