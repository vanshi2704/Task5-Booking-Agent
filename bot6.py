import streamlit as st
import os
import google.generativeai as genai
import datetime
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pytz

# --- CONFIG ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyDW03jShR_m2YnCafu3rPc0gaZ2-HzFf3o")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

CALENDAR_ID = "primary"
SCOPES = ["https://www.googleapis.com/auth/calendar","https://www.googleapis.com/auth/calendar.events"]
SALON_TIMEZONE = "Asia/Kolkata"

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "vanshimehtaa@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "xrbs alac ucfh cdte")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- Salon Services ---
SALON_SERVICES = {
    "Haircut (Men)": {"duration_minutes": 45, "price": 400},
    "Haircut (Women)": {"duration_minutes": 60, "price": 600},
    "Hair Coloring": {"duration_minutes": 120, "price": 2500},
    "Hair Spa": {"duration_minutes": 90, "price": 1500},
    "Manicure": {"duration_minutes": 60, "price": 800},
    "Pedicure": {"duration_minutes": 60, "price": 1000},
    "Facial (Basic)": {"duration_minutes": 60, "price": 1200},
    "Facial (Advanced)": {"duration_minutes": 90, "price": 2000},
    "Body Massage": {"duration_minutes": 90, "price": 2500},
    "Full Body Spa": {"duration_minutes": 120, "price": 3500},
    "Waxing (Full Body)": {"duration_minutes": 90, "price": 1800},
    "Threading & Eyebrows": {"duration_minutes": 30, "price": 200},
}

# --- LTM Storage ---
LTM_FILE = "ltm_data.json"

def load_ltm_data():
    if os.path.exists(LTM_FILE):
        with open(LTM_FILE, "r") as f:
            return json.load(f)
    return []

