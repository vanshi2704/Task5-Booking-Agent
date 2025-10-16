# 💇 Task 5 – Luxe Salon & Spa AI Booking Agent

This repository contains my **Task 5** submission for the AI Agents Laboratory coursework.  
It showcases a fully functional **AI-powered appointment-booking assistant** for **Luxe Salon & Spa**, built with **Streamlit** and **Google Gemini 2.5 Flash**.

---

## 🧠 Overview
- Interactive UI built with **Streamlit**  
- Uses **Gemini 2.5 Flash** to understand natural-language booking requests  
- Integrates with **Google Calendar API** to check real-time availability  
- Sends **confirmation emails** through Gmail SMTP  
- Stores returning-client history locally in `ltm_data.json`

---

## 🧩 Key Features
✅ Understands conversational booking requests (e.g., *“Book me a haircut tomorrow at 5 PM”*)  
✅ Extracts name, email, phone, service, date and time automatically  
✅ Checks Google Calendar for slot availability  
✅ Creates the calendar event automatically  
✅ Sends confirmation emails to clients  
✅ Provides a clean, chat-style interface for real-time booking

---

## ⚙️ Run Locally (in VS Code or any IDE)

> 💡 You don’t need to run these for submission — they’re just instructions for anyone reviewing or testing the app.

### 1️⃣ Clone this repository
```bash
git clone https://github.com/<your-username>/Task5-Booking-Agent.git
cd Task5-Booking-Agent

### 2️⃣ Install dependencies
```bash
pip install -r requirements.txt

### 3️⃣ Run the Streamlit app
```bash
streamlit run bot6.py
