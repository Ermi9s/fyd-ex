import fitz
from PIL import Image
from pyzbar.pyzbar import decode
import pytesseract
import re
import base64
import os
import cv2
import numpy as np
from datetime import date
from rembg import remove


def encode_image_to_base64(image_path):
    if not image_path or not os.path.exists(image_path):
        return None
    with open(image_path, "rb") as f:
        data = f.read()
    ext = image_path.split('.')[-1].lower()
    mime = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg'] else "image/png"
    encoded = base64.b64encode(data).decode('utf-8')
    return f"data:{mime};base64,{encoded}"

pytesseract.pytesseract.tesseract_cmd = r'/usr/bin/tesseract'

month_dict = {
    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
    'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
}

def gregorian_to_ethiopian(g_date_str):
    if not g_date_str:
        return None
    parts = g_date_str.split('/')
    if len(parts) != 3:
        return None
    try:
        g_year = int(parts[0])
        g_month = int(parts[1])
        g_day = int(parts[2])
    except ValueError:
        return None
    g_date = date(g_year, g_month, g_day)
    is_leap_g = (g_year % 4 == 0 and (g_year % 100 != 0 or g_year % 400 == 0))
    new_year_day = 11 if not is_leap_g else 12
    new_year_g = date(g_year, 9, new_year_day)
    if g_date < new_year_g:
        et_year = g_year - 8
        days_diff = (new_year_g - g_date).days
        is_leap_et = (et_year % 4 == 0 and (et_year % 100 != 0 or et_year % 400 == 0))
        total_days = 366 if is_leap_et else 365
        et_day_of_year = total_days - days_diff
    else:
        et_year = g_year - 7
        days_diff = (g_date - new_year_g).days
        et_day_of_year = days_diff + 1
    is_leap_et = (et_year % 4 == 0 and (et_year % 100 != 0 or et_year % 400 == 0))
    if et_day_of_year <= 360:
        et_month = (et_day_of_year - 1) // 30 + 1
        et_day = (et_day_of_year - 1) % 30 + 1
    else:
        et_month = 13
        et_day = et_day_of_year - 360
    return f"{et_year:04d}/{et_month:02d}/{et_day:02d}"


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

def parse_qr_data(qr_string):
    if not qr_string:
        return {}
    dlt_index = qr_string.find("DLT:")
    if dlt_index == -1:
        return {"raw_qr": qr_string}

    qr_blob = qr_string[:dlt_index]
    structured_part = qr_string[dlt_index:]
    parts = structured_part.split(":")
    
    if len(parts) < 10:
        return {"qr_blob": qr_blob, "structured_part": structured_part}

    return {
        "qr_blob": qr_blob,
        "type": parts[0],
        "full_name": parts[1],
        "version": parts[2],
        "other_flags": parts[3:7],
        "fcn": parts[7],
        "dob": parts[9] if parts[8] == "D" else None,
        "signature": ":".join(parts[11:]) if len(parts) > 11 and parts[10] == "SIGN" else None
    }



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


    ocr_data = {}
    for img_path in image_paths:
        try:
            text = pytesseract.image_to_string(Image.open(img_path))
            ocr_data[img_path] = text
        except Exception as e:
            ocr_data[img_path] = ""

    fin = None
    date_of_issue_ec = None
    date_of_issue_gc = None
    expire_date_ec = None
    expire_date_gc = None
    for text in ocr_data.values():
        if fin is None and "FIN" in text:
            lines = text.split('\n')
            for line in lines:
                if "FIN" in line:
                    fin_part = line.split('FIN', 1)[1].strip()
                    fin = fin_part
        if (date_of_issue_ec is None or date_of_issue_gc is None) and "Date of Issue" in text:
            lines = text.split('\n')
            for line in lines:
                if "Date of Issue" in line:
                    dates = re.findall(r'\d{4}/(?:\d{2}|\w{3})/\d{2}', line)
                    processed_dates = []
                    for date in dates:
                        parts = date.split('/')
                        if len(parts) == 3:
                            year, month, day = parts
                            if month.isalpha():
                                month = month_dict.get(month, month)
                            processed_date = f"{year}/{month}/{day}"
                            processed_dates.append(processed_date)
                    if len(processed_dates) >= 2:
                        date_of_issue_ec = processed_dates[0]
                        date_of_issue_gc = processed_dates[1]
                    elif len(processed_dates) == 1:
                        date_of_issue_ec = processed_dates[0]
        if expire_date_ec is None or expire_date_gc is None and "Date of Expiry" in text:
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if "Date of Expiry" in line:
                        lines_to_check = lines[i:i+3]  
                        
                        dates = []
                        for check_line in lines_to_check:
                            dates.extend(re.findall(r'\d{4}/(?:\d{2}|\w{3})/\d{2}', check_line))
                 
                        processed_dates = []
                        for date in dates:
                            parts = date.split('/')
                            if len(parts) == 3:
                                year, month, day = parts
                                if month.isalpha():
                                    month = month_dict.get(month, month)
                                processed_date = f"{year}/{month}/{day}"
                                processed_dates.append(processed_date)
                                
                        if len(processed_dates) >= 2:
                            expire_date_ec = processed_dates[0]
                            expire_date_gc = processed_dates[1]
                        elif len(processed_dates) == 1:
                            expire_date_gc = processed_dates[0]
    

    text_data["fin"] = fin
    text_data["date_of_issue_ec"] = date_of_issue_ec
    text_data["date_of_issue_gc"] = date_of_issue_gc
    text_data["expire_date_ec"] = expire_date_ec
    text_data["expire_date_gc"] = expire_date_gc

    if text_data["date_of_issue_gc"] and not text_data["date_of_issue_ec"]:
        text_data["date_of_issue_ec"] = gregorian_to_ethiopian(text_data["date_of_issue_gc"])
    if text_data["expire_date_gc"] and not text_data["expire_date_ec"]:
        text_data["expire_date_ec"] = gregorian_to_ethiopian(text_data["expire_date_gc"])

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
