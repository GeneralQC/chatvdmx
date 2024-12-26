from flask import Flask, request, jsonify
from flask_cors import CORS
import pytesseract
from PIL import Image
import traceback
import re
import requests
from rapidfuzz import fuzz

app = Flask(__name__)
CORS(app)  # เปิดใช้งาน CORS

# กำหนด path ของ Tesseract OCR
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ฟังก์ชันทำความสะอาดข้อความ
def clean_text(text):
    """
    ลบเครื่องหมายพิเศษและช่องว่างซ้ำออกจากข้อความ
    """
    text = re.sub(r"[^\w\s]", "", text)  # ลบเครื่องหมายพิเศษ
    text = re.sub(r"\s+", " ", text)  # ลดช่องว่างซ้ำเหลือ 1 ช่อง
    return text.strip().lower()

# ฟังก์ชันดึงข้อความที่ต้องการจาก OCR
def extract_error_message(text):
    """
    ดึงข้อความเป้าหมายจาก OCR:
    - ดึงข้อความ AgaregateException ถ้ามี
    - ถ้าไม่มี ให้ค้นหาคำสำคัญ เช่น "Cannot access IQC Webservice"
    """
    match = re.search(r"AgaregateException:\s(.*?\.)", text)
    if match:
        return match.group(1).strip()

    # ค้นหาคำสำคัญในข้อความ OCR
    keywords = ["Cannot access IQC Webservice"]
    for keyword in keywords:
        if keyword.lower() in text.lower():
            return keyword.strip()

    return text.strip()  # ส่งข้อความเต็มถ้าไม่มีเป้าหมาย

# ฟังก์ชันค้นหาใน Google Sheet
def search_in_google_sheet(error_message):
    """
    ค้นหาข้อมูลใน Google Sheet โดยใช้ Fuzzy Matching หากข้อความไม่เจอตรง ๆ
    """
    google_sheet_api_url = "https://script.google.com/macros/s/AKfycbw8NmBDeYgjcH7R8j_WRkH-b7Y5z3w-T2OxZ85Y9uWj5fWg3ftsocUJx55053Q5k_tc/exec"
    try:
        print(f"Searching for: {error_message}")

        # ดึงข้อมูลจาก Google Sheet
        response = requests.get(google_sheet_api_url, params={"query": error_message})
        if response.status_code == 200:
            data = response.json()

            if isinstance(data, list):
                best_match = None
                highest_score = 0

                # ค้นหาคำที่คล้ายที่สุด
                for item in data:
                    if isinstance(item, dict) and 'user' in item and 'answer' in item:
                        error_message_cleaned = clean_text(error_message)
                        item_user_cleaned = clean_text(item['user'])
                        score = fuzz.ratio(error_message_cleaned, item_user_cleaned)
                        print(f"Comparing '{error_message_cleaned}' with '{item_user_cleaned}' - Score: {score}")

                        if score > highest_score:  # เก็บข้อความที่มีคะแนนสูงสุด
                            highest_score = score
                            best_match = item

                if highest_score >= 50:  # ลดเกณฑ์ Threshold
                    print(f"Best Match Found: {best_match} with Score: {highest_score}")
                    return best_match['answer']
                else:
                    print("No close match found.")
                    return None
            else:
                print("Invalid response structure from Google Sheet.")
                return None
        else:
            print(f"Failed to query Google Sheet: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error querying Google Sheet: {str(e)}")
        return None

@app.route('/upload_image', methods=['POST'])
def upload_image():
    try:
        # ตรวจสอบว่ามีไฟล์ภาพในคำขอหรือไม่
        if 'image' not in request.files:
            return jsonify({"error": "No image provided"}), 400

        # โหลดภาพและแปลงเป็น RGB
        file = request.files['image']
        img = Image.open(file.stream).convert('RGB')

        # ใช้ Tesseract OCR ตรวจจับข้อความ
        text = pytesseract.image_to_string(img, lang='tha+eng')

        # พิมพ์ข้อความ OCR ที่อ่านได้ใน Console
        print(f"Full OCR Text: {text}")

        # ดึงข้อความที่เป็น Error Message
        error_message = extract_error_message(text)

        if not error_message:
            return jsonify({"response": "No error message found in the text."})

        print(f"Extracted Error Message: {error_message}")

        # ค้นหาคำตอบใน Google Sheet
        answer = search_in_google_sheet(error_message)

        # ส่งผลลัพธ์กลับไปยัง Frontend
        response = {
            "ocr_text": error_message,  # ข้อความที่ OCR อ่านได้
            "response": answer if answer else "Sorry, no relevant information found in our database."
        }
        return jsonify(response)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