def save_ltm_data(data):
    with open(LTM_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- Helpers ---
def normalize_indian_phone(raw: str) -> str | None:
    if not raw:
        return None
    s = str(raw).strip()
    s = re.sub(r"[^\d+]", "", s)       # keep digits and +
    s = re.sub(r"^\+91", "", s)        # strip +91
    s = re.sub(r"^0", "", s)           # strip leading 0
    s = re.sub(r"\D", "", s)           # remove non-digits
    return s if len(s) == 10 else None

# --- Calendar setup ---
def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

def check_availability(calendar_service, start_dt_local, duration_mins):
    """Check Google Calendar free/busy for given slot (timezone-correct)."""
    salon_tz = pytz.timezone(SALON_TIMEZONE)
    if start_dt_local.tzinfo is None:
        start_local = salon_tz.localize(start_dt_local)
    else:
        start_local = start_dt_local.astimezone(salon_tz)
    end_local = start_local + datetime.timedelta(minutes=duration_mins)

    start_utc = start_local.astimezone(pytz.utc)
    end_utc = end_local.astimezone(pytz.utc)

    # RFC3339 timestamps with Z
    time_min = start_utc.isoformat().replace("+00:00", "Z")
    time_max = end_utc.isoformat().replace("+00:00", "Z")

    body = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": CALENDAR_ID}]}
    try:
        resp = calendar_service.freebusy().query(body=body).execute()
        return not resp["calendars"][CALENDAR_ID]["busy"]
    except Exception as e:
        st.error(f"Calendar check error: {e}")
        return False

def add_google_calendar_event(calendar_service, appointment_details):
    salon_tz = pytz.timezone(SALON_TIMEZONE)
    start_time_naive = datetime.datetime.combine(appointment_details["date"], appointment_details["time"])
    start_time_dt = salon_tz.localize(start_time_naive) # Localize to salon's timezone
    end_time_dt = start_time_dt + datetime.timedelta(minutes=appointment_details["duration"])

    event = {
        "summary": f"{appointment_details['service']} for {appointment_details['name']}",
        "location": "Luxe Salon & Spa, Vadodara",
        "description": (
            f"Client: {appointment_details['name']}\n"
            f"Email: {appointment_details['email']}\n"
            f"Phone: {appointment_details.get('phone','-')}\n"
            f"Service: {appointment_details['service']}\n"
            f"Duration: {appointment_details['duration']} mins\n"
            f"Price: ₹{appointment_details['price']}\n"
        ),
        "start": {"dateTime": start_time_dt.isoformat(), "timeZone": SALON_TIMEZONE},
        "end": {"dateTime": end_time_dt.isoformat(), "timeZone": SALON_TIMEZONE},
        "reminders": {"useDefault": True},
    }
    created = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    return created.get("htmlLink")

# --- Email ---
def send_confirmation_email(user_email, appointment_details):
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = user_email
    msg["Subject"] = "Your Luxe Salon Appointment Confirmation"

    phone_line = f"\n📞 Phone: {appointment_details['phone']}" if appointment_details.get("phone") else ""
    body = f"""
Dear {appointment_details['name']},

Your appointment at Luxe Salon & Spa is confirmed 🎉

📅 Date: {appointment_details['date'].strftime('%A, %d %B %Y')}
⏰ Time: {appointment_details['time'].strftime('%I:%M %p')}
💇 Service: {appointment_details['service']}
⏳ Duration: {appointment_details['duration']} minutes
💰 Price: ₹{appointment_details['price']}{phone_line}

We look forward to pampering you soon!  
Luxe Salon & Spa
"""
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
    return True

# --- Date Preprocessing ---
def preprocess_date_keywords(user_message: str):
    today = datetime.date.today()
    msg = user_message.lower()

    if "day after tomorrow" in msg:
        return user_message.replace("day after tomorrow", str(today + datetime.timedelta(days=2)))
    if "tomorrow" in msg:
        return user_message.replace("tomorrow", str(today + datetime.timedelta(days=1)))
    if "today" in msg:
        return user_message.replace("today", str(today))
    return user_message

# --- Extract booking details ---
def extract_booking_details(user_message):
    prompt = f"""
You are Luxe Salon & Spa’s AI assistant. Extract structured details.

Reply ONLY in JSON with keys:
service, date, time, name, email, phone

- Date must be YYYY-MM-DD if present, else null
- Time must be HH:MM 24-hour if present, else null
- Service must be one of: {list(SALON_SERVICES.keys())}
- If phone seems Indian, return 10 digits (strip +91 or leading 0)

User: "{user_message}"
"""
    response = model.generate_content(prompt)
    text = response.text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
        except:
            return {}
        if "phone" in data and data["phone"]:
            data["phone"] = normalize_indian_phone(data["phone"])
        return data
    return {}

# --- Streamlit App ---
def main():
    st.set_page_config(page_title="💇 Luxe Salon Booking", page_icon="💅", layout="centered")

    st.title("💇 Luxe Salon & Spa AI Booking Assistant")
    calendar_service = get_calendar_service()
    ltm_data = load_ltm_data()

    # Keep your CSS + layout tweaks
    st.markdown("""
        <style>
        div[data-testid="stChatInput"] textarea {
            height: 40px !important;
            font-size: 16px !important;
        }
        div[data-testid="stChatInput"] {
            border-radius: 12px;
            border: 1px solid #ccc;
            margin: 5px;
        }
        .block-container { padding-bottom: 120px; }
        </style>
    """, unsafe_allow_html=True)

    if "chat" not in st.session_state:
        st.session_state.chat = model.start_chat(history=[{
            "role": "user",
            "parts": [f"""
You are Luxe Salon & Spa’s AI booking assistant.
- Act only like a salon receptionist, never generic.
- Services (with duration & price ₹): {SALON_SERVICES}
- Always show services in a Markdown table when asked.
- Python backend will check calendar + send emails when booking is ready.
- Do not say you cannot send emails or calendar invites.
"""]
        }])

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "user_info" not in st.session_state:
        st.session_state.user_info = {"service": None, "date": None, "time": None, "name": None, "email": None, "phone": None}
    if "initial_input_done" not in st.session_state:
        st.session_state.initial_input_done = False
    if "awaiting_phone" not in st.session_state:
        st.session_state.awaiting_phone = False

    # --- Initial name/email stage (unchanged) ---
    if not st.session_state.initial_input_done:
        if not st.session_state.chat_history:
            st.session_state.chat_history.append(("Bot", "Welcome to Luxe Salon & Spa! To help me assist you better, please share your name and email."))

        user_input_name_email = st.chat_input("Enter your name and email...")
        if user_input_name_email:
            extracted_prelim = extract_booking_details(user_input_name_email)
            if extracted_prelim.get("name"):
                st.session_state.user_info["name"] = extracted_prelim["name"]
            if extracted_prelim.get("email"):
                st.session_state.user_info["email"] = extracted_prelim["email"]
            if extracted_prelim.get("phone"):
                st.session_state.user_info["phone"] = extracted_prelim["phone"]

            if st.session_state.user_info["name"] and st.session_state.user_info["email"]:
                found_client = next((item for item in ltm_data if item.get("email") == st.session_state.user_info["email"]), None)
                if found_client:
                    st.session_state.chat_history.append(("Bot", f"Welcome back, {st.session_state.user_info['name']}!"))
                    if found_client.get("phone") and not st.session_state.user_info["phone"]:
                        st.session_state.user_info["phone"] = normalize_indian_phone(found_client["phone"])
                else:
                    st.session_state.chat_history.append(("Bot", f"Nice to meet you, {st.session_state.user_info['name']}!"))

                # Show services
                service_table = "| Service | Duration | Price (₹) |\n|---------|----------|-----------|\n"
                for s, d in SALON_SERVICES.items():
                    service_table += f"| {s} | {d['duration_minutes']} mins | ₹{d['price']} |\n"
                st.session_state.chat_history.append(("Bot", "Here’s our service menu:\n\n" + service_table))
                st.session_state.chat_history.append(("Bot", "Which service would you like to book?"))

                st.session_state.initial_input_done = True
                st.rerun()
            else:
                st.session_state.chat_history.append(("Bot", "I couldn't get your name or email. Please write like: 'My name is <name> and my email is <email@example.com>'"))

    # --- Main chat stage (unchanged flow; added phone & booking guardrails) ---
    else:
        user_input = st.chat_input("Type your message...")
        if user_input:
            st.session_state.chat_history.append(("You", user_input))

            # If we're specifically waiting for phone, handle that first
            if st.session_state.awaiting_phone:
                phone = normalize_indian_phone(user_input)
                if phone:
                    st.session_state.user_info["phone"] = phone
                    st.session_state.awaiting_phone = False
                    st.session_state.chat_history.append(("Bot", "Thanks! Got your phone number. Finalizing your booking now…"))
                else:
                    st.session_state.chat_history.append(("Bot", "That doesn't look like a valid Indian number. Please enter a 10-digit mobile number."))
                    # do not proceed further this turn
                    for role, msg in st.session_state.chat_history:
                        if role == "You":
                            st.chat_message("user").write(msg)
                        else:
                            st.chat_message("assistant").write(msg)
                    return

            processed = preprocess_date_keywords(user_input)
            extracted = extract_booking_details(processed)

            # Save progressive fields
            for k in ["service", "date", "time", "phone"]:
                if extracted.get(k) and not st.session_state.user_info.get(k):
                    if k == "date":
                        try:
                            st.session_state.user_info["date"] = datetime.date.fromisoformat(extracted["date"])
                        except:
                            pass
                    elif k == "time":
                        try:
                            t = extracted["time"].split(":")
                            st.session_state.user_info["time"] = datetime.time(int(t[0]), int(t[1]))
                        except:
                            pass
                    elif k == "phone":
                        st.session_state.user_info["phone"] = normalize_indian_phone(extracted["phone"])
                    else:
                        st.session_state.user_info[k] = extracted[k]

            u = st.session_state.user_info

            # If we have service+date+time, check availability and proceed.
            if u["service"] and u["date"] and u["time"]:
                start_dt_local = datetime.datetime.combine(u["date"], u["time"])
                duration = SALON_SERVICES[u["service"]]["duration_minutes"]
                available = check_availability(calendar_service, start_dt_local, duration)

                if not available:
                    st.session_state.chat_history.append(("Bot", "❌ That slot is already booked. Please choose a different date or time."))
                else:
                    # Ensure we have phone before final booking
                    if not u.get("phone"):
                        st.session_state.awaiting_phone = True
                        st.session_state.chat_history.append(("Bot", "📞 Please share your 10-digit phone number to confirm the booking."))
                    else:
                        # Final booking when all required info is available
                        if all([u["name"], u["email"], u["service"], u["date"], u["time"]]):
                            appointment = {
                                **u,
                                "duration": duration,
                                "price": SALON_SERVICES[u["service"]]["price"],
                            }
                            try:
                                event_link = add_google_calendar_event(calendar_service, appointment)
                                send_confirmation_email(u["email"], appointment)

                                # Save in LTM
                                ltm_entry = {
                                    "name": u["name"],
                                    "email": u["email"],
                                    "phone": u.get("phone"),
                                    "service": u["service"],
                                    "booking_date": u["date"].isoformat(),
                                    "booking_time": u["time"].strftime("%H:%M"),
                                    "timestamp": datetime.datetime.now().isoformat()
                                }
                                ltm_data.append(ltm_entry)
                                save_ltm_data(ltm_data)

                                st.session_state.chat_history.append(("Bot",
                                    f"✅ Your appointment is booked!\n\n"
                                    f"📌 {u['service']}\n"
                                    f"📅 {u['date']}\n"
                                    f"⏰ {u['time']}\n"
                                    f"💰 ₹{appointment['price']}\n\n"
                                    f"A confirmation email has been sent.\n"
                                    f"[View Event]({event_link})"
                                ))
                                # Reset for next session
                                st.session_state.user_info = {"service": None, "date": None, "time": None, "name": None, "email": None, "phone": None}
                                st.session_state.initial_input_done = False
                                st.session_state.awaiting_phone = False
                            except Exception as e:
                                st.session_state.chat_history.append(("Bot", f"⚠️ Booking failed: {e}"))
                        else:
                            # Ask for any missing core detail (very rare here since name/email done initially)
                            missing = [k for k in ["name", "email", "service", "date", "time"] if not u.get(k)]
                            if missing:
                                st.session_state.chat_history.append(("Bot", f"I still need: {', '.join(missing)}"))
            else:
                # Keep the flow conversational via Gemini (optional, unchanged)
                gemini_response = st.session_state.chat.send_message(processed)
                bot_reply = gemini_response.text
                st.session_state.chat_history.append(("Bot", bot_reply))

    # Render chat
    for role, msg in st.session_state.chat_history:
        if role == "You":
            st.chat_message("user").write(msg)
        else:
            st.chat_message("assistant").write(msg)

if __name__ == "__main__":
    main()