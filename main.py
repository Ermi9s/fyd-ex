import base64
import os
import re
from datetime import datetime

import fitz
from PIL import Image
from pyzbar.pyzbar import decode

import easyocr
from rembg import remove


_EASYOCR_READER = None


def encode_image_to_base64(image_path):
    if not image_path or not os.path.exists(image_path):
        return None
    with open(image_path, "rb") as f:
        data = f.read()
    ext = image_path.split('.')[-1].lower()
    mime = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg'] else "image/png"
    encoded = base64.b64encode(data).decode('utf-8')
    return f"data:{mime};base64,{encoded}"


def get_easyocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        languages = ["en"]
        if "AMHARIC" in os.environ.get("SUPPORTED_LANGS", "AMHARIC").upper():
            languages.append("am")
        _EASYOCR_READER = easyocr.Reader(languages, gpu=False, verbose=False)
    return _EASYOCR_READER


DATE_TOKEN_PATTERN = re.compile(r"\d{4}/(?:\d{2}|[A-Za-z]{3,9})/\d{2}")


def normalize_date_token(token):
    cleaned = token.strip().replace('.', '')
    for fmt in ("%Y/%m/%d", "%Y/%b/%d", "%Y/%B/%d"):
        try:
            return datetime.strptime(cleaned, fmt).strftime("%Y/%m/%d")
        except ValueError:
            continue
    return cleaned


def extract_dates_from_text(text):
    return [normalize_date_token(match) for match in DATE_TOKEN_PATTERN.findall(text)]


def extract_dates_near_keyword(text, keyword, window=120):
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return []
    snippet = text[idx: idx + window]
    return extract_dates_from_text(snippet)


def extract_fin(text):
    match = re.search(r"FIN[:\-\s]*([A-Z0-9]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def run_image_ocr(image_paths):
    ocr_map = {path: "" for path in image_paths}
    reader = get_easyocr_reader()
    for path in image_paths:
        try:
            results = reader.readtext(path, detail=1, paragraph=False)
            ocr_map[path] = " ".join(result[1] for result in results)
        except Exception:
            ocr_map[path] = ""
    return ocr_map


def process_face_image(image_path):
    if not image_path or not os.path.exists(image_path):
        return image_path
    
    try:
       
        img_pil = Image.open(image_path)
    
        img_no_bg = remove(img_pil)
        
        processed_path = image_path.replace('.png', '_processed.png').replace('.jpg', '_processed.png').replace('.jpeg', '_processed.png')
        img_no_bg.save(processed_path, 'PNG')
        return processed_path
    except Exception as e:
        print(f"Background removal failed: {e}")
        return image_path


def extract_all_images(pdf_path):
    doc = fitz.open(pdf_path)
    images = {}
    for page in doc:
        for img_index, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image["ext"]
            img_name = f"extracted_{page.number}_{img_index}.{ext}"
            with open(img_name, "wb") as f:
                f.write(image_bytes)
            images[f"extracted_{page.number}_{img_index}"] = img_name
    doc.close()
    return images


def decode_qr(path):
    try:
        img = Image.open(path)
        decoded_objs = decode(img)
        if decoded_objs:
            return decoded_objs[0].data.decode()
    except Exception:
        pass
    return None

def extract_text_data(pdf_path):
    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    data = {}
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]

    try:
        values_start_index = lines.index('Disclaimer: For your personal use only!') + 2
        values = lines[values_start_index:]

        data["dob_ec"] = values[0]
        data["dob_gc"] = values[1]
        data["sex_am"] = values[2]
        data["sex_en"] = values[3]
        data["nationality_am"] = values[4]
        data["nationality_en"] = values[5]
        data["phone_number"] = values[6]
        data["region_am"] = values[7]
        data["region_en"] = values[8]
        data["subcity_am"] = values[9]
        data["subcity_en"] = values[10]
        data["woreda_am"] = values[11]
        data["woreda_en"] = values[12]
        data["fcn"] = values[13].replace(" ", "")
        data["name_am"] = values[14]
        data["name_en"] = values[15]
    except (ValueError, IndexError):
        pass

    return data

def parse_id_card(pdf_path):
    images = extract_all_images(pdf_path)
    image_paths = list(images.values())

    qr_string = None
    qr_image_path = None
    for img_path in image_paths:
        qr_string = decode_qr(img_path)
        if qr_string:
            qr_image_path = img_path
            break


    face_path = image_paths[0] if len(image_paths) > 0 else qr_image_path
    text_data = extract_text_data(pdf_path)


    ocr_data = run_image_ocr(image_paths)

    fin = None
    date_of_issue_ec = None
    date_of_issue_gc = None
    expire_date_ec = None
    expire_date_gc = None
    for text in ocr_data.values():
        if fin is None:
            fin = extract_fin(text)
        if date_of_issue_ec is None or date_of_issue_gc is None:
            issue_dates = extract_dates_near_keyword(text, "Date of Issue")
            if issue_dates:
                date_of_issue_ec = issue_dates[0]
                if len(issue_dates) > 1:
                    date_of_issue_gc = issue_dates[1]
        if expire_date_ec is None or expire_date_gc is None:
            expiry_dates = extract_dates_near_keyword(text, "Date of Expiry")
            if expiry_dates:
                expire_date_ec = expiry_dates[0]
                if len(expiry_dates) > 1:
                    expire_date_gc = expiry_dates[1]
    

    text_data["fin"] = fin
    text_data["date_of_issue_ec"] = date_of_issue_ec
    text_data["date_of_issue_gc"] = date_of_issue_gc
    text_data["expire_date_ec"] = expire_date_ec
    text_data["expire_date_gc"] = expire_date_gc

    # Process face image to remove background
    face_path = process_face_image(face_path)
    
    face_photo_b64 = encode_image_to_base64(face_path)
    qr_image_b64 = encode_image_to_base64(qr_image_path)


    return {
        "dataOfIssue": {
            "amharic": text_data.get("date_of_issue_ec", ""),
            "english": text_data.get("date_of_issue_gc", "")
        },
        "fullName": {
            "amharic": text_data.get("name_am", ""),
            "english": text_data.get("name_en", "")
        },
        "dateOfBirth": {
            "amharic": text_data.get("dob_ec", ""),
            "english": text_data.get("dob_gc", "")
        },
        "sex": {
            "amharic": text_data.get("sex_am", ""),
            "english": text_data.get("sex_en", "")
        },
        "expireDate": {
            "amharic": text_data.get("expire_date_ec", ""),
            "english": text_data.get("expire_date_gc", "")
        },
        "FAN": text_data.get("fcn", ""),
        "phoneNumber": text_data.get("phone_number", ""),
        "region": {
            "amharic": text_data.get("region_am", ""),
            "english": text_data.get("region_en", "")
        },
        "city": {
            "amharic": text_data.get("subcity_am", ""),
            "english": text_data.get("subcity_en", "")
        },
        "kebele": {
            "amharic": text_data.get("woreda_am", ""),
            "english": text_data.get("woreda_en", "")
        },
        "FIN": text_data.get("fin", ""),
        "personelImage": face_photo_b64 or "",
        "qrcodeImage": qr_image_b64 or ""
    }
