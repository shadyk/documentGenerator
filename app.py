# At the top of app.py
DEBUG = False  # Change to False in production

from flask import Flask, render_template, request, send_from_directory, flash, redirect, url_for
import os
import platform
import subprocess
import pandas as pd
from docx import Document
from werkzeug.utils import secure_filename
from datetime import datetime
from babel.dates import format_date

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Configuration
app.config['EXCEL_FILE'] = 'data/data.xlsx'
app.config['TEMPLATE_DIR'] = 'data/templates'
app.config['OUTPUT_DIR'] = 'output_docs'
app.config['ALLOWED_EXTENSIONS'] = {'xlsx'}

# Helper functions
arabic_months = {
    "January": "كانون الثاني",
    "February": "شباط",
    "March": "آذار",
    "April": "نيسان",
    "May": "أيار",
    "June": "حزيران",
    "July": "تموز",
    "August": "آب",
    "September": "أيلول",
    "October": "تشرين الأول",
    "November": "تشرين الثاني",
    "December": "كانون الأول"
}

def convert_to_eastern_arabic(number):
    eastern_arabic_digits = {
        "0": "٠", "1": "١", "2": "٢", "3": "٣", "4": "٤",
        "5": "٥", "6": "٦", "7": "٧", "8": "٨", "9": "٩"
    }
    return "".join(eastern_arabic_digits[digit] for digit in str(number))

def replace_text_in_paragraph(paragraph, old_text, new_text):
    full_text = "".join(run.text for run in paragraph.runs)
    if old_text in full_text:
        full_text = full_text.replace(old_text, new_text)
        for run in paragraph.runs:
            run.text = ""
        paragraph.add_run(full_text)

def fill_template(template_path, data_row, output_path):
    if not os.path.exists(template_path):
        return False, f"الملف غير موجود: {template_path}"
    
    try:
        doc = Document(template_path)
    except Exception as e:
        return False, f"لم استطع فتح الملف: {e}"
    
    for key, value in data_row.items():
        key = key.strip()
        for paragraph in doc.paragraphs:
            if f'{{{key}}}' in paragraph.text:
                paragraph.text = paragraph.text.replace(f'{{{key}}}', str(value))
    
    today = datetime.today()
    day = convert_to_eastern_arabic(today.day)
    month_name = arabic_months[today.strftime("%B")]
    year = convert_to_eastern_arabic(today.year)
    arabic_date = f"{day} {month_name} {year}"
    
    for paragraph in doc.paragraphs:
        replace_text_in_paragraph(paragraph, "Today", arabic_date)
    
    doc.save(output_path)
    return True, output_path

def load_data():
    try:
        df = pd.read_excel(app.config['EXCEL_FILE'], header=1)
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        # Convert all values to strings and handle NaN/None values
        df = df.fillna('').astype(str)
        return df
    except Exception as e:
        app.logger.error(f"Error loading Excel file: {e}")
        return pd.DataFrame()

def get_gender_value(row):
    """Extracts and normalizes gender value from row"""
    gender = str(row.get('Gender', row.get('gender', ''))).strip().upper()
    return gender in ('M', 'MALE', '1', 'ذكر')  # Returns True for male, False for female

@app.route('/', methods=['GET', 'POST'])
def index():
    df = load_data()
    search_term = request.form.get('search', '').strip().lower()
    
    if not df.empty:
        if search_term:
            filtered_rows = df.apply(
                lambda row: row.str.contains(search_term, case=False).any(),
                axis=1
            )
            rows = df[filtered_rows].to_dict('records')
        else:
            rows = df.to_dict('records')
    else:
        rows = []
        flash("No data available or error loading data", "warning")
    
    return render_template('index.html', rows=rows, search_term=search_term)

@app.route('/generate', methods=['POST'])
def generate_document():
    try:
        row_index = int(request.form.get('row_index'))
        doc_type = request.form.get('doc_type')
        
        df = load_data()
        if df.empty:
            flash("Error loading Excel file", "error")
            return redirect(url_for('index'))
        
        selected_row = df.iloc[row_index]
        is_male = get_gender_value(selected_row)
        
        # Determine template and filename
        if doc_type == 'baptism':
            template = 'baptisim_template_m.docx' if is_male else 'baptisim_template_f.docx'
            filename = f"معمودية{row_index + 1}.docx"
        else:  # release
            template = 'release_situation_m.docx' if is_male else 'release_situation_f.docx'
            filename = f"اطلاق حال{row_index + 1}.docx"
        
        template_path = os.path.join(app.config['TEMPLATE_DIR'], template)
        output_path = os.path.join(app.config['OUTPUT_DIR'], filename)
        
        # Verify template exists
        if not os.path.exists(template_path):
            flash(f"Template file not found: {template}", "error")
            return redirect(url_for('index'))
        
        success, message = fill_template(template_path, selected_row, output_path)
        
        if success:
#            flash(f"تم إنشاء الملف: {filename}", "success")
            return send_from_directory(app.config['OUTPUT_DIR'], filename, as_attachment=True)
        else:
            flash(message, "error")
            return redirect(url_for('index'))
    
    except Exception as e:
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['OUTPUT_DIR'], filename, as_attachment=True)

@app.route('/debug')
def debug_data():
    try:
        df = load_data()
        if df.empty:
            return {"status": "error", "message": "DataFrame is empty"}
        
        first_row = df.iloc[0].to_dict()
        return {
            "status": "success",
            "columns": list(df.columns),
            "first_row": first_row,
            "gender_info": {
                "raw_value": first_row.get('Gender', 'N/A'),
                "normalized": get_gender_value(df.iloc[0])
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == '__main__':
    # Create necessary directories if they don't exist
    os.makedirs(app.config['OUTPUT_DIR'], exist_ok=True)
    os.makedirs(app.config['TEMPLATE_DIR'], exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    app.run(debug=True)
